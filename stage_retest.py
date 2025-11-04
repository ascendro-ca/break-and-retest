"""
Stage 3: Retest Detection
==========================

Detects when price retests the breakout level on 1-minute candles after the
5-minute breakout candle has closed.

Base Criteria (always applied):
- Retest search begins AFTER the 5m breakout candle closes (breakout_time + 5 minutes)
- First 1m candle whose body closes on the correct side of the level:
  - Long: close >= level
  - Short: close <= level
- Retest must occur within the first 90 minutes of market open
  (and still after the breakout candle closes)

Grading (optional, via config/CLI):
- Wick touch/pierce requirement (currently not in base)
- Close tolerance (e.g., within 1 tick of level)
- Volume characteristics during retest
- Structure quality (pullback cleanness)

Returns:
    Retest candidate dict if found, else None
"""

from datetime import timedelta
from typing import Callable, Dict, Optional

import pandas as pd


def base_retest_filter(m1: pd.Series, direction: str, level: float) -> bool:
    """
    Base retest criteria (minimal/permissive).

    Returns:
        True if the 1m candle qualifies as a valid retest close
    """
    c = float(m1.get("Close", 0.0))
    return (direction == "long" and c >= level) or (direction == "short" and c <= level)


def detect_retest(
    session_df_1m: pd.DataFrame,
    breakout_time: pd.Timestamp,
    direction: str,
    level: float,
    retest_lookahead_minutes: int = 30,  # Deprecated but kept for backward compatibility
    retest_filter: Optional[Callable[[pd.Series, str, float], bool]] = None,
) -> Optional[Dict]:
    """
    Detect retest after a breakout.

    Args:
        session_df_1m: 1m session data, sorted ascending
        breakout_time: Datetime when the 5m breakout candle started
        direction: 'long' or 'short'
        level: The OR level being tested
        retest_lookahead_minutes: DEPRECATED - No longer used. Retest window is now
                                  determined by 90 minutes from market open.
        retest_filter: Optional custom filter; if None, uses base_retest_filter

    Returns:
        Dict with keys: time, candle if retest found, else None
    """
    if session_df_1m is None or session_df_1m.empty:
        return None

    # Determine market open time (first timestamp in session data)
    market_open = session_df_1m.iloc[0]["Datetime"]

    # Retest window starts AFTER the 5m breakout candle closes
    retest_window_start = breakout_time + timedelta(minutes=5)

    # Retest window ends at 90 minutes from market open
    retest_window_end = market_open + timedelta(minutes=90)

    window_1m = session_df_1m[
        (session_df_1m["Datetime"] >= retest_window_start)
        & (session_df_1m["Datetime"] <= retest_window_end)
    ]

    if window_1m.empty:
        return None

    filter_fn = retest_filter or base_retest_filter

    for _, m1 in window_1m.iterrows():
        if filter_fn(m1, direction, level):
            return {"time": m1["Datetime"], "candle": m1}

    return None
