import pandas as pd
from backtest import BacktestEngine


def build_dummy_data():
    # Minimal 5m dataframe with required columns
    rows = []
    base_time = pd.Timestamp("2025-10-01 13:30:00", tz="UTC")
    for i in range(30):
        t = base_time + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "Datetime": t,
                "Open": 100 + i * 0.2,
                "High": 100 + i * 0.2 + 0.5,
                "Low": 100 + i * 0.2 - 0.5,
                "Close": 100 + i * 0.2 + 0.3,
                "Volume": 1000 + i * 10,
            }
        )
    df = pd.DataFrame(rows)
    return df


def test_profile_c_runs_without_error(monkeypatch):
    df5 = build_dummy_data()
    # Monkeypatch pipeline to produce one simple candidate signal
    from trade_setup_pipeline import run_pipeline as real_run

    def fake_run(**kwargs):
        # Return one candidate dict similar to existing schema
        return [
            {
                "direction": "long",
                "level": 100.0,
                "breakout_time": df5["Datetime"].iloc[5],
                "retest_time": df5["Datetime"].iloc[6],
                "breakout_candle": {
                    "Open": 100.0,
                    "High": 100.8,
                    "Low": 99.9,
                    "Close": 100.6,
                    "Volume": 2500,
                },
                "retest_candle": {
                    "Open": 100.55,
                    "High": 100.7,
                    "Low": 100.0,
                    "Close": 100.62,
                    "Volume": 400,
                },
                "ignition_time": df5["Datetime"].iloc[7],
                "ignition_candle": {
                    "Open": 100.62,
                    "High": 101.0,
                    "Low": 100.55,
                    "Close": 100.95,
                    "Volume": 500,
                },
            }
        ]

    monkeypatch.setattr("trade_setup_pipeline.run_pipeline", fake_run)

    engine = BacktestEngine(initial_capital=7500, pipeline_level=2, grading_system="profile")
    engine.grade_profile_name = "c"
    from grading.profile_loader import load_profile

    engine.grade_profile = load_profile("c")
    result = engine.run_backtest("TEST", df5, cache_dir=df5)
    assert result["symbol"] == "TEST"
    assert result["total_trades"] >= 0
    # Ensure grade profile annotated
    for sig in result.get("signals", []):
        assert sig.get("grade_profile") == "c"
        assert "stage_results" in sig
