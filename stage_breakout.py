"""
Stage 2: Breakout Detection
============================

Detects when price breaks beyond the opening range on a 5-minute candle.

Base Criteria (always applied):
- Previous 5m high <= OR high (for long) or previous 5m low >= OR low (for short)
- Current 5m close beyond OR level (above for long, below for short)
- Volume >= 1.0x 20-period SMA of volume
- VWAP alignment: long close > VWAP, short close < VWAP

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
    Base breakout criteria (minimal/permissive).

    Returns:
        (direction, level) if breakout valid, else None
    """
    vol_ok = float(row["Volume"]) >= float(row.get("vol_ma_20", 0.0))
    vwap_val = float(row.get("vwap", float("nan")))
    close_val = float(row["Close"])

    brk_long = (
        float(prev["High"]) <= or_high and close_val > or_high and vol_ok and close_val > vwap_val
    )
    brk_short = (
        float(prev["Low"]) >= or_low and close_val < or_low and vol_ok and close_val < vwap_val
    )

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
                {"direction": direction, "level": level, "time": row["Datetime"], "candle": row}
            )

    return breakouts
