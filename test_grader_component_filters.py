"""Component filter tests per-grader JSON configs.

We monkeypatch each grader's FILTERS dict to simulate disabling individual
components and assert that the scorer awards the maximum points for that
component while preserving other components' normal behavior.
"""

import pandas as pd
import pytest

import grading.breakout_grader as breakout_grader
import grading.retest_grader as retest_grader
import grading.ignition_grader as ignition_grader
import grading.trend_grader as trend_grader


def _mk(o, h, low_, c, v=100000):
    return {"Open": o, "High": h, "Low": low_, "Close": c, "Volume": v}


def test_breakout_disable_pattern_awards_max(monkeypatch):
    # Weak candle would otherwise score low pattern
    candle = _mk(100.0, 110.0, 95.0, 101.0)
    monkeypatch.setattr(
        breakout_grader,
        "FILTERS",
        {"filter_breakout_pattern": False, "filter_breakout_volume": True},
    )
    score = breakout_grader.score_breakout(candle, vol_ratio=1.0, profile={}, direction="long")
    # Pattern forced to 20; volume at 1.0 -> +2 => 22
    assert score == 22


def test_breakout_disable_volume_awards_max(monkeypatch):
    candle = _mk(100.0, 110.0, 100.0, 106.0)
    monkeypatch.setattr(
        breakout_grader,
        "FILTERS",
        {"filter_breakout_pattern": True, "filter_breakout_volume": False},
    )
    score = breakout_grader.score_breakout(candle, vol_ratio=0.8, profile={}, direction="long")
    # Pattern ~13; volume forced to 10 => >=23
    assert score >= 23


def test_retest_disable_pattern_awards_max(monkeypatch):
    ret = _mk(100.0, 101.0, 98.0, 99.9, 20000)
    br = 100000
    monkeypatch.setattr(
        retest_grader,
        "FILTERS",
        {"filter_retest_pattern": False, "filter_retest_volume": True},
    )
    score = retest_grader.score_retest(
        ret,
        level=99.8,
        direction="long",
        breakout_time=pd.Timestamp("2025-01-01T09:35Z"),
        retest_time=pd.Timestamp("2025-01-01T09:40Z"),
        breakout_volume=br,
        retest_volume=ret["Volume"],
        breakout_candle=_mk(100.0, 102.0, 99.0, 101.5, br),
        profile={},
    )
    # Pattern forced to 20 + some volume bonus (0 or 5 or 10)
    assert score >= 20


def test_retest_disable_volume_awards_max(monkeypatch):
    ret = _mk(100.0, 101.0, 98.0, 100.5, 50000)
    br = 100000
    monkeypatch.setattr(
        retest_grader,
        "FILTERS",
        {"filter_retest_pattern": True, "filter_retest_volume": False},
    )
    score = retest_grader.score_retest(
        ret,
        level=100.0,
        direction="short",
        breakout_time=pd.Timestamp("2025-01-01T09:35Z"),
        retest_time=pd.Timestamp("2025-01-01T09:40Z"),
        breakout_volume=br,
        retest_volume=ret["Volume"],
        breakout_candle=_mk(100.0, 102.0, 99.0, 101.5, br),
        profile={},
    )
    # Volume forced to 10
    assert score >= 10


def test_ignition_disable_components_award_max(monkeypatch):
    ign = _mk(10.0, 11.0, 10.0, 10.6, 30000)
    monkeypatch.setattr(
        ignition_grader,
        "FILTERS",
        {"filter_ignition_pattern": False, "filter_ignition_volume": False},
    )
    score = ignition_grader.score_ignition(
        ign,
        ignition_body_pct=0.2,
        ignition_vol_ratio=0.9,
        progress=0.0,
        profile={},
    )
    # Pattern forced 20 + volume 5 => 25 (clamped <=30)
    assert score == 25


def test_trend_disable_components_award_max(monkeypatch):
    sig = {
        "direction": "long",
        "breakout_candle": _mk(100.0, 101.0, 99.0, 99.5),
        "retest_candle": _mk(100.0, 101.0, 99.0, 99.5),
    }
    monkeypatch.setattr(
        trend_grader,
        "FILTERS",
        {
            "filter_trend_htf_stub": False,
            "filter_trend_vwap_breakout": False,
            "filter_trend_vwap_retest": False,
        },
    )
    pts = trend_grader.score_trend(sig, profile={})
    # Max trend points = 5 + 3 + 2 = 10
    assert pts == 10
