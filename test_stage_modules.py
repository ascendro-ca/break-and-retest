"""
Unit tests for individual stage modules:
- stage_opening_range
- stage_breakout
- stage_retest
- stage_ignition
"""

from datetime import timedelta

import pandas as pd
import pytest

from stage_breakout import base_breakout_filter, detect_breakouts
from stage_ignition import base_ignition_filter, detect_ignition
from stage_opening_range import detect_opening_range
from stage_retest import base_retest_filter, detect_retest

# ============================================================================
# Stage 1: Opening Range Tests
# ============================================================================


def test_opening_range_from_first_candle():
    """Opening range should use the first 5m candle's high/low"""
    times = pd.date_range("2025-11-02 09:30", periods=3, freq="5min")
    df = pd.DataFrame(
        [
            {
                "Datetime": times[0],
                "Open": 100,
                "High": 102,
                "Low": 99,
                "Close": 101,
                "Volume": 10000,
            },
            {
                "Datetime": times[1],
                "Open": 101,
                "High": 103,
                "Low": 100,
                "Close": 102,
                "Volume": 9000,
            },
            {
                "Datetime": times[2],
                "Open": 102,
                "High": 104,
                "Low": 101,
                "Close": 103,
                "Volume": 8000,
            },
        ]
    )

    result = detect_opening_range(df)
    assert result["high"] == 102.0
    assert result["low"] == 99.0
    assert result["open_time"] == times[0]


def test_opening_range_empty_dataframe():
    """Should return zeros for empty dataframe"""
    df = pd.DataFrame()
    result = detect_opening_range(df)
    assert result["high"] == 0.0
    assert result["low"] == 0.0
    assert result["open_time"] is None


# ============================================================================
# Stage 2: Breakout Tests
# ============================================================================


def test_base_breakout_filter_long():
    """Base breakout filter should detect long breakout"""
    prev = pd.Series({"High": 100.0, "Low": 99.0, "Close": 99.5, "Volume": 5000})
    row = pd.Series(
        {
            "High": 101.5,
            "Low": 100.0,
            "Close": 101.0,
            "Volume": 10000,
            "vol_ma_20": 8000,
            "vwap": 100.0,
        }
    )
    or_high = 100.0
    or_low = 99.0

    result = base_breakout_filter(row, prev, or_high, or_low)
    assert result is not None
    assert result[0] == "long"
    assert result[1] == or_high


def test_base_breakout_filter_short():
    """Base breakout filter should detect short breakout"""
    prev = pd.Series({"High": 101.0, "Low": 100.0, "Close": 100.5, "Volume": 5000})
    row = pd.Series(
        {
            "High": 100.0,
            "Low": 98.5,
            "Close": 99.0,
            "Volume": 10000,
            "vol_ma_20": 8000,
            "vwap": 100.0,
        }
    )
    or_high = 101.0
    or_low = 100.0

    result = base_breakout_filter(row, prev, or_high, or_low)
    assert result is not None
    assert result[0] == "short"
    assert result[1] == or_low


def test_base_breakout_filter_no_volume():
    """Should reject breakout without sufficient volume"""
    prev = pd.Series({"High": 100.0, "Low": 99.0, "Close": 99.5, "Volume": 5000})
    row = pd.Series(
        {
            "High": 101.5,
            "Low": 100.0,
            "Close": 101.0,
            "Volume": 5000,  # Below vol_ma_20
            "vol_ma_20": 8000,
            "vwap": 100.0,
        }
    )
    or_high = 100.0
    or_low = 99.0

    result = base_breakout_filter(row, prev, or_high, or_low)
    assert result is None


def test_base_breakout_filter_vwap_alignment():
    """Should reject long breakout if close is below VWAP"""
    prev = pd.Series({"High": 100.0, "Low": 99.0, "Close": 99.5, "Volume": 5000})
    row = pd.Series(
        {
            "High": 101.5,
            "Low": 100.0,
            "Close": 101.0,
            "Volume": 10000,
            "vol_ma_20": 8000,
            "vwap": 101.5,  # Close below VWAP
        }
    )
    or_high = 100.0
    or_low = 99.0

    result = base_breakout_filter(row, prev, or_high, or_low)
    assert result is None


def test_detect_breakouts_within_window():
    """Should find breakouts within the specified time window"""
    times = pd.date_range("2025-11-02 09:30", periods=10, freq="5min")
    rows = [
        {"Datetime": times[0], "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 8000},
        {
            "Datetime": times[1],
            "Open": 100,
            "High": 100.5,
            "Low": 99.5,
            "Close": 100,
            "Volume": 7000,
        },
    ]
    # Breakout at index 2 (within default 90 min window)
    rows.append(
        {
            "Datetime": times[2],
            "Open": 100,
            "High": 102,
            "Low": 100,
            "Close": 101.5,
            "Volume": 12000,
        }
    )
    for i in range(3, 10):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 101,
                "High": 102,
                "Low": 100.5,
                "Close": 101,
                "Volume": 8000,
            }
        )

    df = pd.DataFrame(rows)

    breakouts = detect_breakouts(df, or_high=101.0, or_low=99.0, breakout_window_minutes=90)

    assert len(breakouts) >= 1
    assert breakouts[0]["direction"] == "long"
    assert breakouts[0]["level"] == 101.0


# ============================================================================
# Stage 3: Retest Tests
# ============================================================================


