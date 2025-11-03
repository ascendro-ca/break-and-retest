import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

# Add the project root to the Python path if not already there
project_root = str(Path(__file__).parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from break_and_retest_detection_mt import is_strong_body
from break_and_retest_strategy import scan_ticker
from visualize_test_results import create_chart


# --- Helper to simulate realistic 5-min OHLCV data ---
def make_test_df():
    # Simulate 20 candles, market open at 09:30
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    # First candle: opening range
    data = [
        {
            "Datetime": times[0],
            "Open": 100,
            "High": 102,
            "Low": 99.5,
            "Close": 101.8,
            "Volume": 8000,
        },
        # Flat candles
        {
            "Datetime": times[1],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        {
            "Datetime": times[2],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        # Breakout candle (up) - strong body, very high volume
        {
            "Datetime": times[3],
            "Open": 101.8,
            "High": 102.5,
            "Low": 101.8,
            "Close": 102.5,
            "Volume": 20000,
        },
        # Re-test candle (returns to high, tight, lower vol)
        {
            "Datetime": times[4],
            "Open": 102.2,
            "High": 102.3,
            "Low": 102.0,
            "Close": 102.3,
            "Volume": 10000,
        },
        # Ignition candle (strong body, breaks re-test high, vol up)
        {
            "Datetime": times[5],
            "Open": 102.3,
            "High": 103.0,
            "Low": 102.3,
            "Close": 102.95,
            "Volume": 13000,
        },
    ]
    # Fill rest with flat candles
    for i in range(6, 20):
        data.append(
            {
                "Datetime": times[i],
                "Open": 102.95,
                "High": 103.0,
                "Low": 102.9,
                "Close": 102.95,
                "Volume": 9000,
            }
        )
    df = pd.DataFrame(data)
    return df


# --- Patch scan_ticker to accept a DataFrame for testing ---
from break_and_retest_strategy import scan_ticker as orig_scan_ticker


def scan_ticker_test(df):
    # Match main script: restrict to first 90 min after open
    # Use exact detection loop from main script
    scan_df = df.copy()
    if len(scan_df) < 10:
        return []
    or_high = scan_df.iloc[0]["High"]
    or_low = scan_df.iloc[0]["Low"]
    scan_df["vol_ma"] = scan_df["Volume"].rolling(window=10, min_periods=1).mean()
    signals = []
    lvl_high = or_high
    lvl_low = or_low
    for i in range(1, len(scan_df) - 2):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i - 1]
        breakout_up = (
            prev["High"] <= lvl_high
            and row["High"] > lvl_high
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * 1.2
            and row["Close"] > lvl_high
        )
        breakout_down = (
            prev["Low"] >= lvl_low
            and row["Low"] < lvl_low
            and is_strong_body(row)
            and row["Volume"] > row["vol_ma"] * 1.2
            and row["Close"] < lvl_low
        )
        # debug prints removed for clean test output
        if breakout_up or breakout_down:
            re_test_idx = i + 1
            if re_test_idx >= len(scan_df):
                continue
            re_test = scan_df.iloc[re_test_idx]
            returns_to_level = (breakout_up and abs(re_test["Low"] - lvl_high) <= 0.1) or (
                breakout_down and abs(re_test["High"] - lvl_low) <= 0.1
            )
            tight_candle = re_test["High"] - re_test["Low"] < 0.5 * (row["High"] - row["Low"])
            lower_vol = re_test["Volume"] < row["Volume"]
            # debug prints removed for clean test output
            if returns_to_level and tight_candle and lower_vol:
                ign_idx = i + 2
                if ign_idx >= len(scan_df):
                    continue
                ign = scan_df.iloc[ign_idx]
                ignition = (
                    is_strong_body(ign)
                    and (
                        (breakout_up and ign["High"] > re_test["High"])
                        or (breakout_down and ign["Low"] < re_test["Low"])
                    )
                    and ign["Volume"] > re_test["Volume"]
                )
                # debug prints removed for clean test output
                if ignition:
                    entry = ign["High"] if breakout_up else ign["Low"]
                    stop = re_test["Low"] - 0.05 if breakout_up else re_test["High"] + 0.05
                    risk = abs(entry - stop)
                    target = entry + 2 * risk if breakout_up else entry - 2 * risk
                    signals.append(
                        {
                            "datetime": ign["Datetime"],
                            "direction": "long" if breakout_up else "short",
                            "entry": entry,
                            "stop": stop,
                            "target": target,
                            "risk": risk,
                            "vol_breakout": row["Volume"],
                            "vol_retest": re_test["Volume"],
                            "vol_ignition": ign["Volume"],
                        }
                    )
    return signals


# --- Long break and re-test setup ---
def save_test_visualization(test_name, df, signals):
    """Save an HTML visualization of test results"""
    # Create logs dir if needed
    os.makedirs("logs", exist_ok=True)

    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = f"logs/{test_name}_{timestamp}.html"

    # Create and save chart with custom title
    create_chart(df, signals, html_path, title=f"Test Case: {test_name}")


def test_long_break_and_retest_detects_valid_setup():
    df = make_test_df()
    signals = scan_ticker_test(df)
    assert len(signals) == 1, "Should detect one valid long setup"
    sig = signals[0]
    assert sig["direction"] == "long"
    assert sig["entry"] > df.iloc[0]["High"]
    assert sig["stop"] < sig["entry"]
    assert sig["target"] > sig["entry"]
    assert sig["vol_breakout"] > sig["vol_retest"]
    assert sig["vol_ignition"] > sig["vol_retest"]

    # Save visualization if SHOW_TEST env var is set
    save_test_visualization("test_long_valid", df, signals)


# --- Short break and re-test setup ---
def make_test_df_short():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {
            "Datetime": times[0],
            "Open": 100,
            "High": 102,
            "Low": 99.0,
            "Close": 101.8,
            "Volume": 8000,
        },
        {
            "Datetime": times[1],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        {
            "Datetime": times[2],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        # Breakout candle (down) - strong body, very high volume
        {
            "Datetime": times[3],
            "Open": 99.6,
            "High": 99.7,
            "Low": 98.9,
            "Close": 98.9,
            "Volume": 20000,
        },
        # Re-test candle (returns to low, tight, lower vol)
        {
            "Datetime": times[4],
            "Open": 99.2,
            "High": 99.0,
            "Low": 99.0,
            "Close": 99.0,
            "Volume": 10000,
        },
        # Ignition candle (strong body, breaks re-test low, vol up)
        {
            "Datetime": times[5],
            "Open": 99.1,
            "High": 99.2,
            "Low": 98.5,
            "Close": 98.6,
            "Volume": 13000,
        },
    ]
    for i in range(6, 20):
        data.append(
            {
                "Datetime": times[i],
                "Open": 98.6,
                "High": 99.0,
                "Low": 98.5,
                "Close": 98.6,
                "Volume": 9000,
            }
        )
    df = pd.DataFrame(data)
    return df


def test_short_break_and_retest_detects_valid_setup():
    df = make_test_df_short()
    signals = scan_ticker_test(df)
    assert len(signals) == 1, "Should detect one valid short setup"
    sig = signals[0]
    assert sig["direction"] == "short"
    assert sig["entry"] < df.iloc[0]["Low"]
    assert sig["stop"] > sig["entry"]
    assert sig["target"] < sig["entry"]
    assert sig["vol_breakout"] > sig["vol_retest"]
    assert sig["vol_ignition"] > sig["vol_retest"]

    # Save visualization if SHOW_TEST env var is set
    save_test_visualization("test_short_valid", df, signals)


# --- Long break and re-test failure setup ---
def make_test_df_long_fail():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {
            "Datetime": times[0],
            "Open": 100,
            "High": 102,
            "Low": 99.5,
            "Close": 101.8,
            "Volume": 8000,
        },
        {
            "Datetime": times[1],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        {
            "Datetime": times[2],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        # Breakout candle (up) - strong body, very high volume
        {
            "Datetime": times[3],
            "Open": 101.8,
            "High": 102.5,
            "Low": 101.8,
            "Close": 102.5,
            "Volume": 20000,
        },
        # Re-test candle (returns to high, but NOT tight candle)
        {
            "Datetime": times[4],
            "Open": 102.2,
            "High": 103.0,
            "Low": 102.0,
            "Close": 102.3,
            "Volume": 10000,
        },
        # Ignition candle (strong body, breaks re-test high, vol up)
        {
            "Datetime": times[5],
            "Open": 102.3,
            "High": 103.0,
            "Low": 102.3,
            "Close": 102.95,
            "Volume": 13000,
        },
    ]
    for i in range(6, 20):
        data.append(
            {
                "Datetime": times[i],
                "Open": 102.95,
                "High": 103.0,
                "Low": 102.9,
                "Close": 102.95,
                "Volume": 9000,
            }
        )
    df = pd.DataFrame(data)
    return df


def test_long_break_and_retest_failure_setup():
    df = make_test_df_long_fail()
    signals = scan_ticker_test(df)
    assert len(signals) == 0, "Should NOT detect long setup due to failed tight candle"

    # Save visualization if SHOW_TEST env var is set
    save_test_visualization("test_long_fail", df, signals)


# --- Short break and re-test failure setup ---
def make_test_df_short_fail():
    times = pd.date_range("2025-10-31 09:30", periods=20, freq="5min")
    data = [
        {
            "Datetime": times[0],
            "Open": 100,
            "High": 102,
            "Low": 99.5,
            "Close": 101.8,
            "Volume": 8000,
        },
        {
            "Datetime": times[1],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        {
            "Datetime": times[2],
            "Open": 101.8,
            "High": 101.9,
            "Low": 101.7,
            "Close": 101.8,
            "Volume": 7000,
        },
        # Breakout candle (down) - strong body, very high volume
        {
            "Datetime": times[3],
            "Open": 99.6,
            "High": 99.7,
            "Low": 99.0,
            "Close": 99.0,
            "Volume": 20000,
        },
        # Re-test candle (returns to low, but NOT tight candle)
        {
            "Datetime": times[4],
            "Open": 99.2,
            "High": 99.7,
            "Low": 99.0,
            "Close": 99.1,
            "Volume": 10000,
        },
        # Ignition candle (strong body, breaks re-test low, vol up)
        {
            "Datetime": times[5],
            "Open": 99.1,
            "High": 99.2,
            "Low": 98.5,
            "Close": 98.6,
            "Volume": 13000,
        },
    ]
    for i in range(6, 20):
        data.append(
            {
                "Datetime": times[i],
                "Open": 98.6,
                "High": 99.0,
                "Low": 98.5,
                "Close": 98.6,
                "Volume": 9000,
            }
        )
    df = pd.DataFrame(data)
    return df


def test_short_break_and_retest_failure_setup():
    df = make_test_df_short_fail()
    signals = scan_ticker_test(df)
    assert len(signals) == 0, "Should NOT detect short setup due to failed tight candle"

    # Save visualization if SHOW_TEST env var is set
    save_test_visualization("test_short_fail", df, signals)
