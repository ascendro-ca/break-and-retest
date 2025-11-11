import pandas as pd
from grading.profile_loader import load_profile
from backtest import BacktestEngine
import grading.breakout_grader as breakout_grader
import grading.retest_grader as retest_grader
import grading.ignition_grader as ignition_grader
import grading.trend_grader as trend_grader


def _build_minimal_df5():
    base = pd.Timestamp("2025-10-02 13:30:00", tz="UTC")
    rows = []
    for i in range(20):
        t = base + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "Datetime": t,
                "Open": 100 + i * 0.1,
                "High": 100 + i * 0.1 + 0.4,
                "Low": 100 + i * 0.1 - 0.4,
                "Close": 100 + i * 0.1 + 0.25,
                "Volume": 1500 + i * 5,
            }
        )
    return pd.DataFrame(rows)


def _fake_run_pipeline(**kwargs):
    df5 = kwargs.get("session_df_5m")
    # Produce one candidate with modest metrics (likely below former A threshold)
    return [
        {
            "direction": "long",
            "level": 80.0,
            "breakout_time": df5["Datetime"].iloc[3],
            "retest_time": df5["Datetime"].iloc[4],
            "breakout_candle": {
                "Open": 100.0,
                "High": 100.5,
                "Low": 99.8,
                "Close": 100.35,
                "Volume": 2200,
            },
            "retest_candle": {
                "Open": 100.30,
                "High": 100.4,
                "Low": 100.0,
                "Close": 100.32,
                "Volume": 500,
            },
            "ignition_time": df5["Datetime"].iloc[5],
            "ignition_candle": {
                "Open": 100.32,
                "High": 100.55,
                "Low": 100.25,
                "Close": 100.50,
                "Volume": 600,
            },
        }
    ]


def test_shell_profile_a_includes_signal(monkeypatch):
    df5 = _build_minimal_df5()

    def fake_scan(self, symbol, df5m, cache_dir):  # mimic _scan_continuous_data signature
        return [
            {
                "ticker": symbol,
                "direction": "long",
                "entry": 100.4,
                "stop": 100.1,
                "target": 101.0,
                "risk": 0.3,
                "level": 75.0,
                "datetime": df5["Datetime"].iloc[6],
                "retest_time": df5["Datetime"].iloc[4],
                "breakout_time_5m": df5["Datetime"].iloc[3],
                "vol_breakout_5m": 2200,
                "vol_retest_1m": 500,
                "breakout_candle": {
                    "Open": 100.0,
                    "High": 100.5,
                    "Low": 99.8,
                    "Close": 100.35,
                    "Volume": 2200,
                },
                "prev_breakout_candle": None,
                "retest_candle": {
                    "Open": 100.30,
                    "High": 100.4,
                    "Low": 100.0,
                    "Close": 100.32,
                    "Volume": 500,
                },
                "breakout_body_pct": 0.7,
                "breakout_vol_ratio": 1.2,
                "retest_vol_ratio": 0.25,
                "or_range": 0.8,
                "ignition_candle": {
                    "Open": 100.32,
                    "High": 100.55,
                    "Low": 100.25,
                    "Close": 100.50,
                    "Volume": 600,
                },
                "vol_ignition_1m": 600,
                "ignition_body_pct": 0.6,
                "ignition_vol_ratio": 1.2,
                "distance_to_target": 0.4,
            }
        ]

    monkeypatch.setattr(BacktestEngine, "_scan_continuous_data", fake_scan)
    # Disable all component filters to enforce Level 1 parity at Level 2
    monkeypatch.setattr(
        breakout_grader,
        "FILTERS",
        {"filter_breakout_pattern": False, "filter_breakout_volume": False},
    )
    monkeypatch.setattr(
        retest_grader, "FILTERS", {"filter_retest_pattern": False, "filter_retest_volume": False}
    )
    monkeypatch.setattr(
        ignition_grader,
        "FILTERS",
        {"filter_ignition_pattern": False, "filter_ignition_volume": False},
    )
    monkeypatch.setattr(
        trend_grader,
        "FILTERS",
        {
            "filter_trend_htf_stub": False,
            "filter_trend_vwap_breakout": False,
            "filter_trend_vwap_retest": False,
        },
    )
    engine = BacktestEngine(initial_capital=5000, pipeline_level=2, grading_system="profile")
    engine.grade_profile_name = "a"
    engine.grade_profile = load_profile("a")  # shell profile with only name
    result = engine.run_backtest("TEST", df5, cache_dir=df5)
    assert result.get("signals"), "Shell profile 'a' should retain signals when gating skipped"
    sig = result["signals"][0]
    assert sig.get("grade_profile") == "a"
    assert sig.get("points", {}).get("total") >= 0


def test_shell_profile_b_parity_with_a(monkeypatch):
    df5 = _build_minimal_df5()
    monkeypatch.setattr("trade_setup_pipeline.run_pipeline", _fake_run_pipeline)
    # Disable all component filters to assert parity between A and B when filters are off
    monkeypatch.setattr(
        breakout_grader,
        "FILTERS",
        {"filter_breakout_pattern": False, "filter_breakout_volume": False},
    )
    monkeypatch.setattr(
        retest_grader, "FILTERS", {"filter_retest_pattern": False, "filter_retest_volume": False}
    )
    monkeypatch.setattr(
        ignition_grader,
        "FILTERS",
        {"filter_ignition_pattern": False, "filter_ignition_volume": False},
    )
    monkeypatch.setattr(
        trend_grader,
        "FILTERS",
        {
            "filter_trend_htf_stub": False,
            "filter_trend_vwap_breakout": False,
            "filter_trend_vwap_retest": False,
        },
    )
    engine_b = BacktestEngine(initial_capital=5000, pipeline_level=2, grading_system="profile")
    engine_b.grade_profile_name = "b"
    engine_b.grade_profile = load_profile("b")
    res_b = engine_b.run_backtest("TEST", df5, cache_dir=df5)

    engine_a = BacktestEngine(initial_capital=5000, pipeline_level=2, grading_system="profile")
    engine_a.grade_profile_name = "a"
    engine_a.grade_profile = load_profile("a")
    res_a = engine_a.run_backtest("TEST", df5, cache_dir=df5)

    # Parity: both shell profiles should keep identical candidate set & trade count
    assert len(res_a.get("signals", [])) == len(res_b.get("signals", []))
    assert res_a.get("total_trades") == res_b.get("total_trades")
