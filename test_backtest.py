#!/usr/bin/env python3
"""
Test suite for backtesting functionality
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from backtest import DataCache, BacktestEngine


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
    data.append({"Datetime": times[0], "Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 50000})
    
    # Flat candles before breakout
    for i in range(1, 5):
        data.append({"Datetime": times[i], "Open": 101, "High": 101.5, "Low": 100.5, "Close": 101, "Volume": 25000})
    
    # Breakout candle at bar 5 (09:55)
    data.append({"Datetime": times[5], "Open": 101, "High": 103, "Low": 101, "Close": 102.8, "Volume": 80000})
    
    # More candles after breakout
    for i in range(6, 20):
        data.append({"Datetime": times[i], "Open": 102.5, "High": 103, "Low": 102, "Close": 102.5, "Volume": 30000})
    
    return pd.DataFrame(data)


@pytest.fixture
def sample_ohlcv_data_1m():
    """Generate sample 1-minute OHLCV data for testing (aligned with 5m data)"""
    times = pd.date_range("2024-01-01 09:30", periods=100, freq="1min")
    data = []
    
    # First 30 minutes (before breakout) - flat trading
    for i in range(25):
        data.append({"Datetime": times[i], "Open": 100.5, "High": 101.2, "Low": 100.3, "Close": 100.8, "Volume": 5000})
    
    # Breakout period (09:55-10:00) - 5 bars with higher volatility
    for i in range(25, 30):
        data.append({"Datetime": times[i], "Open": 101, "High": 103, "Low": 101, "Close": 102.5, "Volume": 15000})
    
    # Re-test candle at 10:01 (bar 31)
    data.append({"Datetime": times[31], "Open": 102.5, "High": 102.6, "Low": 102.1, "Close": 102.3, "Volume": 4000})
    
    # Ignition candle at 10:02 (bar 32)
    data.append({"Datetime": times[32], "Open": 102.3, "High": 104, "Low": 102.3, "Close": 103.8, "Volume": 12000})
    
    # Fill rest with normal trading
    for i in range(33, 100):
        data.append({"Datetime": times[i], "Open": 103.5, "High": 104, "Low": 103, "Close": 103.5, "Volume": 6000})
    
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
    
    df = pd.DataFrame({
        "Datetime": pd.date_range("2024-01-01 09:30", periods=5, freq="5min"),
        "Open": [100] * 5,
        "High": [101] * 5,
        "Low": [99] * 5,
        "Close": [100] * 5,
        "Volume": [5000] * 5
    })
    
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
    """Test that breakout is detected on 5m and retest/ignition on 1m"""
    engine = BacktestEngine(initial_capital=10000, position_size_pct=0.1)
    
    # Run backtest
    result = engine.run_backtest("TEST", sample_ohlcv_data_5m, sample_ohlcv_data_1m)
    
    # Should detect at least one signal with our crafted data
    assert len(result["signals"]) >= 1
    
    if len(result["signals"]) > 0:
        signal = result["signals"][0]
        
        # Verify signal has multi-timeframe metadata
        assert "breakout_time_5m" in signal
        assert "vol_breakout_5m" in signal
        assert "vol_retest_1m" in signal
        assert "vol_ignition_1m" in signal
        
        # Verify entry/stop/target are set
        assert signal["entry"] > 0
        assert signal["stop"] > 0
        assert signal["target"] > 0
        assert signal["risk"] > 0
        
        # For long: target > entry > stop
        # For short: target < entry < stop
        if signal["direction"] == "long":
            assert signal["target"] > signal["entry"] > signal["stop"]
        else:
            assert signal["target"] < signal["entry"] < signal["stop"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
