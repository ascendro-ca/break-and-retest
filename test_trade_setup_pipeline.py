from datetime import timedelta

import pandas as pd

from trade_setup_pipeline import run_pipeline


def _make_session_5m():
    # 5m bars starting at 09:30 local (naive timestamps acceptable for unit tests)
    times = pd.date_range("2025-10-31 09:30", periods=8, freq="5min")
    rows = []
    # OR candle 09:30-09:35
    rows.append(
        {
            "Datetime": times[0],
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 10000,
        }
    )
    # Pre-breakout quiet bar
    rows.append(
        {
            "Datetime": times[1],
            "Open": 100.4,
            "High": 100.6,
            "Low": 100.2,
            "Close": 100.5,
            "Volume": 9000,
        }
    )
    # Breakout up bar beyond OR high, with decent volume
    rows.append(
        {
            "Datetime": times[2],
            "Open": 100.5,
            "High": 101.6,
            "Low": 100.5,
            "Close": 101.5,
            "Volume": 30000,
        }
    )
    # A few follow-on bars
    for i in range(3, 8):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 101.3,
                "High": 101.7,
                "Low": 101.1,
                "Close": 101.4,
                "Volume": 15000 - (i - 3) * 500,
            }
        )
    df = pd.DataFrame(rows)
    return df


def _make_session_1m(breakout_time: pd.Timestamp, or_high: float):
    # Create 1m bars covering at least until a valid retest after breakout close
    start = pd.Timestamp("2025-10-31 09:30")
    times = pd.date_range(start, periods=60, freq="1min")
    rows = []
    # Initial flat area
    for i in range(0, 10):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 100.4,
                "High": 100.8,
                "Low": 100.2,
                "Close": 100.6,
                "Volume": 2000,
            }
        )

    # Ensure we have bars until after breakout close (breakout_time + 5min)
    t = rows[-1]["Datetime"] + timedelta(minutes=1)
    while t < breakout_time + timedelta(minutes=5):
        rows.append(
            {
                "Datetime": t,
                "Open": 101.0,
                "High": 101.2,
                "Low": 100.9,
                "Close": 101.1,
                "Volume": 1800,
            }
        )
        t += timedelta(minutes=1)

    # First valid retest strictly after breakout close
    retest_time = breakout_time + timedelta(minutes=6)
    rows.append(
        {
            "Datetime": retest_time,
            "Open": or_high,
            "High": or_high + 0.4,
            "Low": or_high - 0.1,
            "Close": or_high + 0.05,  # close on/above level for long
            "Volume": 1200,
        }
    )

    df = pd.DataFrame(rows).drop_duplicates(subset=["Datetime"]).sort_values("Datetime")
    df = df.reset_index(drop=True)
    return df


def test_minimal_stage_candidates_long_breakout_and_retest():
    df5 = _make_session_5m()
    or_high = float(df5.iloc[0]["High"])  # 101.0
    breakout_time = df5.iloc[2]["Datetime"]
    df1 = _make_session_1m(breakout_time, or_high)

    # Run pipeline at Level 0 (base 3-stage mode, no ignition)
    cands = run_pipeline(
        df5, df1, breakout_window_minutes=90, retest_lookahead_minutes=30, pipeline_level=0
    )

    assert isinstance(cands, list)
    assert len(cands) == 1
    c = cands[0]
    assert c["direction"] == "long"
    assert abs(float(c["level"]) - or_high) < 1e-9
    # Retest strictly after breakout close (+5 minutes)
    retest_dt = pd.to_datetime(c["retest_time"])  # type: ignore
    assert retest_dt >= breakout_time + timedelta(minutes=5)


