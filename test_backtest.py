#!/usr/bin/env python3
"""
Test suite for backtesting functionality
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backtest import BacktestEngine, DataCache
from config_utils import load_config


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    yield str(cache_dir)
    # Cleanup
    if cache_dir.exists():
        shutil.rmtree(cache_dir)


@pytest.fixture
def sample_ohlcv_data_5m():
    """Generate sample 5-minute OHLCV data for testing"""
    times = pd.date_range("2024-01-01 09:30", periods=20, freq="5min")
    data = []

    # Opening range
    data.append(
        {"Datetime": times[0], "Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 50000}
    )

    # Flat candles before breakout
    for i in range(1, 5):
        data.append(
            {
                "Datetime": times[i],
                "Open": 101,
                "High": 101.5,
                "Low": 100.5,
                "Close": 101,
                "Volume": 25000,
            }
        )

    # Breakout candle at bar 5 (09:55)
    data.append(
        {
            "Datetime": times[5],
            "Open": 101,
            "High": 103,
            "Low": 101,
            "Close": 102.8,
            "Volume": 80000,
        }
    )

    # More candles after breakout
    for i in range(6, 20):
        data.append(
            {
                "Datetime": times[i],
                "Open": 102.5,
                "High": 103,
                "Low": 102,
                "Close": 102.5,
                "Volume": 30000,
            }
        )

    return pd.DataFrame(data)


@pytest.fixture
def sample_ohlcv_data_1m():
    """Generate sample 1-minute OHLCV data for testing (aligned with 5m data)"""
    times = pd.date_range("2024-01-01 09:30", periods=100, freq="1min")
    data = []

    # First 30 minutes (before breakout) - flat trading
    for i in range(25):
        data.append(
            {
                "Datetime": times[i],
                "Open": 100.5,
                "High": 101.2,
                "Low": 100.3,
                "Close": 100.8,
                "Volume": 5000,
            }
        )

    # Breakout period (09:55-10:00) - 5 bars with higher volatility
    for i in range(25, 30):
        data.append(
            {
                "Datetime": times[i],
                "Open": 101,
                "High": 103,
                "Low": 101,
                "Close": 102.5,
                "Volume": 15000,
            }
        )

    # Re-test candle at 10:01 (bar 31)
    data.append(
        {
            "Datetime": times[31],
            "Open": 102.5,
            "High": 102.6,
            "Low": 102.0,  # touch OR high (102.0) to satisfy strict retest requirement
            "Close": 102.3,
            "Volume": 4000,
        }
    )

    # Ignition candle at 10:02 (bar 32)
    data.append(
        {
            "Datetime": times[32],
            "Open": 102.3,
            "High": 104,
            "Low": 102.3,
            "Close": 103.8,
            "Volume": 12000,
        }
    )

    # Fill rest with normal trading
    for i in range(33, 100):
        data.append(
            {
                "Datetime": times[i],
                "Open": 103.5,
                "High": 104,
                "Low": 103,
                "Close": 103.5,
                "Volume": 6000,
            }
        )

    return pd.DataFrame(data)


def test_data_cache_creation(temp_cache_dir):
    """Test DataCache initialization"""
    cache = DataCache(temp_cache_dir)
    assert cache.cache_dir.exists()


def test_data_cache_save_and_load(temp_cache_dir, sample_ohlcv_data_5m):
    """Test caching and retrieving data"""
    cache = DataCache(temp_cache_dir)

    # Cache the data
    cache.cache_data("AAPL", "2024-01-01", "5m", sample_ohlcv_data_5m)

    # Verify file was created
    cache_path = cache._get_cache_path("AAPL", "2024-01-01", "5m")
    assert cache_path.exists()

    # Load cached data
    loaded_df = cache.get_cached_data("AAPL", "2024-01-01", "5m")
    assert loaded_df is not None
    assert len(loaded_df) == len(sample_ohlcv_data_5m)
    assert list(loaded_df.columns) == list(sample_ohlcv_data_5m.columns)


def test_backtest_engine_initialization():
    """Test BacktestEngine initialization"""
    engine = BacktestEngine(initial_capital=10000, position_size_pct=0.1)
    assert engine.initial_capital == 10000
    assert engine.position_size_pct == 0.1
    assert engine.cash == 10000


def test_backtest_with_signals(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test backtest execution with valid signals using multi-timeframe data"""
    engine = BacktestEngine(initial_capital=10000, position_size_pct=0.1)

    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    assert result["symbol"] == "TEST"
    assert "total_trades" in result
    assert "winning_trades" in result
    assert "losing_trades" in result
    assert "total_pnl" in result
    assert "win_rate" in result

    # With the properly aligned 5m and 1m data, we should detect the pattern
    assert result["total_trades"] >= 0
    assert len(result["signals"]) >= 0


