"""
Break and Retest Detection Module

Shared logic for detecting breakout, retest, and ignition patterns.
Supports both single-timeframe and multi-timeframe analysis.
"""

from datetime import timedelta
from typing import Dict, List, Optional

import pandas as pd


def is_strong_body(row):
    """Check if candle has a strong body (>=60% of range)."""
    body = abs(row["Close"] - row["Open"])
    range_ = row["High"] - row["Low"]
    return body >= 0.6 * range_


def detect_breakout_5m(
    scan_df: pd.DataFrame,
    or_high: float,
    or_low: float,
    vol_threshold: float = 1.0,
) -> List[Dict]:
    """
    Detect breakouts on 5-minute timeframe.

    Args:
        scan_df: DataFrame with 5-minute candles (must have vol_ma column)
        or_high: Opening range high level
        or_low: Opening range low level
        vol_threshold: Volume multiplier threshold (default 1.0)

    Returns:
        List of breakout dictionaries with keys:
            - index: Position in scan_df
            - direction: "long" or "short"
            - level: Breakout level (or_high or or_low)
            - time: Datetime of breakout
            - candle: The breakout candle (as Series)
    """
    breakouts = []

    for i in range(1, len(scan_df)):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i - 1]

        breakout_up = (
            prev["High"] <= or_high
            and row["High"] > or_high
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] > or_high
        )

        breakout_down = (
            prev["Low"] >= or_low
            and row["Low"] < or_low
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] < or_low
        )

        if breakout_up:
            breakouts.append(
                {
                    "index": i,
                    "direction": "long",
                    "level": or_high,
                    "time": row["Datetime"],
                    "candle": row,
                }
            )
        elif breakout_down:
            breakouts.append(
                {
                    "index": i,
                    "direction": "short",
                    "level": or_low,
                    "time": row["Datetime"],
                    "candle": row,
                }
            )

    return breakouts


def detect_retest_and_ignition_1m(
    df_1m: pd.DataFrame,
    breakout_time: pd.Timestamp,
    breakout_candle: pd.Series,
    breakout_level: float,
    direction: str,
    lookforward_minutes: int = 30,
) -> Optional[Dict]:
    """
    Detect retest and ignition pattern on 1-minute timeframe after a breakout.

    Args:
        df_1m: DataFrame with 1-minute candles
        breakout_time: Time of the breakout candle
        breakout_candle: The 5-minute breakout candle (used for comparison)
        breakout_level: Level that was broken (or_high or or_low)
        direction: "long" or "short"
        lookforward_minutes: How many minutes to look ahead for pattern

    Returns:
        Dictionary with retest and ignition info if found, None otherwise:
            - retest_candle: The retest candle (as Series)
            - ignition_candle: The ignition candle (as Series)
            - retest_index: Position in df_1m
            - ignition_index: Position in df_1m
    """
    # Get 1-minute window starting after breakout time
    retest_window_end = breakout_time + timedelta(minutes=lookforward_minutes)
    df_1m_window = df_1m[
        (df_1m["Datetime"] > breakout_time) & (df_1m["Datetime"] <= retest_window_end)
    ].copy()

    if len(df_1m_window) < 2:
        return None

    breakout_up = direction == "long"

    # Look for retest + ignition pattern
    for j in range(len(df_1m_window) - 1):
        retest_1m = df_1m_window.iloc[j]

        # Check if this candle retests the level
        returns_to_level = (breakout_up and abs(retest_1m["Low"] - breakout_level) < 0.5) or (
            not breakout_up and abs(retest_1m["High"] - breakout_level) < 0.5
        )

        # Check if it's a tight candle (smaller range than 5m breakout)
        tight_candle = retest_1m["High"] - retest_1m["Low"] < 0.75 * (
            breakout_candle["High"] - breakout_candle["Low"]
        )

        # Volume should be lower than breakout (compare 1m to 5m average)
        # 5m volume / 5 bars, with 1.5x tolerance
        lower_vol = retest_1m["Volume"] < (breakout_candle["Volume"] / 5) * 1.5

        if returns_to_level and tight_candle and lower_vol:
            # Found retest! Now look for ignition on next 1-minute candle
            if j + 1 >= len(df_1m_window):
                continue

            ign_1m = df_1m_window.iloc[j + 1]

            # Ignition: strong body, breaks above/below retest, volume increases
            ignition = (
                is_strong_body(ign_1m)
                and (
                    (breakout_up and ign_1m["High"] > retest_1m["High"])
                    or (not breakout_up and ign_1m["Low"] < retest_1m["Low"])
                )
                and ign_1m["Volume"] > retest_1m["Volume"]
            )

            if ignition:
                return {
                    "retest_candle": retest_1m,
                    "ignition_candle": ign_1m,
                    "retest_index": j,
                    "ignition_index": j + 1,
                }

    return None


