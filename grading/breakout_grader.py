"""Breakout grader.

`grade_breakout` remains a pass-through (profiles are shells), while
`score_breakout` implements the first iteration of the 30-point breakout
scoring system defined in `GRADING_SYSTEMS.md`:

Breakout Quality (30 pts total):
    - Candle Pattern (max 20)
    - Volume Confirmation (max 10)

Implemented heuristic mapping (initial version):
    Pattern component (0–20):
        - Marubozu (bullish/bearish) -> 20
        - Engulfing (approximated: body_pct >= 0.75 and both wicks <= 10%) -> 18
        - Wide-Range Breakout (WRB heuristic: body_pct >= 0.70) -> 17
        - Belt Hold (heuristic: body_pct >= 0.65 and one wick <=5%, other <=15%) -> 15
        - Other Clean Candle (body_pct >= 0.60) -> 13
        - Messy/overlapping (body_pct >= 0.40) -> 10
        - Weak / small body (body_pct < 0.40) -> 7

    Volume component (0–10) using provided `vol_ratio` (breakout volume / 5m avg):
        - > 1.5x -> 10
        - 1.2x – 1.5x -> 5
        - 1.0x – 1.2x -> 2
        - < 1.0x -> 0

Notes:
    - True Engulfing would require the previous candle; an approximation is
        used until previous candle context is plumbed into the scoring interface.
    - WRB & Belt Hold definitions are heuristic and may be refined later.
    - Function returns an int 0–30. Invalid candles => 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from candle_patterns import classify_candle_strength
from config_utils import load_config

CONFIG = load_config()


def _load_filters() -> Dict[str, bool]:
    defaults = {
        "filter_breakout_pattern": True,
        "filter_breakout_volume": True,
    }
    try:
        cfg_path = Path(__file__).parent / "breakout_grader.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text())
            if isinstance(data, dict):
                defaults.update({k: bool(v) for k, v in data.items()})
    except Exception:
        pass
    return defaults


FILTERS = _load_filters()


def grade_breakout(candle: Dict[str, float], vol_ratio: float, profile: Dict) -> Tuple[bool, str]:
    # Thresholds removed entirely: validate candle shape only.
    try:
        float(candle.get("Open"))
        float(candle.get("High"))
        float(candle.get("Low"))
        float(candle.get("Close"))
    except Exception:
        return False, "invalid_candle"
    return True, "ok"


def score_breakout_details(
    candle: Dict[str, float],
    vol_ratio: float,
    profile: Dict,
    direction: Optional[str] = None,
) -> Dict[str, object]:
    """Return detailed breakout scoring components and total.

    Returns a dict including:
      - total: int (0–30)
      - pattern_pts: int (0–20)
      - volume_pts: int (0–10)
      - ctype: str (classified candle type)
      - body_pct, upper_wick_pct, lower_wick_pct: floats
      - candle_dir: str (bullish/bearish/neutral)
    """
    # Validate OHLC first
    try:
        o = float(candle.get("Open"))
        h = float(candle.get("High"))
        lo = float(candle.get("Low"))
        c = float(candle.get("Close"))
    except Exception:
        return {
            "total": 0,
            "pattern_pts": 0,
            "volume_pts": 0,
            "ctype": "invalid",
            "body_pct": 0.0,
            "upper_wick_pct": 0.0,
            "lower_wick_pct": 0.0,
            "candle_dir": "neutral",
        }

    # Feature flag: if breakout grader disabled, return max points immediately
    if not CONFIG.get("feature_breakout_grader_enable", True):
        return {
            "total": 30,
            "pattern_pts": 20,
            "volume_pts": 10,
            "ctype": "disabled",
            "body_pct": 0.0,
            "upper_wick_pct": 0.0,
            "lower_wick_pct": 0.0,
            "candle_dir": "neutral",
        }
    rng = h - lo
    if rng <= 0:
        return {
            "total": 0,
            "pattern_pts": 0,
            "volume_pts": 0,
            "ctype": "zero_range",
            "body_pct": 0.0,
            "upper_wick_pct": 0.0,
            "lower_wick_pct": 0.0,
            "candle_dir": "neutral",
        }

    # Build a pandas Series for classifier (expects Series-like)
    ser = pd.Series({"Open": o, "High": h, "Low": lo, "Close": c})
    cls = classify_candle_strength(ser)
    body_pct = float(cls.get("body_pct", 0.0))
    upper_wick_pct = float(cls.get("upper_wick_pct", 0.0))
    lower_wick_pct = float(cls.get("lower_wick_pct", 0.0))
    ctype = str(cls.get("type", "unknown"))
    candle_dir = str(cls.get("direction", "neutral"))

    # Normalize expected direction if provided (long->bullish, short->bearish)
    if direction is None:
        expected_dir = None
    else:
        d_lower = str(direction).lower()
        if d_lower == "long":
            expected_dir = "bullish"
        elif d_lower == "short":
            expected_dir = "bearish"
        else:
            expected_dir = None

    # -----------------------------
    # Pattern component (0–20)
    # -----------------------------
    pattern_pts = 0
    # Direction mismatch penalty: if we have an expected direction and candle_dir conflicts,
    # immediately degrade to weak pattern bucket (7 points).
    if expected_dir is not None and candle_dir not in {expected_dir, "neutral"}:
        pattern_pts = 7
    # Marubozu (shaved) – minimal wicks + large body (direction must align when provided)
    elif (ctype == "bullish_marubozu" and (expected_dir in (None, "bullish"))) or (
        ctype == "bearish_marubozu" and (expected_dir in (None, "bearish"))
    ):
        pattern_pts = 20
    # Approximated engulfing (needs previous candle for perfect detection)
    elif body_pct >= 0.75 and upper_wick_pct <= 0.10 and lower_wick_pct <= 0.10:
        pattern_pts = (
            18 if (expected_dir is None or candle_dir in {expected_dir, "neutral"}) else 10
        )
    # Wide-Range Breakout heuristic
    elif body_pct >= 0.70:
        pattern_pts = (
            17 if (expected_dir is None or candle_dir in {expected_dir, "neutral"}) else 10
        )
    # Belt Hold heuristic – strong body, one side shaved, small opposite wick
    elif body_pct >= 0.65 and (
        (upper_wick_pct <= 0.05 and lower_wick_pct <= 0.15)
        or (lower_wick_pct <= 0.05 and upper_wick_pct <= 0.15)
    ):
        pattern_pts = (
            15 if (expected_dir is None or candle_dir in {expected_dir, "neutral"}) else 10
        )
    # Other clean candle ≥ 60% body
    elif body_pct >= 0.60:
        pattern_pts = (
            13 if (expected_dir is None or candle_dir in {expected_dir, "neutral"}) else 10
        )
    # Messy / overlapping – moderate body
    elif body_pct >= 0.40:
        pattern_pts = 10
    else:
        pattern_pts = 7

    # Apply component filter override for pattern
    if not FILTERS.get("filter_breakout_pattern", True):
        pattern_pts = 20

    # -----------------------------
    # Volume component (0–10)
    # -----------------------------
    try:
        vr = float(vol_ratio)
    except Exception:
        vr = 0.0
    if vr > 1.5:
        volume_pts = 10
    elif vr >= 1.2:
        volume_pts = 5
    elif vr >= 1.0:
        volume_pts = 2
    else:
        volume_pts = 0

    # Apply component filter override for volume
    if not FILTERS.get("filter_breakout_volume", True):
        volume_pts = 10

    total = pattern_pts + volume_pts
    # Safety clamp
    if total < 0:
        total = 0
    if total > 30:
        total = 30
    return {
        "total": int(round(total)),
        "pattern_pts": int(pattern_pts),
        "volume_pts": int(volume_pts),
        "ctype": ctype,
        "body_pct": float(body_pct),
        "upper_wick_pct": float(upper_wick_pct),
        "lower_wick_pct": float(lower_wick_pct),
        "candle_dir": candle_dir,
    }


def score_breakout(
    candle: Dict[str, float],
    vol_ratio: float,
    profile: Dict,
    direction: Optional[str] = None,
) -> int:
    """Return breakout points (0–30) using pattern + volume scoring."""
    details = score_breakout_details(candle, vol_ratio, profile, direction)
    try:
        return int(details.get("total", 0))
    except Exception:
        return 0
