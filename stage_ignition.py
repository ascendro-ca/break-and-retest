"""
Stage 4: Ignition Detection
============================

Detects the ignition candle that confirms continuation after trade entry.

IMPORTANT: Stage 4 is for POST-ENTRY confirmation, not pre-entry filtering.
- In base pipeline mode: Stage 4 is optional and does NOT filter candidates
- Candidates pass Stage 1-3 and are valid trade setups without ignition
- Ignition detection is used after entry to confirm the trade is working

Base Criteria (always applied when Stage 4 is enabled):
- Ignition search begins in the candles AFTER the retest candle
- For long: ignition breaks above the retest candle's high
- For short: ignition breaks below the retest candle's low
- Ignition must occur within ignition_lookahead_minutes of retest

Note:
- The retest candle itself does NOT qualify as ignition in base detection
  (since it by definition establishes the retest high/low reference)
- Ignition must be a subsequent candle that breaks beyond the retest range

Grading (optional, via config/CLI):
- Body strength (% of candle range that is body)
- Volume ratio vs breakout volume
- Distance toward target achieved
- Speed of formation
- Could allow retest candle as ignition under strict body/volume criteria

Returns:
    Ignition candidate dict if found, else None
"""

from datetime import timedelta
from typing import Callable, Dict, Optional

import pandas as pd


def retest_qualifies_as_ignition(
    retest_candle: pd.Series,
    direction: str,
    breakout_candle: pd.Series,
    session_df_1m: pd.DataFrame = None,
) -> bool:
    """
    Check if retest candle meets ignition criteria (Case 2).

    Uses the same grading logic as grade_continuation from points grading system:
    - Strong body (marubozu/WRB-like)
    - Good volume (retest candle itself has strong volume)

    If retest qualifies as ignition, we can enter immediately without waiting for Stage 4.

    Args:
        retest_candle: The retest candle
        direction: 'long' or 'short'
        breakout_candle: The breakout candle (for reference, not used in current logic)
        session_df_1m: Optional 1m session data for volume percentile checks

    Returns:
        True if retest candle qualifies as ignition (can bypass Stage 4)
    """
    try:
        # Calculate body percentage (same as grading logic)
        o = float(retest_candle.get("Open", 0.0))
        h = float(retest_candle.get("High", 0.0))
        low = float(retest_candle.get("Low", 0.0))
        c = float(retest_candle.get("Close", 0.0))
        rng = max(h - low, 1e-9)
        body_pct = abs(c - o) / rng

        # For retest-as-ignition, we want strong volume on the retest itself
        # Since we're comparing ignition to retest, and retest IS ignition here,
        # we need the retest to have strong absolute volume
        retest_vol = float(retest_candle.get("Volume", 0.0))

        # Require strong body (at least belt-hold level: 60% body)
        if body_pct < 0.60:
            return False

        # Check directionality: close must be in correct direction
        if direction == "long":
            # For long: close should be in upper half of range
            close_position = (c - low) / rng if rng > 0 else 0.0
            if close_position < 0.5:
                return False
        else:
            # For short: close should be in lower half of range
            close_position = (c - low) / rng if rng > 0 else 0.0
            if close_position > 0.5:
                return False

        # If session data available, check if retest volume is strong relative to session
        if session_df_1m is not None and not session_df_1m.empty:
            try:
                session_volumes = session_df_1m["Volume"].dropna()
                if len(session_volumes) > 0:
                    # Require retest volume to be at least above median for retest-as-ignition
                    if retest_vol < session_volumes.median():
                        return False
            except Exception:
                pass

        return True

    except Exception:
        return False


def base_ignition_filter(
    m1: pd.Series, direction: str, retest_high: float, retest_low: float
) -> bool:
    """
    Base ignition criteria (minimal/permissive).

    For Stage 4 ignition: Ignition must break beyond retest candle (wick or close).

    Args:
        m1: 1-minute candle
        direction: 'long' or 'short'
        retest_high: High of the retest candle
        retest_low: Low of the retest candle

    Returns:
        True if the candle qualifies as ignition
    """
    if direction == "long":
        # For long, ignition must break above retest high (wick or close)
        return float(m1.get("High", 0.0)) > retest_high
    else:
        # For short, ignition must break below retest low (wick or close)
        return float(m1.get("Low", 0.0)) < retest_low


def detect_ignition(
    session_df_1m: pd.DataFrame,
    retest_time: pd.Timestamp,
    retest_candle: pd.Series,
    direction: str,
    ignition_lookahead_minutes: int = 30,
    ignition_filter: Optional[Callable[[pd.Series, str, float, float], bool]] = None,
) -> Optional[Dict]:
    """
    Detect ignition after a retest (Stage 4: post-entry confirmation).

    Args:
        session_df_1m: 1m session data, sorted ascending
        retest_time: Datetime when the retest candle occurred
        retest_candle: The retest candle (Series or dict-like)
        direction: 'long' or 'short'
        ignition_lookahead_minutes: Minutes after retest to search for ignition
        ignition_filter: Optional custom filter; if None, uses base_ignition_filter

    Returns:
        Dict with keys: time, candle if ignition found, else None
    """
    if session_df_1m is None or session_df_1m.empty:
        return None

    # Extract retest high/low
    retest_high = float(retest_candle.get("High", 0.0))
    retest_low = float(retest_candle.get("Low", 0.0))

    if retest_high == 0.0 or retest_low == 0.0:
        return None

    filter_fn = ignition_filter or base_ignition_filter

    # Search for ignition starting from the NEXT candle after retest
    # (The retest candle by definition touches/closes on the level,
    #  ignition must break beyond the retest candle's range)
    window_start = retest_time + timedelta(minutes=1)
    window_end = retest_time + timedelta(minutes=ignition_lookahead_minutes)

    window_1m = session_df_1m[
        (session_df_1m["Datetime"] >= window_start) & (session_df_1m["Datetime"] <= window_end)
    ]

    if window_1m.empty:
        return None

    for _, m1 in window_1m.iterrows():
        if filter_fn(m1, direction, retest_high, retest_low):
            return {"time": m1["Datetime"], "candle": m1}

    return None