def detect_retest_and_ignition_5m(
    scan_df: pd.DataFrame,
    breakout_index: int,
    breakout_candle: pd.Series,
    breakout_level: float,
    direction: str,
) -> Optional[Dict]:
    """
    Detect retest and ignition pattern on same 5-minute timeframe (for single-timeframe mode).

    Args:
        scan_df: DataFrame with 5-minute candles
        breakout_index: Index of breakout candle in scan_df
        breakout_candle: The breakout candle
        breakout_level: Level that was broken
        direction: "long" or "short"

    Returns:
        Dictionary with retest and ignition info if found, None otherwise
    """
    # Need at least 2 candles after breakout (retest + ignition)
    if breakout_index + 2 >= len(scan_df):
        return None

    re_test = scan_df.iloc[breakout_index + 1]
    ign = scan_df.iloc[breakout_index + 2]

    breakout_up = direction == "long"

    # Check retest conditions
    returns_to_level = (breakout_up and abs(re_test["Low"] - breakout_level) < 0.1) or (
        not breakout_up and abs(re_test["High"] - breakout_level) < 0.1
    )

    tight_candle = re_test["High"] - re_test["Low"] < 0.5 * (
        breakout_candle["High"] - breakout_candle["Low"]
    )

    lower_vol = re_test["Volume"] < breakout_candle["Volume"]

    if not (returns_to_level and tight_candle and lower_vol):
        return None

    # Check ignition conditions
    ignition = (
        is_strong_body(ign)
        and (
            (breakout_up and ign["High"] > re_test["High"])
            or (not breakout_up and ign["Low"] < re_test["Low"])
        )
        and ign["Volume"] > re_test["Volume"]
    )

    if ignition:
        return {
            "retest_candle": re_test,
            "ignition_candle": ign,
            "retest_index": breakout_index + 1,
            "ignition_index": breakout_index + 2,
        }

    return None


def scan_for_setups(
    df_5m: pd.DataFrame,
    df_1m: Optional[pd.DataFrame] = None,
    or_high: Optional[float] = None,
    or_low: Optional[float] = None,
    vol_threshold: float = 1.0,
    use_multitimeframe: bool = True,
) -> List[Dict]:
    """
    Scan for break and retest setups.

    Args:
        df_5m: DataFrame with 5-minute candles (must have Datetime, OHLCV, vol_ma)
        df_1m: Optional DataFrame with 1-minute candles (required for multi-timeframe)
        or_high: Opening range high (if None, uses first candle high)
        or_low: Opening range low (if None, uses first candle low)
        vol_threshold: Volume multiplier for breakout detection (default 1.0)
        use_multitimeframe: If True and df_1m provided, use 1m for retest/ignition

    Returns:
        List of setup dictionaries with complete signal information
    """
    if df_5m is None or len(df_5m) < 3:
        return []

    # Get opening range from first candle if not provided
    if or_high is None or or_low is None:
        first_candle = df_5m.iloc[0]
        or_high = first_candle["High"]
        or_low = first_candle["Low"]

    # Detect breakouts on 5-minute timeframe
    breakouts = detect_breakout_5m(df_5m, or_high, or_low, vol_threshold)

    setups = []

    for breakout in breakouts:
        pattern = None

        if use_multitimeframe and df_1m is not None:
            # Use 1-minute timeframe for retest and ignition
            pattern = detect_retest_and_ignition_1m(
                df_1m,
                breakout["time"],
                breakout["candle"],
                breakout["level"],
                breakout["direction"],
            )
        else:
            # Use 5-minute timeframe for everything
            pattern = detect_retest_and_ignition_5m(
                df_5m,
                breakout["index"],
                breakout["candle"],
                breakout["level"],
                breakout["direction"],
            )

        if pattern:
            # Combine breakout and pattern info
            setup = {
                "breakout": breakout,
                "retest": pattern["retest_candle"],
                "ignition": pattern["ignition_candle"],
                "direction": breakout["direction"],
                "level": breakout["level"],
            }
            setups.append(setup)

    return setups
