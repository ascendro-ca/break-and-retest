"""
Break and Retest Detection Module (Multi-timeframe only)

- 5m breakout detection with VWAP alignment and volume threshold
- 1m retest strictly AFTER 5m close with wick touch/pierce and
    correct-side close (<= 1 tick epsilon)
- Next-1m ignition with strong body, break of retest, and volume increase
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

    Requires scan_df to include a rolling volume MA column 'vol_ma' and preferably 'vwap'.
    """
    breakouts: List[Dict] = []

    for i in range(1, len(scan_df)):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i - 1]

        vwap = row.get("vwap", None)
        vwap_aligned_long = (vwap is None) or (row["Close"] > vwap)
        vwap_aligned_short = (vwap is None) or (row["Close"] < vwap)

        breakout_up = (
            prev["High"] <= or_high
            and row["High"] > or_high
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] > or_high
            and vwap_aligned_long
        )
        breakout_down = (
            prev["Low"] >= or_low
            and row["Low"] < or_low
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * vol_threshold
            and row["Close"] < or_low
            and vwap_aligned_short
        )

        if breakout_up:
            breakouts.append(
                {
                    "index": i,
                    "direction": "long",
                    "level": or_high,
                    "time": row["Datetime"],
                    "candle": row,
                    "vwap": vwap,
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
                    "vwap": vwap,
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
    tick_size: float = 0.01,
) -> Optional[Dict]:
    """
    Detect retest and ignition pattern on 1-minute timeframe after a breakout.
    """
    retest_window_start = breakout_time + timedelta(minutes=5)  # after 5m close
    retest_window_end = breakout_time + timedelta(minutes=lookforward_minutes)
    window = df_1m[
        (df_1m["Datetime"] >= retest_window_start) & (df_1m["Datetime"] <= retest_window_end)
    ].copy()

    if len(window) < 2:
        return None

    breakout_up = direction == "long"

    for j in range(len(window) - 1):
        ret = window.iloc[j]
        returns_to_level = (breakout_up and ret["Low"] <= breakout_level) or (
            (not breakout_up) and ret["High"] >= breakout_level
        )
        close_val = float(ret["Close"])
        close_holds = (
            close_val >= (breakout_level - tick_size)
            if breakout_up
            else close_val <= (breakout_level + tick_size)
        )
        if returns_to_level and close_holds:
            ign = window.iloc[j + 1]
            ignition = (
                is_strong_body(ign)
                and (
                    (breakout_up and ign["High"] > ret["High"]) or (not breakout_up and ign["Low"] < ret["Low"])  # noqa: E501
                )
                and ign["Volume"] > ret["Volume"]
            )
            if ignition:
                return {
                    "retest_candle": ret,
                    "ignition_candle": ign,
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
    """
    if df_5m is None or len(df_5m) < 3:
        return []
    if df_1m is None or len(df_1m) < 2:
        return []

    if or_high is None or or_low is None:
        first = df_5m.iloc[0]
        or_high = first["High"]
        or_low = first["Low"]

    breakouts = detect_breakout_5m(df_5m, or_high, or_low, vol_threshold)

    setups: List[Dict] = []
    for br in breakouts:
        pattern = detect_retest_and_ignition_1m(
            df_1m,
            br["time"],
            br["candle"],
            br["level"],
            br["direction"],
        )
        if pattern:
            setups.append(
                {
                    "breakout": br,
                    "retest": pattern["retest_candle"],
                    "ignition": pattern["ignition_candle"],
                    "direction": br["direction"],
                    "level": br["level"],
                    "vwap": br.get("vwap"),
                }
            )

    return setups
