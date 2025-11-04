"""
Unit tests specifically for retest_qualifies_as_ignition function in stage_ignition module.
"""

import pandas as pd
import pytest

from stage_ignition import retest_qualifies_as_ignition


# Helper to create a breakout candle (required but not used in logic)
def create_breakout_candle():
    return pd.Series(
        {
            "Open": 99.0,
            "High": 100.5,
            "Low": 98.5,
            "Close": 100.0,
            "Volume": 4000,
        }
    )


def test_retest_qualifies_as_ignition_long_perfect():
    """Test long retest that qualifies as ignition - strong body, good directionality, good volume"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.8,
            "Close": 101.8,  # Close near high, strong bullish
            "Volume": 5000,
        }
    )

    # Session data with lower median volume
    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame([{"Datetime": t, "Volume": 3000} for t in session_times])

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is True


def test_retest_qualifies_as_ignition_long_weak_body():
    """Test long retest with weak body percentage - should not qualify"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.5,
            "Close": 100.5,  # Small body relative to range
            "Volume": 5000,
        }
    )

    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame([{"Datetime": t, "Volume": 3000} for t in session_times])

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is False


def test_retest_qualifies_as_ignition_long_wrong_directionality():
    """Test long retest where close is in lower half - should not qualify"""
    retest_candle = pd.Series(
        {
            "Open": 101.0,
            "High": 102.0,
            "Low": 99.0,
            "Close": 99.5,  # Close in lower half for supposed long
            "Volume": 5000,
        }
    )

    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame([{"Datetime": t, "Volume": 3000} for t in session_times])

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is False


def test_retest_qualifies_as_ignition_long_low_volume():
    """Test long retest with volume below session median - should not qualify"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.8,
            "Close": 101.8,
            "Volume": 2000,  # Below session median
        }
    )

    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame(
        [
            {"Datetime": t, "Volume": 5000}  # Higher median
            for t in session_times
        ]
    )

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is False


def test_retest_qualifies_as_ignition_short_perfect():
    """Test short retest that qualifies as ignition"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 100.2,
            "Low": 98.0,
            "Close": 98.2,  # Close near low, strong bearish
            "Volume": 5000,
        }
    )

    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame([{"Datetime": t, "Volume": 3000} for t in session_times])

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="short",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is True


def test_retest_qualifies_as_ignition_short_wrong_directionality():
    """Test short retest where close is in upper half - should not qualify"""
    retest_candle = pd.Series(
        {
            "Open": 99.0,
            "High": 101.0,
            "Low": 98.0,
            "Close": 100.5,  # Close in upper half for supposed short
            "Volume": 5000,
        }
    )

    session_times = pd.date_range("2025-11-02 09:30", periods=10, freq="1min")
    session_df = pd.DataFrame([{"Datetime": t, "Volume": 3000} for t in session_times])

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="short",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is False


def test_retest_qualifies_as_ignition_no_session_data():
    """Test retest qualification without session data - should still work based on body/direction"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.8,
            "Close": 101.8,
            "Volume": 5000,
        }
    )

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=None,
    )

    assert result is True


def test_retest_qualifies_as_ignition_empty_session_data():
    """Test retest qualification with empty session DataFrame"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.8,
            "Close": 101.8,
            "Volume": 5000,
        }
    )

    session_df = pd.DataFrame()

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=session_df,
    )

    assert result is True


def test_retest_qualifies_as_ignition_zero_range():
    """Test retest with zero range - should handle gracefully"""
    retest_candle = pd.Series(
        {
            "Open": 100.0,
            "High": 100.0,
            "Low": 100.0,
            "Close": 100.0,
            "Volume": 5000,
        }
    )

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=None,
    )

    # With zero range, body_pct will be 0, which is < 0.60
    assert result is False


def test_retest_qualifies_as_ignition_exception_handling():
    """Test that exceptions are handled gracefully"""
    # Invalid retest candle that might cause exceptions
    retest_candle = pd.Series(
        {
            "Open": None,
            "High": None,
            "Low": None,
            "Close": None,
            "Volume": None,
        }
    )

    result = retest_qualifies_as_ignition(
        retest_candle=retest_candle,
        direction="long",
        breakout_candle=create_breakout_candle(),
        session_df_1m=None,
    )

    # Should return False on exception
    assert result is False
