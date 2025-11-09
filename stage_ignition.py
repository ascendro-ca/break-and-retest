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


def _ensure_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP column if not present"""
    if "vwap" in df.columns:
        return df
    df = df.copy()
    df["typical_price"] = (df["High"] + df["Low"] + df["Close"]) / 3
    if "Volume" in df.columns:
        df["tp_volume"] = df["typical_price"] * df["Volume"]
        df["vwap"] = df["tp_volume"].cumsum() / df["Volume"].cumsum()
    else:
        # If Volume is missing, set VWAP to typical price as a fallback
        df["vwap"] = df["typical_price"]
    return df


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
    m1: pd.Series,
    direction: str,
    retest_high: float,
    retest_low: float,
    enable_vwap_check: bool = True,
) -> bool:
    """
    Base ignition criteria with optional VWAP alignment.

    VWAP alignment validates institutional flow alignment closer to actual entry timing.

    Args:
        m1: 1-minute candle
        direction: 'long' or 'short'
        retest_high: High of the retest candle
        retest_low: Low of the retest candle
        enable_vwap_check: If True, enforce VWAP alignment (default: True)

    Returns:
        True if the candle qualifies as ignition
    """
    # First check basic ignition criteria
    if direction == "long":
        # For long, ignition must break above retest high (wick or close)
        basic_check = float(m1.get("High", 0.0)) > retest_high
    else:
        # For short, ignition must break below retest low (wick or close)
        basic_check = float(m1.get("Low", 0.0)) < retest_low

    if not basic_check:
        return False

    # VWAP alignment with 0.05% buffer (optional)
    if enable_vwap_check:
        c = float(m1.get("Close", 0.0))
        vwap_val = float(m1.get("vwap", float("nan")))

        if not pd.isna(vwap_val):
            vwap_buffer = abs(vwap_val) * 0.0005  # 0.05% = 0.0005

            if direction == "long":
                vwap_aligned = c >= (vwap_val - vwap_buffer)
            else:  # short
                vwap_aligned = c <= (vwap_val + vwap_buffer)

            return vwap_aligned

    # If VWAP check is disabled or VWAP not available, return True (basic check already passed)
    return True


def detect_ignition(
    session_df_1m: pd.DataFrame,
    retest_time: pd.Timestamp,
    retest_candle: pd.Series,
    direction: str,
    ignition_lookahead_minutes: int = 30,
    ignition_filter: Optional[Callable[[pd.Series, str, float, float], bool]] = None,
    enable_vwap_check: bool = True,
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
        enable_vwap_check: If True, enforce VWAP alignment in base filter (default: True)

    Returns:
        Dict with keys: time, candle if ignition found, else None
    """
    if session_df_1m is None or session_df_1m.empty:
        return None

    session_df_1m = session_df_1m.copy()

    # ------------------------------------------------------------------
    # Timezone Normalization (mirrors Stage 3 logic)
    # ------------------------------------------------------------------
    # Handle mixed tz-aware vs tz-naive comparisons between session datetimes
    # and retest_time. Preserve tz-naive outputs when the input data is naive
    # so existing unit tests remain valid.
    dt_series = session_df_1m["Datetime"]
    session_tz = getattr(dt_series.dt, "tz", None)
    retest_time_adj = retest_time
    try:
        if session_tz is None:
            if retest_time.tzinfo is not None:
                try:
                    retest_time_adj = retest_time.tz_convert("America/New_York").tz_localize(None)
                except Exception:
                    retest_time_adj = retest_time.tz_localize(None)
        else:
            if retest_time.tzinfo is None:
                retest_time_adj = retest_time.tz_localize("America/New_York").tz_convert("UTC")
            else:
                retest_time_adj = retest_time.tz_convert("UTC")
            session_df_1m["Datetime"] = dt_series.dt.tz_convert("UTC")
    except Exception:
        retest_time_adj = retest_time

    # Ensure VWAP is calculated for ignition filtering
    session_df_1m = _ensure_vwap(session_df_1m)

    # Extract retest high/low
    retest_high = float(retest_candle.get("High", 0.0))
    retest_low = float(retest_candle.get("Low", 0.0))

    if retest_high == 0.0 or retest_low == 0.0:
        return None

    # Use custom filter if provided, otherwise use base filter with VWAP check setting
    if ignition_filter is not None:
        filter_fn = ignition_filter
    else:
        # Create a function that captures the enable_vwap_check parameter
        def filter_fn(m1, direction, retest_high, retest_low):
            return base_ignition_filter(m1, direction, retest_high, retest_low, enable_vwap_check)

    # Search for ignition starting from the NEXT candle after retest
    # (The retest candle by definition touches/closes on the level,
    #  ignition must break beyond the retest candle's range)
    window_start = retest_time_adj + timedelta(minutes=1)
    window_end = retest_time_adj + timedelta(minutes=ignition_lookahead_minutes)

    window_1m = session_df_1m[
        (session_df_1m["Datetime"] >= window_start) & (session_df_1m["Datetime"] <= window_end)
    ]

    if window_1m.empty:
        return None

    for _, m1 in window_1m.iterrows():
        if filter_fn(m1, direction, retest_high, retest_low):
            return {"time": m1["Datetime"], "candle": m1}

    return None
