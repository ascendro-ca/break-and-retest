"""Retest grader.

`grade_retest` remains a pass-through (profiles are shells). `score_retest`
implements the 30-point retest scoring per GRADING_SYSTEMS.md:

Retest Quality (30 pts total):
    - Candle Pattern (max 20)
    - Volume Filter vs breakout (max 10)

Pattern mapping (heuristics):
    Long retest (direction == 'long'):
        - Hammer / Dragonfly Doji -> 20
        - Pin Bar (lower wick ≥ 55%, body ≤ 20%, upper wick ≤ 20%) -> 18
        - Doji with long rejection lower wick (≥ 40%) -> 17
        - Inside Bar proxy (body ≤ 30% and wicks ≤ 30%) -> 13
        - Other small-wick hold -> 10–12 (based on body/wick)
        - Wick fails to touch level -> 5–9 (based on proximity)

    Short retest mirrors with upper wick criteria (Shooting Star / Gravestone Doji etc.).

Touch/proximity: full credit prefers a clean tap/pierce within 15% of the 1m range and close on the
correct side of the level; otherwise reduce points or apply the near‑miss band (5–9).
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
        "filter_retest_pattern": True,
        "filter_retest_volume": True,
    }
    try:
        cfg_path = Path(__file__).parent / "retest_grader.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text())
            if isinstance(data, dict):
                defaults.update({k: bool(v) for k, v in data.items()})
    except Exception:
        pass
    return defaults


FILTERS = _load_filters()


def grade_retest(
    retest_candle: Dict[str, float],
    *,
    level: float,
    direction: str,
    breakout_time,
    retest_time,
    breakout_volume: float,
    retest_volume: float,
    breakout_candle: Optional[Dict[str, float]] = None,
    profile: Dict,
) -> Tuple[bool, str]:
    # Thresholds removed entirely: validate candle shape only.
    try:
        float(retest_candle.get("Open"))
        float(retest_candle.get("High"))
        float(retest_candle.get("Low"))
        float(retest_candle.get("Close"))
    except Exception:
        return False, "invalid_candle"
    return True, "ok"


def score_retest(
    retest_candle: Dict[str, float],
    *,
    level: float,
    direction: str,
    breakout_time,
    retest_time,
    breakout_volume: float,
    retest_volume: float,
    breakout_candle: Optional[Dict[str, float]] = None,
    profile: Dict = None,
) -> int:
    """Return retest points (0–30) using pattern + volume criteria."""
    # Validate OHLC first
    try:
        o = float(retest_candle.get("Open"))
        h = float(retest_candle.get("High"))
        lo = float(retest_candle.get("Low"))
        c = float(retest_candle.get("Close"))
    except Exception:
        return 0

    # Feature flag: if retest grader disabled, return max points
    if not CONFIG.get("feature_retest_grader_enable", True):
        return 30
    rng = h - lo
    if rng <= 0:
        return 0

    # Classify candle
    ser = pd.Series({"Open": o, "High": h, "Low": lo, "Close": c})
    cls = classify_candle_strength(ser)
    body_pct = float(cls.get("body_pct", 0.0))
    upper_wick_pct = float(cls.get("upper_wick_pct", 0.0))
    lower_wick_pct = float(cls.get("lower_wick_pct", 0.0))
    ctype = str(cls.get("type", "unknown"))
    cdir = str(cls.get("direction", "neutral"))

    dirn = str(direction or "").lower()
    is_long = dirn == "long"
    is_short = dirn == "short"

    # Touch/proximity to level
    touches = (lo - 1e-9) <= float(level) <= (h + 1e-9)
    # Distance from the rejection side to level in % of range
    if is_long:
        prox_ratio = abs(float(level) - lo) / rng if rng > 0 else 1.0
        close_ok = c >= float(level) - 1e-9
    else:
        prox_ratio = abs(h - float(level)) / rng if rng > 0 else 1.0
        close_ok = c <= float(level) + 1e-9

    clean_tap = touches and prox_ratio <= 0.15

    # -----------------------------
    # Pattern component (0–20)
    # -----------------------------
    pattern_pts = 0
    if is_long:
        if ctype in {"hammer", "dragonfly_doji"}:
            pattern_pts = 20
        elif lower_wick_pct >= 0.55 and body_pct <= 0.20 and upper_wick_pct <= 0.20:
            pattern_pts = 18  # pin bar proxy
        elif ctype == "doji" and lower_wick_pct >= 0.40:
            pattern_pts = 17
        elif body_pct <= 0.30 and upper_wick_pct <= 0.30 and lower_wick_pct <= 0.30:
            pattern_pts = 13  # inside bar proxy
        elif body_pct <= 0.40 and lower_wick_pct >= 0.20:
            pattern_pts = 12
        else:
            pattern_pts = 10
        # Direction mismatch penalty (rare for hammer patterns)
        if cdir not in {"bullish", "neutral"}:
            pattern_pts = max(7, pattern_pts - 3)
    elif is_short:
        if ctype in {"shooting_star", "gravestone_doji"}:
            pattern_pts = 20
        elif upper_wick_pct >= 0.55 and body_pct <= 0.20 and lower_wick_pct <= 0.20:
            pattern_pts = 18  # pin bar proxy
        elif ctype == "doji" and upper_wick_pct >= 0.40:
            pattern_pts = 17
        elif body_pct <= 0.30 and upper_wick_pct <= 0.30 and lower_wick_pct <= 0.30:
            pattern_pts = 13  # inside bar proxy
        elif body_pct <= 0.40 and upper_wick_pct >= 0.20:
            pattern_pts = 12
        else:
            pattern_pts = 10
        if cdir not in {"bearish", "neutral"}:
            pattern_pts = max(7, pattern_pts - 3)
    else:
        # Unknown direction – fallback to generic mapping
        pattern_pts = 10 if body_pct >= 0.40 else 7

    # If not touching level, force the near-miss band 5–9 based on proximity
    if not touches:
        if prox_ratio <= 0.05:
            pattern_pts = 9
        elif prox_ratio <= 0.10:
            pattern_pts = 7
        else:
            pattern_pts = 5
    else:
        # If touch but not a clean tap or close on wrong side, shave points
        if not clean_tap or not close_ok:
            pattern_pts = max(5, pattern_pts - 2)

    # Apply component filter override for pattern
    if not FILTERS.get("filter_retest_pattern", True):
        pattern_pts = 20

    # -----------------------------
    # Volume component (0–10)
    # -----------------------------
    vol_bonus = 0
    try:
        br = float(breakout_volume)
        rr = float(retest_volume)
        ratio = rr / br if br > 0 else 1.0
    except Exception:
        ratio = 1.0
    if ratio < 0.15:
        vol_bonus = 10
    elif ratio <= 0.30:
        vol_bonus = 5
    else:
        vol_bonus = 0

    # Apply component filter override for volume
    if not FILTERS.get("filter_retest_volume", True):
        vol_bonus = 10

    total = int(round(min(30, max(0, pattern_pts + vol_bonus))))
    return total