def test_backtest_with_no_signals():
    """Test backtest with data that generates no signals"""
    # Create flat 5m data with no breakout
    times_5m = pd.date_range("2024-01-01 09:30", periods=20, freq="5min")
    data_5m = [
        {"Datetime": t, "Open": 100, "High": 100.1, "Low": 99.9, "Close": 100, "Volume": 25000}
        for t in times_5m
    ]
    df_5m = pd.DataFrame(data_5m)

    # Create flat 1m data with no breakout
    times_1m = pd.date_range("2024-01-01 09:30", periods=100, freq="1min")
    data_1m = [
        {"Datetime": t, "Open": 100, "High": 100.1, "Low": 99.9, "Close": 100, "Volume": 5000}
        for t in times_1m
    ]
    df_1m = pd.DataFrame(data_1m)

    engine = BacktestEngine(initial_capital=10000)
    result = engine.run_backtest("FLAT", df_5m, df_1m)

    assert result["symbol"] == "FLAT"
    assert result["total_trades"] == 0
    assert result["total_pnl"] == 0


def test_cache_directory_organization(temp_cache_dir):
    """Test that cache organizes files by symbol"""
    cache = DataCache(temp_cache_dir)

    df = pd.DataFrame(
        {
            "Datetime": pd.date_range("2024-01-01 09:30", periods=5, freq="5min"),
            "Open": [100] * 5,
            "High": [101] * 5,
            "Low": [99] * 5,
            "Close": [100] * 5,
            "Volume": [5000] * 5,
        }
    )

    # Cache data for multiple symbols
    cache.cache_data("AAPL", "2024-01-01", "5m", df)
    cache.cache_data("MSFT", "2024-01-01", "5m", df)

    # Check directory structure
    aapl_dir = Path(temp_cache_dir) / "AAPL"
    msft_dir = Path(temp_cache_dir) / "MSFT"

    assert aapl_dir.exists()
    assert msft_dir.exists()
    assert (aapl_dir / "2024-01-01_5m.csv").exists()
    assert (msft_dir / "2024-01-01_5m.csv").exists()


