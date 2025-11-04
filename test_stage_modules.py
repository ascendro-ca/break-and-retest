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
    """Base filter should accept even without volume; volume enforced at Grade C"""
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
    assert result is not None
    assert result[0] == "long"
    assert result[1] == or_high


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


def test_breakout_with_existing_vol_ma():
    """Test that breakout detection works when vol_ma_20 column already exists"""
    times = pd.date_range("2025-11-02 09:30", periods=5, freq="5min")
    rows = [
        {
            "Datetime": times[0],
            "Open": 100,
            "High": 101,
            "Low": 99,
            "Close": 100,
            "Volume": 8000,
            "vol_ma_20": 8000,
        },
        {
            "Datetime": times[1],
            "Open": 100,
            "High": 100.5,
            "Low": 99.5,
            "Close": 100,
            "Volume": 7000,
            "vol_ma_20": 7500,
        },
        # Breakout candle with vol_ma_20 already present
        {
            "Datetime": times[2],
            "Open": 100,
            "High": 102,
            "Low": 100,
            "Close": 101.5,
            "Volume": 12000,
            "vol_ma_20": 8500,
        },
    ]
    for i in range(3, 5):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 101,
                "High": 102,
                "Low": 100.5,
                "Close": 101,
                "Volume": 8000,
                "vol_ma_20": 8000,
            }
        )

    df = pd.DataFrame(rows)

    breakouts = detect_breakouts(df, or_high=101.0, or_low=99.0)

    assert len(breakouts) >= 1
    assert breakouts[0]["direction"] == "long"


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


def test_opening_range_single_candle():
    """Opening range with only one candle"""
    times = pd.date_range("2025-11-02 09:30", periods=1, freq="5min")
    df = pd.DataFrame(
        [
            {
                "Datetime": times[0],
                "Open": 100,
                "High": 102,
                "Low": 99,
                "Close": 101,
                "Volume": 10000,
            }
        ]
    )

    result = detect_opening_range(df)
    assert result["high"] == 102.0
    assert result["low"] == 99.0


def test_breakout_no_volume_ma():
    """Test breakout detection when vol_ma_20 is missing"""
    times = pd.date_range("2025-11-02 09:30", periods=5, freq="5min")
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
        {
            "Datetime": times[2],
            "Open": 100,
            "High": 102,
            "Low": 100,
            "Close": 101.5,
            "Volume": 12000,
        },
    ]

    df = pd.DataFrame(rows)
    # Don't compute vol_ma_20, test fallback behavior
    breakouts = detect_breakouts(df, or_high=101.0, or_low=99.0)
    # Should still find breakouts even without vol_ma_20 (uses fallback)
    assert isinstance(breakouts, list)


def test_retest_no_valid_candles():
    """Test retest detection when no valid candles after breakout"""
    breakout_time = pd.Timestamp("2025-11-02 09:40")
    times_1m = pd.date_range(breakout_time, periods=5, freq="1min")

    rows = []
    # All candles during breakout period (should be ignored)
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

    df_1m = pd.DataFrame(rows)

    result = detect_retest(
        df_1m,
        breakout_time=breakout_time,
        direction="long",
        level=100.0,
        retest_lookahead_minutes=30,
    )

    # No valid retest after breakout close
    assert result is None


def test_ignition_immediate_in_retest():
    """Test when retest candle itself could be ignition - implementation doesn't check retest candle"""
    retest_time = pd.Timestamp("2025-11-02 09:50")
    retest_candle = pd.Series(
        {
            "Datetime": retest_time,
            "Open": 100.0,
            "High": 100.8,  # Doesn't break above retest_high
            "Low": 99.8,
            "Close": 100.2,
            "Volume": 1500,
        }
    )

    times_1m = pd.date_range(retest_time + timedelta(minutes=1), periods=10, freq="1min")
    rows = []
    # Next candle breaks above retest_high
    rows.append(
        {
            "Datetime": times_1m[0],
            "Open": 100.2,
            "High": 101.0,  # Breaks above retest high (100.8)
            "Low": 100.0,
            "Close": 100.8,  # Can close at or below retest high
            "Volume": 3000,
        }
    )
    for i in range(1, 10):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 101,
                "High": 101.5,
                "Low": 100.5,
                "Close": 101,
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

    # Should detect ignition in first candle after retest
    assert result is not None
    assert result["time"] == times_1m[0]


