"""Ignition grader (1m continuation) – real scoring.

Implements the 30-point ignition scoring block from GRADING_SYSTEMS.md:

Ignition Quality (Max 30 pts)
    - Candle Pattern (max 20)
            Marubozu: 20
            WRB: 18
            Engulfing: 17
            Belt Hold: 15
            Other momentum: 12–14
            Wicky/indecisive: 7–10
    - Volume confirmation (max 5)
            ≥ 1.5x retest volume AND > 90th pctile: +5
            ≥ 1.3x retest volume AND > average:     +3
            > retest volume but < average:          +1
            ≤ retest volume:                        +0

Notes/assumptions:
    - We currently do not have the 1m session average or 90th percentile volume in `signal`.
        As a pragmatic approximation we use `ignition_vol_ratio = ignition_vol / retest_vol`:
                - ≥ 1.5x -> +5
                - ≥ 1.3x -> +3
                - >  1.0 -> +1
                - else    -> +0
        This preserves the intended tiering while we avoid unavailable stats.
    - Candle classification uses `candle_patterns.classify_candle_strength`.
        Where exact pattern types aren't available on 1m, we fall back to body/wick heuristics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from candle_patterns import classify_candle_strength
from config_utils import load_config

CONFIG = load_config()


def _load_filters() -> Dict[str, bool]:
    defaults = {
        "filter_ignition_pattern": True,
        "filter_ignition_volume": True,
    }
    try:
        cfg_path = Path(__file__).parent / "ignition_grader.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text())
            if isinstance(data, dict):
                defaults.update({k: bool(v) for k, v in data.items()})
    except Exception:
        pass
    return defaults


FILTERS = _load_filters()


def grade_ignition(
    ignition_candle: Dict[str, float],
    *,
    ignition_body_pct: float,
    ignition_vol_ratio: float,
    progress: float,
    profile: Dict,
) -> Tuple[bool, str]:
    th = profile.get("ignition", {})
    if not th:
        return True, "ok"


def score_ignition(
    ignition_candle: Dict[str, float],
    *,
    ignition_body_pct: float,
    ignition_vol_ratio: float,
    progress: float,
    profile: Dict,
) -> int:
    """Return ignition points on a 0–30 scale.

    Inputs expected (robust to missing):
      - ignition_candle: dict with Open/High/Low/Close
      - ignition_body_pct: precomputed |C-O|/(H-L) for the 1m bar
      - ignition_vol_ratio: ignition_vol / retest_vol (ratio)
      - progress: distance toward target at ignition close (0..1) – not scored here
    """
    # Feature flag: if ignition grader disabled, return max points
    if not CONFIG.get("feature_ignition_grader_enable", True):
        return 30

    # Determine component toggles up-front
    pattern_enabled = FILTERS.get("filter_ignition_pattern", True)
    volume_enabled = FILTERS.get("filter_ignition_volume", True)

    # If both components are disabled, award combined max (20 + 5 = 25)
    if not pattern_enabled and not volume_enabled:
        return 25

    # Pattern component (0–20)
    pattern_pts = 0
    if not pattern_enabled:
        pattern_pts = 20
    else:
        # Validate candle fields only when pattern scoring is enabled
        try:
            o = float(ignition_candle.get("Open"))
            h = float(ignition_candle.get("High"))
            low_ = float(ignition_candle.get("Low"))
            c = float(ignition_candle.get("Close"))
        except Exception:
            o = h = low_ = c = None

        if o is not None and h is not None and low_ is not None and c is not None:
            rng = h - low_
            if rng > 0:
                # Classify candle strength on 1m ignition
                try:
                    ser = pd.Series({"Open": o, "High": h, "Low": low_, "Close": c})
                    cls = classify_candle_strength(ser)
                    body_pct = float(cls.get("body_pct", ignition_body_pct or 0.0))
                    upper_wick_pct = float(cls.get("upper_wick_pct", 0.0))
                    lower_wick_pct = float(cls.get("lower_wick_pct", 0.0))
                    ctype = str(cls.get("type", "unknown"))
                except Exception:
                    body_pct = float(ignition_body_pct or 0.0)
                    upper_wick_pct = lower_wick_pct = 0.0
                    ctype = "unknown"

                # Pattern mapping
                if ctype in {"bullish_marubozu", "bearish_marubozu"}:
                    pattern_pts = 20
                elif body_pct >= 0.75 and upper_wick_pct <= 0.15 and lower_wick_pct <= 0.15:
                    pattern_pts = 18
                elif body_pct >= 0.70 and upper_wick_pct <= 0.10 and lower_wick_pct <= 0.10:
                    pattern_pts = 17
                elif body_pct >= 0.65 and (
                    (upper_wick_pct <= 0.05 and lower_wick_pct <= 0.15)
                    or (lower_wick_pct <= 0.05 and upper_wick_pct <= 0.15)
                ):
                    pattern_pts = 15
                elif body_pct >= 0.55:
                    pattern_pts = 14
                elif body_pct >= 0.45:
                    pattern_pts = 12
                elif body_pct >= 0.30:
                    pattern_pts = 10
                else:
                    pattern_pts = 7
            else:
                pattern_pts = 0
        else:
            # Missing/invalid candle when pattern scoring is enabled → 0 for pattern
            pattern_pts = 0

    # -----------------------------
    # Volume confirmation (0–5) – approximated with ignition_vol_ratio
    # -----------------------------
    if not volume_enabled:
        vol_pts = 5
    else:
        try:
            vr = float(ignition_vol_ratio)
        except Exception:
            vr = 0.0
        if vr >= 1.5:
            vol_pts = 5
        elif vr >= 1.3:
            vol_pts = 3
        elif vr > 1.0:
            vol_pts = 1
        else:
            vol_pts = 0

    total = pattern_pts + vol_pts
    return int(max(0, min(30, round(total))))