def test_base_retest_filter_long():
    """Retest filter should accept long retest when close >= level"""
    m1 = pd.Series({"Close": 100.5})
    assert base_retest_filter(m1, "long", 100.0) is True
    assert base_retest_filter(m1, "long", 101.0) is False


def test_base_retest_filter_short():
    """Retest filter should accept short retest when close <= level"""
    m1 = pd.Series({"Close": 99.5})
    assert base_retest_filter(m1, "short", 100.0) is True
    assert base_retest_filter(m1, "short", 99.0) is False


def test_detect_retest_after_breakout_close():
    """Retest should only be detected after the 5m breakout closes"""
    breakout_time = pd.Timestamp("2025-11-02 09:40")
    times_1m = pd.date_range(breakout_time, periods=20, freq="1min")

    rows = []
    # First 5 minutes (during breakout candle) - should be ignored
    for i in range(5):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 101,
                "High": 101.2,
                "Low": 100.8,
                "Close": 101,
                "Volume": 2000,
            }
        )
    # After breakout close - valid retest at minute 6
    rows.append(
        {
            "Datetime": times_1m[6],
            "Open": 100.5,
            "High": 100.8,
            "Low": 100.2,
            "Close": 100.4,  # Close above level (100.0)
            "Volume": 1500,
        }
    )
    for i in range(7, 20):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 100,
                "High": 100.5,
                "Low": 99.5,
                "Close": 100,
                "Volume": 1800,
            }
        )

    df_1m = pd.DataFrame(rows)

    result = detect_retest(
        df_1m,
        breakout_time=breakout_time,
        direction="long",
        level=100.0,
        retest_lookahead_minutes=30,
    )

    assert result is not None
    assert result["time"] == times_1m[6]


# ============================================================================
# Stage 4: Continuation/Ignition Tests
# ============================================================================


def test_base_ignition_filter_long():
    """Ignition filter should detect long ignition breaking above retest high"""
    m1 = pd.Series({"High": 101.5, "Low": 100.5, "Close": 101.2})
    # Should break retest_high
    assert base_ignition_filter(m1, "long", retest_high=101.0, retest_low=100.0) is True
    assert base_ignition_filter(m1, "long", retest_high=102.0, retest_low=100.0) is False


def test_base_ignition_filter_short():
    """Ignition filter should detect short ignition breaking below retest low"""
    m1 = pd.Series({"High": 100.5, "Low": 99.5, "Close": 99.8})
    # Should break retest_low
    assert base_ignition_filter(m1, "short", retest_high=101.0, retest_low=100.0) is True
    assert base_ignition_filter(m1, "short", retest_high=101.0, retest_low=99.0) is False


def test_detect_continuation_ignition_after_retest():
    """Ignition should be detected in the candles after retest"""
    retest_time = pd.Timestamp("2025-11-02 09:50")
    retest_candle = pd.Series(
        {
            "Datetime": retest_time,
            "Open": 100.0,
            "High": 100.5,
            "Low": 99.8,
            "Close": 100.2,
            "Volume": 1500,
        }
    )

    times_1m = pd.date_range(retest_time + timedelta(minutes=1), periods=10, freq="1min")
    rows = []
    # First bar after retest is the ignition
    rows.append(
        {
            "Datetime": times_1m[0],
            "Open": 100.2,
            "High": 101.0,  # Breaks above retest high (100.5)
            "Low": 100.0,
            "Close": 100.8,
            "Volume": 3000,
        }
    )
    for i in range(1, 10):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 100,
                "High": 100.5,
                "Low": 99.5,
                "Close": 100,
                "Volume": 1800,
            }
        )

    df_1m = pd.DataFrame(rows)

    result = detect_ignition(
        df_1m,
        retest_time=retest_time,
        retest_candle=retest_candle,
        direction="long",
        ignition_lookahead_minutes=30,
    )

    assert result is not None
    assert result["time"] == times_1m[0]


def test_detect_continuation_separate_ignition():
    """Ignition can be a separate candle after retest"""
    retest_time = pd.Timestamp("2025-11-02 09:50")
    retest_candle = pd.Series(
        {
            "Datetime": retest_time,
            "Open": 100.0,
            "High": 100.5,  # Does not break above
            "Low": 99.8,
            "Close": 100.2,
            "Volume": 1500,
        }
    )

    times_1m = pd.date_range(retest_time + timedelta(minutes=1), periods=10, freq="1min")
    rows = []
    # First few bars don't break
    for i in range(2):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 100,
                "High": 100.4,
                "Low": 99.9,
                "Close": 100.1,
                "Volume": 1800,
            }
        )
    # Ignition at index 2
    rows.append(
        {
            "Datetime": times_1m[2],
            "Open": 100.2,
            "High": 101.0,  # Breaks above retest high (100.5)
            "Low": 100.0,
            "Close": 100.8,
            "Volume": 3000,
        }
    )
    for i in range(3, 10):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 100,
                "High": 100.5,
                "Low": 99.5,
                "Close": 100,
                "Volume": 1800,
            }
        )

    df_1m = pd.DataFrame(rows)

    result = detect_ignition(
        df_1m,
        retest_time=retest_time,
        retest_candle=retest_candle,
        direction="long",
        ignition_lookahead_minutes=30,
    )

    assert result is not None
    assert result["time"] == times_1m[2]
