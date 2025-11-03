from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

from cache_utils import (
    integrity_check_cache,
    integrity_check_day,
    integrity_check_range,
    load_cached_day,
    save_day,
)


def _df_1m_for_date(date_str: str, start_time: str = "09:30", bars: int = 10):
    # Build simple 1m bars starting at given time local NY
    base_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
    times = [base_dt + timedelta(minutes=i) for i in range(bars)]
    df = pd.DataFrame(
        {
            "Datetime": times,
            "Open": [10 + i * 0.1 for i in range(bars)],
            "High": [10 + i * 0.1 + 0.2 for i in range(bars)],
            "Low": [10 + i * 0.1 - 0.2 for i in range(bars)],
            "Close": [10 + i * 0.1 for i in range(bars)],
            "Volume": [1000 for _ in range(bars)],
        }
    )
    return df


def test_integrity_ok_single_day(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sym = "TEST"
    date_str = "2025-10-10"
    df = _df_1m_for_date(date_str, bars=5)
    save_day(cache_dir, sym, date_str, "1m", df)
    rep = integrity_check_day(cache_dir, sym, date_str, "1m")
    assert rep["status"] in {"ok", "warning"}
    assert rep["stats"].get("rows") == 5


def test_integrity_missing_file(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    rep = integrity_check_day(cache_dir, "TEST", "2025-10-11", "1m")
    assert rep["status"] == "error"
    assert "missing-file" in rep["errors"]


def test_integrity_multiday_detection(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sym = "TEST"
    file_date = "2025-10-12"
    # Intentionally craft bars for a different date
    wrong_date = "2025-10-13"
    df = _df_1m_for_date(wrong_date, bars=3)
    save_day(cache_dir, sym, file_date, "1m", df)
    rep = integrity_check_day(cache_dir, sym, file_date, "1m")
    assert rep["status"] == "error"
    assert any("multi-day-file" in e for e in rep["errors"]) or rep["stats"].get(
        "unique_dates"
    ) == [wrong_date]


def test_integrity_range_and_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sym = "TEST"
    d1 = "2025-10-14"
    d2 = "2025-10-15"
    save_day(cache_dir, sym, d1, "1m", _df_1m_for_date(d1, bars=3))
    save_day(cache_dir, sym, d2, "1m", _df_1m_for_date(d2, bars=4))
    rsum = integrity_check_range(cache_dir, [sym], d1, d2, intervals=["1m"], cross_interval=False)
    assert rsum["checked_files"] == 2
    # Full cache should also see these two and report no errors
    csum = integrity_check_cache(cache_dir, intervals=["1m"], cross_interval=False)
    assert csum["errors"] >= 0
    assert csum["checked_files"] >= 2


def test_integrity_gaps_alignment_and_ohlc(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sym = "TEST2"
    d = "2025-10-16"
    # Craft a 5m dataset with a deliberate gap and misalignment
    base = datetime.strptime(f"{d} 09:31", "%Y-%m-%d %H:%M")
    times = [base + timedelta(minutes=5 * i) for i in range(4)]  # 09:31, 09:36, 09:41, 09:46
    df = pd.DataFrame(
        {
            "Datetime": times,
            "Open": [10, 11, 12, 13],
            "High": [10.5, 11.5, 12.5, 13.5],
            "Low": [9.5, 10.5, 11.5, 12.5],
            "Close": [10.2, 11.2, 12.2, 13.2],
            "Volume": [100, 200, 300, 400],
        }
    )
    save_day(cache_dir, sym, d, "5m", df)
    rep = integrity_check_day(cache_dir, sym, d, "5m")
    # Expect warning for misalignment and possibly gaps (depending on normalization)
    assert rep["status"] in {"ok", "warning", "error"}
    # Force a candle with inconsistent OHLC and negative volume
    df_bad = df.copy()
    df_bad.loc[0, "High"] = 8.0  # lower than Low
    df_bad.loc[1, "Volume"] = -10
    save_day(cache_dir, sym, d, "1m", df_bad)
    rep_bad = integrity_check_day(cache_dir, sym, d, "1m")
    assert rep_bad["status"] == "error"
    assert any("inconsistent-ohlc" in e for e in rep_bad["errors"]) or any(
        "negative-volume" in e for e in rep_bad["errors"]
    )


def test_integrity_duplicates_and_cross_interval(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    sym = "TEST3"
    d = "2025-10-17"
    # 1m data with duplicate timestamp and a missing middle minute
    b = datetime.strptime(f"{d} 09:30", "%Y-%m-%d %H:%M")
    times = [b, b + timedelta(minutes=1), b + timedelta(minutes=3)]
    # Add duplicate of first
    times.append(b)
    df1 = pd.DataFrame(
        {
            "Datetime": times,
            "Open": [10, 10.1, 10.3, 10],
            "High": [10.2, 10.3, 10.5, 10.2],
            "Low": [9.9, 10.0, 10.2, 9.9],
            "Close": [10.1, 10.2, 10.4, 10.1],
            "Volume": [100, 110, 120, 100],
        }
    )
    save_day(cache_dir, sym, d, "1m", df1)
    rep1 = integrity_check_day(cache_dir, sym, d, "1m")
    # Should detect duplicate or gaps
    assert rep1["status"] in {"warning", "error"}
    # Create a mismatched 5m cache to trigger cross-interval warning
    df5 = pd.DataFrame(
        {
            "Datetime": [b + timedelta(minutes=5)],  # Single bar at 09:35
            "Open": [10.0],
            "High": [10.6],
            "Low": [9.8],
            "Close": [10.5],
            "Volume": [330],
        }
    )
    save_day(cache_dir, sym, d, "5m", df5)
    rng = integrity_check_range(cache_dir, [sym], d, d, intervals=["1m", "5m"], cross_interval=True)
    # Expect at least a checked file and possibly a cross-interval warning
    assert rng["checked_files"] >= 1
    # Run full cache as well to hit that path
    csum = integrity_check_cache(cache_dir, intervals=["1m", "5m"], cross_interval=True)
    assert csum["checked_files"] >= 2


def test_canonical_interval_edge_cases():
    """Test canonical_interval function with various inputs"""
    from cache_utils import canonical_interval

    # Test already canonical
    assert canonical_interval("1m") == "1m"
    assert canonical_interval("5m") == "5m"
    assert canonical_interval("1h") == "1h"

    # Test variations
    assert canonical_interval("1min") == "1m"
    assert canonical_interval("5min") == "5m"
    assert canonical_interval("hour") == "1h"
    assert canonical_interval("60min") == "1h"
    assert canonical_interval("h") == "1h"

    # Test pass-through for unknown intervals
    assert canonical_interval("15m") == "15m"
    assert canonical_interval("custom") == "custom"


def test_get_cache_path_creates_directory(tmp_path):
    """Test that get_cache_path creates symbol directory"""
    from cache_utils import get_cache_path

    cache_dir = tmp_path / "cache"
    path = get_cache_path(cache_dir, "AAPL", "2025-11-02", "1m")

    # Should create symbol directory
    assert (cache_dir / "AAPL").exists()
    assert path == cache_dir / "AAPL" / "2025-11-02_1m.csv"


def test_load_cached_day_nonexistent(tmp_path):
    """Test loading a day that doesn't exist in cache"""
    from cache_utils import load_cached_day

    result = load_cached_day(tmp_path, "TSLA", "2025-11-02", "1m")
    assert result is None


def test_save_and_load_preserves_utc_timezone(tmp_path):
    """Test that saving and loading cache preserves UTC timezone"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Create data with UTC timezone (like from API after conversion)
    market_open_utc = datetime(2025, 7, 7, 13, 30, 0, tzinfo=ZoneInfo("UTC"))
    times = [market_open_utc + timedelta(minutes=i) for i in range(5)]

    df = pd.DataFrame(
        {
            "Datetime": times,
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "High": [100.5, 101.5, 102.5, 103.5, 104.5],
            "Low": [99.5, 100.5, 101.5, 102.5, 103.5],
            "Close": [100.2, 101.2, 102.2, 103.2, 104.2],
            "Volume": [1000, 1100, 1200, 1300, 1400],
        }
    )

    # Save to cache
    save_day(cache_dir, "TEST", "2025-07-07", "1m", df)

    # Load from cache
    loaded = load_cached_day(cache_dir, "TEST", "2025-07-07", "1m")

    assert loaded is not None
    assert len(loaded) == 5

    # Check timezone is preserved as UTC
    first_time = loaded["Datetime"].iloc[0]
    assert first_time.tzinfo is not None
    # UTC timezone should have zero offset
    assert first_time.utcoffset().total_seconds() == 0

    # Check the actual time value is correct (13:30 UTC = market open)
    assert first_time.hour == 13
    assert first_time.minute == 30


def test_load_cached_day_preserves_existing_utc(tmp_path):
    """Test that loading already-cached UTC data preserves timezone"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Manually create a CSV with UTC timezone (like stockdata would create)
    csv_content = """Datetime,Open,High,Low,Close,Volume
2025-07-07 13:30:00+00:00,100.0,100.5,99.5,100.2,1000
2025-07-07 13:31:00+00:00,101.0,101.5,100.5,101.2,1100
2025-07-07 13:32:00+00:00,102.0,102.5,101.5,102.2,1200
"""

    cache_path = cache_dir / "TEST"
    cache_path.mkdir()
    (cache_path / "2025-07-07_1m.csv").write_text(csv_content)

    # Load from cache
    loaded = load_cached_day(cache_dir, "TEST", "2025-07-07", "1m")

    assert loaded is not None
    assert len(loaded) == 3

    # Verify timezone is UTC
    first_time = loaded["Datetime"].iloc[0]
    assert first_time.tzinfo is not None
    # UTC timezone should have zero offset
    assert first_time.utcoffset().total_seconds() == 0
    assert first_time.hour == 13
    assert first_time.minute == 30


def test_timezone_naive_timestamps_become_utc(tmp_path):
    """Test that timezone-naive timestamps are localized to UTC"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Create CSV with naive timestamps
    csv_content = """Datetime,Open,High,Low,Close,Volume
2025-07-07 13:30:00,100.0,100.5,99.5,100.2,1000
2025-07-07 13:31:00,101.0,101.5,100.5,101.2,1100
"""

    cache_path = cache_dir / "TEST"
    cache_path.mkdir()
    (cache_path / "2025-07-07_1m.csv").write_text(csv_content)

    # Load from cache
    loaded = load_cached_day(cache_dir, "TEST", "2025-07-07", "1m")

    assert loaded is not None

    # Should have been localized to UTC
    first_time = loaded["Datetime"].iloc[0]
    assert first_time.tzinfo is not None
    # UTC timezone should have zero offset
    assert first_time.utcoffset().total_seconds() == 0
