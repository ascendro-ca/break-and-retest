import pytest

import grading.breakout_grader as breakout_grader
from grading.breakout_grader import score_breakout

# Profile shells currently unused by score_breakout; keep placeholder.
DUMMY_PROFILE = {"name": "c"}


@pytest.fixture(autouse=True)
def _isolate_breakout_filters(monkeypatch):
    """Ensure tests are independent of breakout_grader.json and config flags.

    - Force FILTERS to enable both subcomponents so scoring logic runs
      (no auto-max from disabled filters).
    - Ensure feature flag is enabled so the scorer doesn't short-circuit to max.
    """
    monkeypatch.setattr(
        breakout_grader,
        "FILTERS",
        {"filter_breakout_pattern": True, "filter_breakout_volume": True},
        raising=True,
    )
    monkeypatch.setattr(
        breakout_grader,
        "CONFIG",
        {"feature_breakout_grader_enable": True},
        raising=True,
    )
    yield


def _mk(open_, high_, low_, close_):
    return {"Open": open_, "High": high_, "Low": low_, "Close": close_, "Volume": 1000}


def test_score_breakout_marubozu_max_points():
    # Perfect bullish marubozu: body ~100% range, negligible wicks
    candle = _mk(100.0, 110.0, 100.0, 110.0)  # range=10 body=10 body_pct=1
    score = score_breakout(candle, vol_ratio=1.6, profile=DUMMY_PROFILE)
    assert score == 30  # 20 (pattern) + 10 (volume)


def test_score_breakout_engulfing_approx_pattern():
    # Engulfing approximation: large body (0.80-0.89 range) small wicks
    # Ensure body_pct < 0.90 so it doesn't classify as marubozu.
    # Use small upper wick (<=10%) so it qualifies for the engulfing approximation.
    # Pick high=108.6 so range=8.6; upper wick=0.8 => 0.8/8.6 ≈ 0.093.
    # Body 7.8/8.6 ≈ 0.907 (still < marubozu due to wick thresholds in classifier).
    candle = _mk(100.0, 108.6, 100.0, 107.8)
    score = score_breakout(candle, vol_ratio=1.25, profile=DUMMY_PROFILE)
    # Pattern expected 18 + volume tier (1.2-1.5) => +5 = 23
    assert score == 23


def test_score_breakout_clean_candle_mid_volume():
    # Clean candle (body >= 0.60) but not special pattern; volume 1.05x => +2
    # Choose body_pct ~0.62
    candle = _mk(100.0, 110.0, 100.0, 106.2)  # range=10 body=6.2 body_pct=0.62
    score = score_breakout(candle, vol_ratio=1.05, profile=DUMMY_PROFILE)
    # 13 (pattern) + 2 (volume) = 15
    assert score == 15


def test_score_breakout_messy_moderate_body():
    # Messy / overlapping (0.40 <= body_pct < 0.60); volume 1.3x => +5
    candle = _mk(100.0, 110.0, 100.0, 104.5)  # range=10 body=4.5 body_pct=0.45
    score = score_breakout(candle, vol_ratio=1.3, profile=DUMMY_PROFILE)
    # 10 (pattern) + 5 (volume) = 15
    assert score == 15


def test_score_breakout_small_body_low_volume():
    # Small body (<0.40) weak pattern; low volume <1.0 => 0
    candle = _mk(100.0, 110.0, 95.0, 101.0)  # range=15 body=1 body_pct≈0.066
    score = score_breakout(candle, vol_ratio=0.8, profile=DUMMY_PROFILE)
    # 7 (pattern) + 0 (volume) = 7
    assert score == 7


def test_score_breakout_volume_exact_boundaries():
    # Check boundary conditions for volume tiers.
    maru = _mk(100.0, 110.0, 100.0, 110.0)
    # vol_ratio exactly 1.5 => should be 5 (not 10)
    score_1_5 = score_breakout(maru, vol_ratio=1.5, profile=DUMMY_PROFILE)
    assert score_1_5 == 25  # 20 + 5
    # vol_ratio just above 1.5 => 10
    score_1_51 = score_breakout(maru, vol_ratio=1.51, profile=DUMMY_PROFILE)
    assert score_1_51 == 30  # 20 + 10


def test_score_breakout_clamp_upper_bound():
    # Ensure no scores exceed 30 when both components max
    maru = _mk(100.0, 110.0, 100.0, 110.0)
    score = score_breakout(maru, vol_ratio=3.0, profile=DUMMY_PROFILE)
    assert score == 30
