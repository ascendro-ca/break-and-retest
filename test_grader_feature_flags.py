"""Tests for grader feature flags returning max points when disabled.

Each grader has a feature flag in config.json:
  - feature_breakout_grader_enable (max 30)
  - feature_retest_grader_enable (max 30)
  - feature_ignition_grader_enable (max 30)
  - feature_trend_grader_enable (max 10)

When the flag is False the scorer should return its max points regardless of input.
We monkeypatch the module-level CONFIG dict to simulate disabled flags without
mutating the shared config.json file.
"""

import pandas as pd
import pytest

import grading.breakout_grader as breakout_grader
import grading.retest_grader as retest_grader
import grading.ignition_grader as ignition_grader
import grading.trend_grader as trend_grader


@pytest.fixture
def breakout_candle():
    return {"Open": 10.0, "High": 11.0, "Low": 9.5, "Close": 10.8, "Volume": 100000}


@pytest.fixture
def retest_candle():
    return {"Open": 10.7, "High": 10.9, "Low": 10.5, "Close": 10.6, "Volume": 20000}


@pytest.fixture
def ignition_candle():
    return {"Open": 10.6, "High": 11.2, "Low": 10.6, "Close": 11.1, "Volume": 30000}


def test_breakout_flag_disabled_returns_max(monkeypatch, breakout_candle):
    monkeypatch.setattr(breakout_grader, "CONFIG", {"feature_breakout_grader_enable": False})
    pts = breakout_grader.score_breakout(
        breakout_candle, vol_ratio=0.5, profile={}, direction="long"
    )
    assert pts == 30


def test_retest_flag_disabled_returns_max(monkeypatch, retest_candle, breakout_candle):
    monkeypatch.setattr(retest_grader, "CONFIG", {"feature_retest_grader_enable": False})
    pts = retest_grader.score_retest(
        retest_candle,
        level=10.6,
        direction="long",
        breakout_time=pd.Timestamp("2025-01-01T09:35Z"),
        retest_time=pd.Timestamp("2025-01-01T09:40Z"),
        breakout_volume=breakout_candle["Volume"],
        retest_volume=retest_candle["Volume"],
        breakout_candle=breakout_candle,
        profile={},
    )
    assert pts == 30


def test_ignition_flag_disabled_returns_max(monkeypatch, ignition_candle):
    monkeypatch.setattr(ignition_grader, "CONFIG", {"feature_ignition_grader_enable": False})
    pts = ignition_grader.score_ignition(
        ignition_candle,
        ignition_body_pct=0.5,
        ignition_vol_ratio=0.8,
        progress=0.2,
        profile={},
    )
    assert pts == 30


def test_trend_flag_disabled_returns_max(monkeypatch, breakout_candle, retest_candle):
    monkeypatch.setattr(trend_grader, "CONFIG", {"feature_trend_grader_enable": False})
    signal = {
        "direction": "long",
        "breakout_candle": breakout_candle,
        "retest_candle": retest_candle,
    }
    pts = trend_grader.score_trend(signal, profile={})
    assert pts == 10
