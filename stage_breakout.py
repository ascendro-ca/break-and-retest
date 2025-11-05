"""
Stage 2: Breakout Detection
============================

Detects when price breaks beyond the opening range on a 5-minute candle.

Base Criteria (always applied at Level 0/1):
- Breakout candle is NOT the first 5m candle of the session
- Breakout candle OPEN is inside OR or within small tolerance (gap continuation):
  - Long: open ≤ OR high + 0.25% buffer (allows slight gap above)
  - Short: open ≥ OR low - 0.25% buffer (allows slight gap below)
- Breakout candle CLOSE beyond OR level with 1-tick tolerance:
  - Long: close ≥ OR high - $0.01
  - Short: close ≤ OR low + $0.01

Note: VWAP alignment has been moved to Stage 3 (Retest) to reduce false negatives
      and align with institutional logic for cleaner breakout-confirmation structure.

Note: Volume confirmation (Volume ≥ 1.0× 20-period SMA) has been moved to
    Grade C criteria and is no longer enforced at the base filter for Level 0/1.

Grading (optional, via config/CLI):
- Body strength: % of candle that is body vs wick
- Upper wick size constraints for cleaner entries
- Volume ratio thresholds (can be raised from 1.0x to 1.2x+)

Returns:
    List of breakout candidates with direction, level, time, and candle data
"""

from datetime import timedelta
from typing import Callable, Dict, List, Optional, Tuple

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


def _ensure_vol_ma_20(df: pd.DataFrame) -> pd.DataFrame:
    """Add 20-period volume SMA if not present"""
    if "vol_ma_20" in df.columns:
        return df
    df = df.copy()
    df["vol_ma_20"] = df["Volume"].rolling(window=20, min_periods=1).mean()
    return df


def base_breakout_filter(
    row: pd.Series, prev: pd.Series, or_high: float, or_low: float
) -> Optional[Tuple[str, float]]:
    """
    Base breakout criteria (minimal/permissive with tolerance for gap continuations).

    Allows:
    1. Open inside OR with 0.25% tolerance (gap continuation cases)
    2. Close beyond OR level with 1-tick ($0.01) tolerance

    Note: VWAP alignment moved to retest stage for cleaner breakout detection.

    Returns:
        (direction, level) if breakout valid, else None
    """
    # Base (Level 0/1) relaxed criteria with tolerance
    open_raw = row.get("Open")
    try:
        open_val = float(open_raw) if open_raw is not None else float("nan")
    except Exception:
        open_val = float("nan")
    close_val = float(row["Close"])

    # Tolerance parameters
    TICK_BUFFER = 0.01  # $0.01 tolerance for close
    OPEN_GAP_PCT = 0.0025  # 0.25% tolerance for open (gap continuation)

    # 1) Not the first 5m candle – guaranteed by iteration in detect_breakouts (i>=1)

    # 2) Open must be inside OR with tolerance for gap continuations
    if pd.notna(open_val):
        or_high_buffer = or_high * (1 + OPEN_GAP_PCT)
        or_low_buffer = or_low * (1 - OPEN_GAP_PCT)
        opened_inside_or_long = open_val <= or_high_buffer
        opened_inside_or_short = open_val >= or_low_buffer
    else:
        # If open is missing, allow (for compatibility with unit tests)
        opened_inside_or_long = True
        opened_inside_or_short = True

    # 3) Close beyond OR level with 1-tick tolerance
    close_beyond_long = close_val >= (or_high - TICK_BUFFER)
    close_beyond_short = close_val <= (or_low + TICK_BUFFER)

    brk_long = opened_inside_or_long and close_beyond_long
    brk_short = opened_inside_or_short and close_beyond_short

    if brk_long:
        return ("long", or_high)
    if brk_short:
        return ("short", or_low)
    return None


def detect_breakouts(
    session_df_5m: pd.DataFrame,
    or_high: float,
    or_low: float,
    breakout_window_minutes: int = 90,
    breakout_filter: Optional[
        Callable[[pd.Series, pd.Series, float, float], Optional[Tuple[str, float]]]
    ] = None,
) -> List[Dict]:
    """
    Detect breakout candles within the breakout window.

    Args:
        session_df_5m: 5m session data, sorted ascending
        or_high: Opening range high
        or_low: Opening range low
        breakout_window_minutes: Minutes from session open to scan
        breakout_filter: Optional custom filter; if None, uses base_breakout_filter

    Returns:
        List of breakout dicts with keys: direction, level, time, candle
    """
    if session_df_5m is None or session_df_5m.empty:
        return []

    session_df_5m = session_df_5m.copy()
    session_df_5m = _ensure_vwap(session_df_5m)
    # Keep vol_ma_20 present for grading, but not used by base filter anymore
    session_df_5m = _ensure_vol_ma_20(session_df_5m)

    start_time = session_df_5m.iloc[0]["Datetime"]
    end_time = start_time + timedelta(minutes=breakout_window_minutes)
    scan_df = session_df_5m[
        (session_df_5m["Datetime"] >= start_time) & (session_df_5m["Datetime"] < end_time)
    ].copy()

    if len(scan_df) < 2:
        return []

    filter_fn = breakout_filter or base_breakout_filter
    breakouts = []

    for i in range(1, len(scan_df)):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i - 1]
        verdict = filter_fn(row, prev, or_high, or_low)
        if verdict is not None:
            direction, level = verdict
            breakouts.append(
                {
                    "direction": direction,
                    "level": level,
                    "time": row["Datetime"],
                    "candle": row,
                    "prev_candle": prev,
                }
            )

    return breakouts
