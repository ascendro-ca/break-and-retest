import copy

import pandas as pd
import pytest

from grading import trend_grader as tg


@pytest.fixture()
def restore_filters():
    original_filters = copy.deepcopy(tg.FILTERS)
    original_config = copy.deepcopy(tg.CONFIG)
    try:
        yield
    finally:
        tg.FILTERS = original_filters
        tg.CONFIG = original_config


def test_trend_all_filters_disabled_returns_10(restore_filters):
    tg.CONFIG = {**tg.CONFIG, "feature_trend_grader_enable": True}
    tg.FILTERS = {
        "filter_trend_htf_stub": False,
        "filter_trend_vwap_breakout": False,
        "filter_trend_vwap_retest": False,
    }
    signal = {"direction": "long"}
    assert tg.score_trend(signal) == 10


def test_trend_series_inputs_are_handled_and_score_full_when_meeting_conditions(restore_filters):
    tg.CONFIG = {**tg.CONFIG, "feature_trend_grader_enable": True}
    # Keep filters enabled (defaults True)
    tg.FILTERS = {
        "filter_trend_htf_stub": True,
        "filter_trend_vwap_breakout": True,
        "filter_trend_vwap_retest": True,
    }
    breakout_series = pd.Series({"vwap": 100.0, "Close": 101.0})  # close >= vwap -> +3
    retest_series = pd.Series({"vwap": 100.0, "Open": 100.5, "Close": 100.6})  # min>=vwap -> +2
    signal = {
        "direction": "long",
        "breakout_candle": breakout_series,
        "retest_candle": retest_series,
    }
    # Expect 5 (HTF) + 3 (breakout VWAP) + 2 (retest VWAP) = 10
    assert tg.score_trend(signal) == 10


def test_trend_disabled_breakout_awards_points_even_when_condition_fails(restore_filters):
    tg.CONFIG = {**tg.CONFIG, "feature_trend_grader_enable": True}
    tg.FILTERS = {
        "filter_trend_htf_stub": True,
        "filter_trend_vwap_breakout": False,  # disabled -> award +3 regardless
        "filter_trend_vwap_retest": True,
    }
    breakout_series = pd.Series(
        {"vwap": 101.0, "Close": 100.0}
    )  # close < vwap (would fail if enabled)
    retest_series = pd.Series({"vwap": 102.0, "Open": 100.0, "Close": 101.0})  # min< vwap -> no +2
    signal = {
        "direction": "long",
        "breakout_candle": breakout_series,
        "retest_candle": retest_series,
    }
    # Expect 5 (HTF) + 3 (breakout disabled) + 0 (retest condition fails) = 8
    assert tg.score_trend(signal) == 8