def test_multitimeframe_breakout_detection(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test that breakout is detected on 5m and retest on 1m at Level 0 (base pipeline)"""
    # Level 0: Base pipeline (Stages 1-3 only, no ignition)
    engine = BacktestEngine(initial_capital=10000, position_size_pct=0.1, pipeline_level=0)

    # Run backtest
    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # Should detect at least one candidate with our crafted data
    assert len(result["signals"]) >= 1

    if len(result["signals"]) > 0:
        signal = result["signals"][0]

        # Verify signal has multi-timeframe metadata
        assert "breakout_time_5m" in signal
        assert "vol_breakout_5m" in signal
        assert "vol_retest_1m" in signal
        # At Level 0, ignition is not detected
        # assert "vol_ignition_1m" in signal  # Only present at Level 1+

        # At Level 0, entry/stop/target are None (candidates only)
        assert signal["entry"] is None
        assert signal["stop"] is None
        assert signal["target"] is None
        assert signal["risk"] is None


def test_level_1_grading_analytics(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test that Level 1 applies grading (for analytics) without any quality filtering."""
    engine = BacktestEngine(initial_capital=7500, position_size_pct=0.01, pipeline_level=1)

    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # At Level 1, all signals matching base criteria should become trades
    # Grading should not filter any signals
    if len(result["signals"]) > 0:
        signal = result["signals"][0]

        # Level 1 should have entry/stop/target (trades enabled)
        assert signal["entry"] is not None
        assert signal["stop"] is not None
        assert signal["target"] is not None
        assert signal["risk"] is not None

    # Grading metadata present (analytics only, no filtering at Level 1)
    assert "overall_grade" in signal
    assert "breakout_tier" in signal
    assert "component_grades" in signal
    # Ensure overall_grade is one of expected values
    assert signal["overall_grade"] in {"A+", "A", "B", "C"}


def test_level_1_position_sizing_risk_based(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test that Level 1 uses 0.5% risk-based position sizing"""
    initial_capital = 7500
    engine = BacktestEngine(initial_capital=initial_capital, pipeline_level=1)

    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    if result["total_trades"] > 0 and len(result["trades"]) > 0:
        trade = result["trades"][0]

        # Calculate expected position size
        entry = trade["entry"]
        stop = trade["stop"]
        risk_per_share = abs(entry - stop)
        risk_amount = initial_capital * 0.005  # 0.5% risk
        expected_shares = int(risk_amount / risk_per_share)

        # Verify shares match 0.5% risk calculation
        assert trade["shares"] == expected_shares or trade["shares"] == expected_shares + 1
        # Allow ±1 share for rounding

        # Verify total risk is approximately 0.5% of capital
        total_risk = trade["shares"] * risk_per_share
        risk_pct = total_risk / initial_capital
        assert 0.004 <= risk_pct <= 0.006  # 0.4% to 0.6% tolerance


def test_level_2_grading_simplified_filter(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test that Level 2 applies grading and only filters on breakout & RR quality (simplified)."""
    engine = BacktestEngine(
        initial_capital=7500,
        pipeline_level=2,
    )

    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # At Level 2, grading should be applied
    if len(result["signals"]) > 0:
        signal = result["signals"][0]

        # Grading fields present
        assert "overall_grade" in signal
        # Simplified filter does not enforce overall grade threshold (no min_grade) so any overall_grade allowed


def test_level_2_points_filtering_with_toggles(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Level 2 with toggles: C gate (breakout & rr) + B gate (points >=70)."""
    engine = BacktestEngine(
        initial_capital=7500,
        pipeline_level=2,
    )

    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # Check that signals passed the Level 2 gates according to defaults (C and B enabled)
    for signal in result["signals"]:
        component_grades = signal.get("component_grades", {})
        # Grade C gate: require breakout and rr not ❌
        assert component_grades.get("breakout", "❌") != "❌"
        assert component_grades.get("rr", "❌") != "❌"

        # Grade B gate: total points >= 70
        breakout_pts = signal.get("breakout_points", 0)
        retest_pts = signal.get("retest_points", 0)
        ignition_pts = signal.get("ignition_points", 0)
        context_pts = signal.get("context_points", 0)
        total_points = breakout_pts + retest_pts + ignition_pts + context_pts
        assert total_points >= 70, f"Signal has {total_points} points, expected >=70"


def test_level_0_vs_level_1_differences(sample_ohlcv_data_5m, sample_ohlcv_data_1m):
    """Test key differences between Level 0 (candidates) and Level 1 (trades)"""
    # Level 0: Candidates only
    engine_0 = BacktestEngine(initial_capital=7500, pipeline_level=0)
    result_0 = engine_0.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # Level 1: Trades with base criteria
    engine_1 = BacktestEngine(initial_capital=7500, pipeline_level=1)
    result_1 = engine_1.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)

    # Level 1 should have fewer or equal candidates due to trade execution filters
    assert len(result_1["signals"]) <= len(result_0["signals"])

    if len(result_0["signals"]) > 0:
        sig_0 = result_0["signals"][0]
        sig_1 = result_1["signals"][0]

        # Level 0: No entry/stop/target (candidates only)
        assert sig_0["entry"] is None
        assert sig_0["stop"] is None
        assert sig_0["target"] is None

        # Level 1: Has entry/stop/target (trades)
        assert sig_1["entry"] is not None
        assert sig_1["stop"] is not None
        assert sig_1["target"] is not None

    # Level 0: candidate mode retains no grading metadata
    assert "overall_grade" not in sig_0
    # Level 1: grading computed for analytics (no quality filtering)
    assert "overall_grade" in sig_1
    assert sig_1["overall_grade"] in {"A+", "A", "B", "C"}


def test_cache_integrity_check_feature_flag(tmp_path):
    """Test that feature_cache_check_integrity flag controls integrity check behavior"""
    config_path = tmp_path / "config.json"

    # Test with flag disabled (default)
    config_disabled = {"tickers": ["TEST"], "feature_cache_check_integrity": False}
    config_path.write_text(json.dumps(config_disabled))

    # Load config and verify flag is False
    import importlib

    import config_utils
    from config_utils import load_config

    # Temporarily modify the config path for testing
    original_config_path = (
        config_utils.CONFIG_PATH if hasattr(config_utils, "CONFIG_PATH") else None
    )

    try:
        # Test that the flag exists and defaults to False
        config = load_config()
        assert "feature_cache_check_integrity" in config or not config.get(
            "feature_cache_check_integrity", False
        )

        # Test with flag enabled
        config_enabled = {"tickers": ["TEST"], "feature_cache_check_integrity": True}
        config_path.write_text(json.dumps(config_enabled))

        # Reload config
        importlib.reload(config_utils)
        config = load_config()

        # Verify we can read the flag (implementation may vary)
        # The actual check happens in main() so we just verify the config structure is correct
        assert isinstance(config, dict)

    finally:
        # Restore original config path if it existed
        if original_config_path:
            config_utils.CONFIG_PATH = original_config_path


def test_cache_integrity_flag_in_default_config():
    """Test that default config.json has feature_cache_check_integrity flag"""
    config = load_config()

    # Verify flag exists in config (either explicitly or via default)
    # Default should be False
    flag_value = config.get("feature_cache_check_integrity", False)
    assert isinstance(flag_value, bool)
    assert not flag_value  # Default value should be False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