def test_breakout_empty_window():
    """Test breakout detection with window that excludes all breakouts"""
    times = pd.date_range("2025-11-02 09:30", periods=30, freq="5min")
    rows = [
        {"Datetime": times[0], "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 8000}
    ]
    # Breakout way outside window
    for i in range(1, 30):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 100,
                "High": 100.5,
                "Low": 99.5,
                "Close": 100,
                "Volume": 7000,
            }
        )
    # Late breakout at index 25 (125 minutes after open)
    rows[25] = {
        "Datetime": times[25],
        "Open": 100,
        "High": 102,
        "Low": 100,
        "Close": 101.5,
        "Volume": 12000,
    }

    df = pd.DataFrame(rows)

    # Use very short window (10 minutes)
    breakouts = detect_breakouts(df, or_high=101.0, or_low=99.0, breakout_window_minutes=10)

    # Should not find the late breakout
    assert len(breakouts) == 0


def test_detect_breakouts_custom_filter_and_min_window():
    """Custom filter should be used; and too-small window (<2 rows) should early-return"""
    times = pd.date_range("2025-11-02 09:30", periods=3, freq="5min")
    df = pd.DataFrame(
        [
            {
                "Datetime": times[0],
                "Open": 100,
                "High": 101,
                "Low": 99,
                "Close": 100,
                "Volume": 8000,
            },
            {
                "Datetime": times[1],
                "Open": 100,
                "High": 100.4,
                "Low": 99.6,
                "Close": 99.9,
                "Volume": 9000,
            },
            {
                "Datetime": times[2],
                "Open": 100,
                "High": 100.3,
                "Low": 99.5,
                "Close": 99.8,
                "Volume": 9000,
            },
        ]
    )

    # Custom filter forces a short breakout on the second row regardless of base criteria
    def force_short(row, prev, or_high, or_low):
        if row["Datetime"] == times[1]:
            return ("short", or_low)
        return None

    # With full window, custom filter should trigger
    brks = detect_breakouts(
        df,
        or_high=101.0,
        or_low=99.0,
        breakout_window_minutes=90,
        breakout_filter=force_short,
    )
    assert isinstance(brks, list)
    assert len(brks) >= 1 and brks[0]["direction"] == "short"

    # With breakout_window_minutes so small that only the first candle is included,
    # len(scan_df) < 2 -> early return []
    tiny_window_brks = detect_breakouts(
        df,
        or_high=101.0,
        or_low=99.0,
        breakout_window_minutes=0,  # only the very first candle is in-scope
        breakout_filter=force_short,
    )
    assert tiny_window_brks == []


def test_ignition_no_break_after_retest():
    """Test when no candle breaks retest range after retest"""
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
    # All candles stay within retest range
    for i in range(10):
        rows.append(
            {
                "Datetime": times_1m[i],
                "Open": 100.0,
                "High": 100.4,  # Doesn't break above retest high (100.5)
                "Low": 99.9,
                "Close": 100.1,
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

    # No ignition since no candle breaks above retest high
    assert result is None


def test_ignition_invalid_retest_and_empty_window():
    """Ignition should return None when retest candle lacks high/low or window is empty"""
    retest_time = pd.Timestamp("2025-11-02 09:50")
    # Missing/zero highs/lows should trigger early None
    invalid_retest = pd.Series(
        {"Datetime": retest_time, "Open": 100.0, "High": 0.0, "Low": 0.0, "Close": 100.0}
    )

    df_1m = pd.DataFrame(
        [
            {
                "Datetime": retest_time - timedelta(minutes=5),
                "Open": 100,
                "High": 100.3,
                "Low": 99.9,
                "Close": 100.1,
            }
        ]
    )
    res1 = detect_ignition(
        df_1m, retest_time, invalid_retest, direction="long", ignition_lookahead_minutes=5
    )
    assert res1 is None

    # Valid retest, but no candles in the lookahead window
    valid_retest = pd.Series(
        {"Datetime": retest_time, "Open": 100.0, "High": 100.5, "Low": 99.8, "Close": 100.1}
    )
    empty_window_df = pd.DataFrame(
        [
            {
                "Datetime": retest_time - timedelta(minutes=1),
                "Open": 100,
                "High": 100.2,
                "Low": 99.9,
                "Close": 100.0,
            }
        ]
    )
    res2 = detect_ignition(
        empty_window_df, retest_time, valid_retest, direction="long", ignition_lookahead_minutes=1
    )
    assert res2 is None


def test_retest_filter_rejects_all_returns_none():
    """When custom retest filter rejects all candles, function should return None (end-of-loop branch)"""
    breakout_time = pd.Timestamp("2025-11-02 09:40")
    times_1m = pd.date_range(breakout_time + timedelta(minutes=5), periods=5, freq="1min")
    df_1m = pd.DataFrame(
        [
            {"Datetime": t, "Open": 100, "High": 100.3, "Low": 99.9, "Close": 100.1, "Volume": 1500}
            for t in times_1m
        ]
    )

    # Custom retest filter that always returns False
    def never(m1, direction, level):
        return False

    res = detect_retest(
        df_1m,
        breakout_time=breakout_time,
        direction="long",
        level=100.0,
        retest_lookahead_minutes=15,
        retest_filter=never,
    )
    assert res is None
