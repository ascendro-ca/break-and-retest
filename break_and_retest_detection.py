"""
Break and Retest Detection Module

Shared logic for detecting breakout, retest, and ignition patterns.
Multi-timeframe only: 5m breakout detection, 1m retest and ignition.
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
        scan_df: DataFrame with 5-minute candles (must have vol_ma and vwap columns)
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
            - vwap: VWAP value at breakout time
    """
    breakouts = []

    for i in range(1, len(scan_df)):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i - 1]

        # Get VWAP value (if available)
        vwap = row.get("vwap", None)

        # VWAP filter: LONG requires close > VWAP, SHORT requires close < VWAP
        vwap_aligned_long = (vwap is None) or (row["Close"] > vwap)
        vwap_aligned_short = (vwap is None) or (row["Close"] < vwap)

        breakout_up = (
            prev["High"] <= or_high
            and row["High"] > or_high
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] > or_high
            and vwap_aligned_long  # VWAP filter for long
        )

        breakout_down = (
            prev["Low"] >= or_low
            and row["Low"] < or_low
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] < or_low
            """
            Deprecated compatibility shim for detection functions.

            Note: The project now uses multi-timeframe-only detection implemented in
            `break_and_retest_detection_mt.py`. This module re-exports the public API so
            older imports continue to work until the file can be removed.
            """

            from break_and_retest_detection_mt import (  # noqa: F401
                detect_breakout_5m,
                detect_retest_and_ignition_1m,
                is_strong_body,
                scan_for_setups,
            )
                else:
                    close_holds = close_val <= (breakout_level + tick_size)

                if returns_to_level and close_holds:
                    # Ignition is the very next 1-minute candle
                    ign_1m = df_1m_window.iloc[j + 1]

                    ignition = (
                        is_strong_body(ign_1m)
                        and (
                            (breakout_up and ign_1m["High"] > retest_1m["High"]) or (not breakout_up and ign_1m["Low"] < retest_1m["Low"])
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


        def scan_for_setups(
            df_5m: pd.DataFrame,
            df_1m: pd.DataFrame,
            or_high: Optional[float] = None,
            or_low: Optional[float] = None,
            vol_threshold: float = 1.0,
        ) -> List[Dict]:
            """
            Scan for break and retest setups (multi-timeframe only).

            Args:
                df_5m: DataFrame with 5-minute candles (must have Datetime, OHLCV, vol_ma)
                df_1m: DataFrame with 1-minute candles (required)
                or_high: Opening range high (if None, uses first candle high)
                or_low: Opening range low (if None, uses first candle low)
                vol_threshold: Volume multiplier for breakout detection (default 1.0)

            Returns:
                List of setup dictionaries with complete signal information
            """
            if df_5m is None or len(df_5m) < 3:
                return []
            if df_1m is None or len(df_1m) < 2:
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
                # Always use 1-minute timeframe for retest and ignition
                pattern = detect_retest_and_ignition_1m(
                    df_1m,
                    breakout["time"],
                    breakout["candle"],
                    breakout["level"],
                    breakout["direction"],
                )

                if pattern:
                    setup = {
                        "breakout": breakout,
                        "retest": pattern["retest_candle"],
                        "ignition": pattern["ignition_candle"],
                        "direction": breakout["direction"],
                        "level": breakout["level"],
                        "vwap": breakout.get("vwap"),
                    }
                    setups.append(setup)

            return setups
