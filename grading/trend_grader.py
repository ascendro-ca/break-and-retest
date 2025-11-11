"""Trend/context grader.

Components (max 10):
    - HTF context (stub): fixed +5 points.
    - VWAP confirmation (max 5):
            - Breakout 5m close vs 5m VWAP at breakout (+3)
                    Long: Close >= VWAP; Short: Close <= VWAP
            - Retest 1m body vs 1m VWAP at retest (+2)
                    Long: min(Open, Close) >= VWAP; Short: max(Open, Close) <= VWAP

Assumes the signal carries:
    - signal['breakout_candle']['vwap'] for the breakout 5m bar
    - signal['retest_candle']['vwap'] for the retest 1m bar

If VWAP fields are missing, the corresponding points are not awarded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from config_utils import load_config

CONFIG = load_config()


def _load_filters() -> Dict[str, bool]:
    defaults = {
        "filter_trend_htf_stub": True,
        "filter_trend_vwap_breakout": True,
        "filter_trend_vwap_retest": True,
    }
    try:
        cfg_path = Path(__file__).parent / "trend_grader.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text())
            if isinstance(data, dict):
                defaults.update({k: bool(v) for k, v in data.items()})
    except Exception:
        pass
    return defaults


FILTERS = _load_filters()


def score_trend(signal: Dict, profile: Dict | None = None) -> int:
    """Return trend/context points (0–10) as HTF stub + VWAP checks.

    Disabled-filter contract:
    - If ALL trend sub-filters are disabled, return full 10 immediately.
    - If an individual sub-filter is disabled, award that component's max.
    Robustness:
    - Tolerates non-dict signal and missing fields without raising.
    """
    # Feature flag: if trend grader disabled, return max points (10)
    if not CONFIG.get("feature_trend_grader_enable", True):
        return 10

    sig = signal if isinstance(signal, dict) else {}
    # Avoid truth-value checks on pandas Series; don't use `or {}` on possibly-Series values
    breakout = sig.get("breakout_candle") if isinstance(sig, dict) else {}
    retest = sig.get("retest_candle") if isinstance(sig, dict) else {}
    breakout = {} if breakout is None else breakout
    retest = {} if retest is None else retest
    direction = str(sig.get("direction", "") if isinstance(sig, dict) else "").lower()

    # Early short-circuit: all sub-filters disabled => full 10
    try:
        ft = FILTERS or {}
        if (
            not bool(ft.get("filter_trend_htf_stub", True))
            and not bool(ft.get("filter_trend_vwap_breakout", True))
            and not bool(ft.get("filter_trend_vwap_retest", True))
        ):
            return 10
    except Exception:
        # Continue to compute best-effort points
        pass

    points = 0

    # HTF context (stub): +5 (kept for symmetry; not gated by data)
    try:
        if FILTERS.get("filter_trend_htf_stub", True):
            points += 5
        else:
            points += 5  # award same points when disabled
    except Exception:
        points += 5  # safest default

    # VWAP 5m breakout close vs 5m VWAP (+3)
    try:
        if FILTERS.get("filter_trend_vwap_breakout", True):
            try:
                vwap5 = float(breakout.get("vwap"))
                close5 = float(breakout.get("Close"))
                if direction == "long" and close5 >= vwap5:
                    points += 3
                elif direction == "short" and close5 <= vwap5:
                    points += 3
            except Exception:
                pass
        else:
            points += 3  # award max when disabled
    except Exception:
        # If FILTERS access failed, do not add points here (conservative)
        pass

    # VWAP 1m retest body vs 1m VWAP (+2)
    try:
        if FILTERS.get("filter_trend_vwap_retest", True):
            try:
                vwap1 = float(retest.get("vwap"))
                o1 = float(retest.get("Open"))
                c1 = float(retest.get("Close"))
                if direction == "long" and min(o1, c1) >= vwap1:
                    points += 2
                elif direction == "short" and max(o1, c1) <= vwap1:
                    points += 2
            except Exception:
                pass
        else:
            points += 2  # award max when disabled
    except Exception:
        # If FILTERS access failed, do not add points here (conservative)
        pass

    # Clamp to 0–10
    return int(max(0, min(10, points)))
