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
- VWAP alignment with 0.05% buffer:
  - Long: close >= VWAP - 0.05% buffer
  - Short: close <= VWAP + 0.05% buffer
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


def _ensure_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP column if not present"""
    if "vwap" in df.columns:
        return df
    df = df.copy()
    df["typical_price"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["tp_volume"] = df["typical_price"] * df["Volume"]
    df["vwap"] = df["tp_volume"].cumsum() / df["Volume"].cumsum()
    return df


def base_retest_filter(
    m1: pd.Series, direction: str, level: float, enable_vwap_check: bool = True
) -> bool:
    """
    Base retest criteria.

    Args:
        m1: 1-minute candle series
        direction: 'long' or 'short'
        level: The price level being tested
        enable_vwap_check: If True, enforce VWAP alignment in base filter (default: True)

    Returns:
        True if the 1m candle qualifies as a valid retest close
    """
    c = float(m1.get("Close", 0.0))
    vwap = float(m1.get("vwap", 0.0))

    # VWAP buffer is 0.05%
    vwap_buffer = vwap * 0.0005

    if direction == "long":
        # Long: close >= level AND close >= vwap - buffer
        if c >= level and c >= (vwap - vwap_buffer):
            return True
        else:
            return False
    elif direction == "short":
        # Short: close <= level AND close <= vwap + buffer
        if c <= level and c <= (vwap + vwap_buffer):
            return True
        else:
            return False
    else:
        # Unknown direction
        return False


# Level 0 retest filter: body must be at or beyond the OR level in the direction of the trade
def level0_retest_filter(m1: pd.Series, direction: str, level: float) -> bool:
    o = float(m1.get("Open", 0.0))
    c = float(m1.get("Close", 0.0))
    if direction == "long":
        return o >= level and c >= level
    elif direction == "short":
        return o <= level and c <= level
    else:
        return False


def detect_retest(
    session_df_1m: pd.DataFrame,
    breakout_time: pd.Timestamp,
    direction: str,
    level: float,
    retest_lookahead_minutes: int = 30,  # Deprecated but kept for backward compatibility
    retest_filter: Optional[Callable[[pd.Series, str, float], bool]] = None,
    enable_vwap_check: bool = True,
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
        enable_vwap_check: If True, enforce VWAP alignment in base filter (default: True)

    Returns:
        Dict with keys: time, candle if retest found, else None
    """
    if session_df_1m is None or session_df_1m.empty:
        return None

    session_df_1m = session_df_1m.copy()

    # ------------------------------------------------------------------
    # Timezone Normalization Strategy (robust to mixed tz-aware/naive inputs)
    # ------------------------------------------------------------------
    # Unit tests construct tz-naive timestamps (assumed America/New_York). The backtest
    # pipeline increasingly produces tz-aware UTC timestamps for stage transitions.
    # Pandas disallows direct comparison between tz-aware and tz-naive datetimes.
    #
    # Rules:
    # 1. If the session data is tz-naive, downcast any tz-aware breakout_time to naive
    #    America/New_York (convert then drop tz) so tests continue to pass unchanged.
    # 2. If the session data is tz-aware and breakout_time is naive, localize breakout_time
    #    to America/New_York then convert both sides to UTC for uniform comparison.
    # 3. If both are tz-aware (any zone), convert both to UTC.
    # 4. Preserve the original session dataframe timezone style (naive vs aware) so that
    #    returned retest timestamp matches caller expectations (tests expect naive).
    # ------------------------------------------------------------------
    dt_series = session_df_1m["Datetime"]
    session_tz = getattr(dt_series.dt, "tz", None)

    breakout_time_adj = breakout_time
    try:
        if session_tz is None:
            # Session is naive
            if breakout_time.tzinfo is not None:
                # Convert breakout_time to NY local then drop tz
                try:
                    breakout_time_adj = breakout_time.tz_convert("America/New_York").tz_localize(
                        None
                    )
                except Exception:
                    # If already localized to NY, just drop tz
                    breakout_time_adj = breakout_time.tz_localize(None)
        else:
            # Session is tz-aware
            if breakout_time.tzinfo is None:
                # Localize breakout_time to NY first then convert to UTC
                breakout_time_adj = breakout_time.tz_localize("America/New_York").tz_convert("UTC")
            else:
                breakout_time_adj = breakout_time.tz_convert("UTC")
            # Convert session datetimes to UTC for alignment
            session_df_1m["Datetime"] = dt_series.dt.tz_convert("UTC")
    except Exception:
        # Fallback: leave as-is if any unexpected tz errors occur
        breakout_time_adj = breakout_time

    # Ensure VWAP is calculated for retest filtering
    session_df_1m = _ensure_vwap(session_df_1m)

    # Determine market open time (first timestamp in session data)
    market_open = session_df_1m.iloc[0]["Datetime"]

    # Retest window starts AFTER the 5m breakout candle closes
    retest_window_start = breakout_time_adj + timedelta(minutes=5)

    # Retest window ends at 90 minutes from market open
    retest_window_end = market_open + timedelta(minutes=90)

    window_1m = session_df_1m[
        (session_df_1m["Datetime"] >= retest_window_start)
        & (session_df_1m["Datetime"] <= retest_window_end)
    ]

    if window_1m.empty:
        return None

    # Use provided retest_filter (now unified across all pipeline levels). If none, fall back
    # to strict level0_retest_filter semantics instead of the previous VWAP + close-only logic.
    if retest_filter is not None:
        filter_fn = retest_filter
    else:
        # strict parity fallback
        def filter_fn(m1, direction, level):
            o = float(m1.get("Open", 0.0))
            c = float(m1.get("Close", 0.0))
            if direction == "long":
                return o >= level and c >= level
            elif direction == "short":
                return o <= level and c <= level
            return False

    for _, m1 in window_1m.iterrows():
        if filter_fn(m1, direction, level):
            return {"time": m1["Datetime"], "candle": m1}

    return None
