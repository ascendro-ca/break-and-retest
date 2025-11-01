from datetime import timedelta

import pandas as pd

from break_and_retest_detection_mt import scan_for_setups


def _make_5m_data():
    # 5m bars starting 09:30
    times = pd.date_range("2025-10-31 09:30", periods=6, freq="5min")
    rows = []
    # OR candle 09:30-09:35
    rows.append({
        "Datetime": times[0],
        "Open": 100.0,
        "High": 101.0,
        "Low": 99.0,
        "Close": 100.5,
        "Volume": 10000,
    })
    # Pre-breakout flat candle; next bar will be breakout
    rows.append({
        "Datetime": times[1],
        "Open": 100.4,
        "High": 100.6,
        "Low": 100.2,
        "Close": 100.5,
        "Volume": 9000,
    })
    # Breakout up candle: use times[2] as breakout for simplicity
    rows.append({
        "Datetime": times[2],
        "Open": 100.5,
        "High": 101.5,
        "Low": 100.5,
        "Close": 101.5,
        "Volume": 30000,
    })
    # Post-breakout bars
    rows.append({
        "Datetime": times[3],
        "Open": 101.3,
        "High": 101.6,
        "Low": 101.0,
        "Close": 101.4,
        "Volume": 15000,
    })
    rows.append({
        "Datetime": times[4],
        "Open": 101.4,
        "High": 101.8,
        "Low": 101.2,
        "Close": 101.6,
        "Volume": 14000,
    })
    rows.append({
        "Datetime": times[5],
        "Open": 101.6,
        "High": 101.9,
        "Low": 101.4,
        "Close": 101.7,
        "Volume": 13000,
    })
    df = pd.DataFrame(rows)
    # vol_ma required by breakout detector
    df["vol_ma"] = df["Volume"].rolling(window=3, min_periods=1).mean()
    return df


def _make_1m_data(breakout_start: pd.Timestamp):
    # 1m bars covering 09:30-10:00
    times = pd.date_range("2025-10-31 09:30", periods=40, freq="1min")
    rows = []
    # or_high not needed directly here (comes from 5m)
    # Flat pre-breakout
    for i in range(0, 10):
        rows.append({
            "Datetime": times[i],
            "Open": 100.4,
            "High": 100.8,
            "Low": 100.2,
            "Close": 100.6,
            "Volume": 2000,
        })
    # During breakout window (within 5 minutes of breakout): include an ignored retest
    touch_during = breakout_start + timedelta(minutes=3)
    rows.append({
        "Datetime": touch_during,
        "Open": 101.2,
        "High": 101.3,
        "Low": 101.0,  # touches OR high
        "Close": 101.05,  # holds above
        "Volume": 1500,
    })
    # Fill remaining minutes until after breakout close (we'll ensure continuity)
    # Add some neutral bars up to just after breakout close
    t = times[len(rows)] if len(rows) < len(times) else touch_during + timedelta(minutes=1)
    while t < breakout_start + timedelta(minutes=5):
        rows.append({
            "Datetime": t,
            "Open": 101.1,
            "High": 101.3,
            "Low": 101.05,
            "Close": 101.2,
            "Volume": 1800,
        })
        t += timedelta(minutes=1)
    # First valid retest AFTER breakout close
    retest_time = breakout_start + timedelta(minutes=6)
    rows.append({
        "Datetime": retest_time,
        "Open": 101.3,
        "High": 101.35,
        "Low": 101.0,  # touches/pierces level
        "Close": 101.15,  # closes on correct side (>= level - 1 tick)
        "Volume": 1200,
    })
    # Ignition next minute breaking retest high
    ignition_time = retest_time + timedelta(minutes=1)
    rows.append({
        "Datetime": ignition_time,
        "Open": 101.15,
        "High": 101.60,  # breaks above retest high 101.35
        "Low": 101.12,
        "Close": 101.55,
        "Volume": 3000,
    })
    # Finalize 1m DF with unique/sorted timestamps
    df = pd.DataFrame(rows).drop_duplicates(subset=["Datetime"]).sort_values("Datetime")
    df = df.reset_index(drop=True)
    return df


def test_retest_starts_after_breakout_close():
    df5 = _make_5m_data()
    or_high = df5.iloc[0]["High"]
    or_low = df5.iloc[0]["Low"]

    # Breakout candle is at index 2 in our construction
    breakout_start = df5.iloc[2]["Datetime"]
    df1 = _make_1m_data(breakout_start)

    setups = scan_for_setups(
        df_5m=df5,
        df_1m=df1,
        or_high=or_high,
        or_low=or_low,
        vol_threshold=1.0,
    )

    # We expect exactly one setup detected, using the AFTER-close retest
    assert isinstance(setups, list)
    assert len(setups) >= 1
    setup = setups[0]
    retest_dt = pd.to_datetime(setup["retest"]["Datetime"])  # type: ignore
    ignition_dt = pd.to_datetime(setup["ignition"]["Datetime"])  # type: ignore
    # Retest must be >= breakout_start + 5 minutes
    assert retest_dt >= breakout_start + timedelta(minutes=5)
    # Ignition is the very next minute
    assert ignition_dt == retest_dt + timedelta(minutes=1)