def test_full_4stage_pipeline_with_ignition():
    """Test the full 4-stage pipeline at Level 2 including ignition detection"""
    df5 = _make_session_5m()
    or_high = float(df5.iloc[0]["High"])  # 101.0
    breakout_time = df5.iloc[2]["Datetime"]

    # Build 1m data with an ignition candle after retest
    start = pd.Timestamp("2025-10-31 09:30")
    times = pd.date_range(start, periods=60, freq="1min")
    rows = []
    # Initial flat area
    for i in range(0, 10):
        rows.append(
            {
                "Datetime": times[i],
                "Open": 100.4,
                "High": 100.8,
                "Low": 100.2,
                "Close": 100.6,
                "Volume": 2000,
            }
        )

    # Bars until after breakout close
    t = rows[-1]["Datetime"] + timedelta(minutes=1)
    while t < breakout_time + timedelta(minutes=5):
        rows.append(
            {
                "Datetime": t,
                "Open": 101.0,
                "High": 101.2,
                "Low": 100.9,
                "Close": 101.1,
                "Volume": 1800,
            }
        )
        t += timedelta(minutes=1)

    # Retest after breakout close
    retest_time = breakout_time + timedelta(minutes=6)
    rows.append(
        {
            "Datetime": retest_time,
            "Open": or_high,
            "High": or_high + 0.4,
            "Low": or_high - 0.1,
            "Close": or_high + 0.05,
            "Volume": 1200,
        }
    )

    # Ignition candle right after retest
    ignition_time = retest_time + timedelta(minutes=1)
    rows.append(
        {
            "Datetime": ignition_time,
            "Open": or_high + 0.1,
            "High": or_high + 1.0,  # Breaks above retest high
            "Low": or_high,
            "Close": or_high + 0.8,
            "Volume": 3000,
        }
    )

    df1 = pd.DataFrame(rows).drop_duplicates(subset=["Datetime"]).sort_values("Datetime")
    df1 = df1.reset_index(drop=True)

    # Run pipeline at Level 2 (includes Stage 4: Ignition detection)
    cands = run_pipeline(
        df5, df1, breakout_window_minutes=90, retest_lookahead_minutes=30, pipeline_level=2
    )

    assert isinstance(cands, list)
    assert len(cands) == 1
    c = cands[0]
    assert c["direction"] == "long"
    assert "ignition_time" in c
    assert "ignition_candle" in c
    ign_dt = pd.to_datetime(c["ignition_time"])
    assert ign_dt >= pd.to_datetime(c["retest_time"]) + timedelta(minutes=1)


def test_pipeline_edge_case_none_inputs():
    """Test pipeline handles None inputs gracefully"""
    from trade_setup_pipeline import run_pipeline

    # None for 5m data
    result = run_pipeline(None, pd.DataFrame(), pipeline_level=0)
    assert result == []

    # None for 1m data
    result = run_pipeline(pd.DataFrame(), None, pipeline_level=0)
    assert result == []

    # Both None
    result = run_pipeline(None, None, pipeline_level=0)
    assert result == []


def test_pipeline_edge_case_empty_dataframes():
    """Test pipeline handles empty DataFrames gracefully"""
    from trade_setup_pipeline import run_pipeline

    df5_empty = pd.DataFrame(columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df1_empty = pd.DataFrame(columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])

    # Empty 5m
    result = run_pipeline(
        df5_empty, _make_session_1m(pd.Timestamp("2025-10-31 09:40"), 101.0), pipeline_level=0
    )
    assert result == []

    # Empty 1m
    result = run_pipeline(_make_session_5m(), df1_empty, pipeline_level=0)
    assert result == []

    # Both empty
    result = run_pipeline(df5_empty, df1_empty, pipeline_level=0)
    assert result == []


def test_pipeline_no_opening_range():
    """Test pipeline returns empty when opening range is invalid (zero high/low)"""
    from trade_setup_pipeline import run_pipeline

    # Create 5m data with invalid opening range (all zeros)
    times = pd.date_range("2025-10-31 09:30", periods=5, freq="5min")
    rows = [
        {"Datetime": t, "Open": 0.0, "High": 0.0, "Low": 0.0, "Close": 0.0, "Volume": 0}
        for t in times
    ]
    df5 = pd.DataFrame(rows)
    df1 = _make_session_1m(times[2], 0.0)

    result = run_pipeline(df5, df1, pipeline_level=0)
    assert result == []


def test_pipeline_no_breakouts_returns_empty():
    """Pipeline should return [] when Stage 2 finds no breakouts"""
    # Construct 5m data that never breaks the OR
    times = pd.date_range("2025-10-31 09:30", periods=8, freq="5min")
    rows5 = [
        {
            "Datetime": times[0],
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 10000,
        }
    ]
    for i in range(1, 8):
        rows5.append(
            {
                "Datetime": times[i],
                "Open": 100.2,
                "High": 100.8,  # stays within OR
                "Low": 99.2,
                "Close": 100.4,
                "Volume": 9000,
            }
        )
    df5 = pd.DataFrame(rows5)

    # 1m data present but irrelevant since no breakouts
    df1 = _make_session_1m(times[2], or_high=float(df5.iloc[0]["High"]))

    result = run_pipeline(df5, df1, pipeline_level=0)
    assert result == []
