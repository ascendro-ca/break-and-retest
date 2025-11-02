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


def base_ignition_filter(
    m1: pd.Series, direction: str, retest_high: float, retest_low: float
) -> bool:
    """
    Base ignition criteria (minimal/permissive).

    Args:
        m1: 1-minute candle
        direction: 'long' or 'short'
        retest_high: High of the retest candle
        retest_low: Low of the retest candle

    Returns:
        True if the candle qualifies as ignition
    """
    if direction == "long":
        # For long, ignition must break above retest high
        return float(m1.get("High", 0.0)) > retest_high
    else:
        # For short, ignition must break below retest low
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
