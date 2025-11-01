import pandas as pd
import pytest

# ruff: noqa: E501

# Deprecated: single-timeframe (5m-only) path removed. Disable this test module.
pytest.skip("Deprecated single-timeframe path; tests disabled.", allow_module_level=True)

from break_and_retest_detection import (
    detect_retest_and_ignition_5m,
    is_strong_body,
)


def test_is_strong_body_threshold():
    row = {"Open": 100.0, "Close": 101.2, "High": 101.5, "Low": 100.0}
    assert is_strong_body(row) is True
    row2 = {"Open": 100.0, "Close": 100.3, "High": 101.0, "Low": 100.0}
    assert is_strong_body(row2) is False


def test_detect_retest_and_ignition_5m_happy_path():
    # Build minimal 5m DataFrame: breakout at idx 1, retest at 2, ignition at 3
    rows = []
    times = pd.date_range("2025-10-31 09:30", periods=6, freq="5min")
    # OR candle
    rows.append({"Datetime": times[0], "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 10000})
    # Breakout candle (strong body up)
    rows.append({"Datetime": times[1], "Open": 100.6, "High": 102.0, "Low": 100.6, "Close": 101.9, "Volume": 25000})
    # Retest tight candle lower vol, touches or below level 101.0
    rows.append({"Datetime": times[2], "Open": 101.6, "High": 101.6, "Low": 100.95, "Close": 101.3, "Volume": 12000})
    # Ignition strong body, breaks retest high and higher volume
    rows.append({"Datetime": times[3], "Open": 101.2, "High": 102.2, "Low": 101.1, "Close": 102.0, "Volume": 20000})
    # Padding
    rows.append({"Datetime": times[4], "Open": 102.0, "High": 102.2, "Low": 101.8, "Close": 102.1, "Volume": 15000})
    rows.append({"Datetime": times[5], "Open": 102.1, "High": 102.3, "Low": 102.0, "Close": 102.2, "Volume": 14000})

    df5 = pd.DataFrame(rows)

    breakout_idx = 1
    breakout_candle = df5.iloc[breakout_idx]
    breakout_level = 101.0
    direction = "long"

    pattern = detect_retest_and_ignition_5m(
        df5,
        breakout_idx,
        breakout_candle,
        breakout_level,
        direction,
    )

    assert pattern is not None
    assert pattern["retest_index"] == breakout_idx + 1
    assert pattern["ignition_index"] == breakout_idx + 2


def test_detect_retest_and_ignition_5m_no_retest():
    # Breakout followed by non-touch retest should return None
    rows = []
    times = pd.date_range("2025-10-31 09:30", periods=4, freq="5min")
    rows.append({"Datetime": times[0], "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 10000})
    rows.append({"Datetime": times[1], "Open": 100.6, "High": 102.0, "Low": 100.6, "Close": 101.9, "Volume": 25000})
    rows.append({"Datetime": times[2], "Open": 101.7, "High": 101.8, "Low": 101.2, "Close": 101.3, "Volume": 12000})  # no touch
    rows.append({"Datetime": times[3], "Open": 101.3, "High": 102.2, "Low": 101.1, "Close": 102.0, "Volume": 20000})

    df5 = pd.DataFrame(rows)
    breakout_idx = 1
    breakout_candle = df5.iloc[breakout_idx]
    breakout_level = 101.0
    direction = "long"

    pattern = detect_retest_and_ignition_5m(
        df5,
        breakout_idx,
        breakout_candle,
        breakout_level,
        direction,
    )

    assert pattern is None
