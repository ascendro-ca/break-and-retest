"""
Tests for signal grading system (Scarface Rules)
"""

import pytest

from signal_grader import (
    calculate_overall_grade,
    generate_signal_report,
    grade_breakout_candle,
    grade_market_context,
    grade_retest,
    grade_risk_reward,
)


def test_grade_breakout_candle_perfect():
    """Test perfect breakout candle grading"""
    candle = {"Open": 100, "High": 105, "Low": 99, "Close": 104}
    vol_ratio = 2.5
    body_pct = 0.80

    grade, desc = grade_breakout_candle(candle, vol_ratio, body_pct)

    assert grade == "✅"
    assert "Strong candle + high vol" in desc


def test_grade_breakout_candle_weak():
    """Test weak breakout candle grading"""
    candle = {"Open": 100, "High": 101, "Low": 99, "Close": 100.2}
    vol_ratio = 0.8
    body_pct = 0.20

    grade, desc = grade_breakout_candle(candle, vol_ratio, body_pct)

    assert grade == "❌"
    assert "Weak" in desc


def test_grade_retest_long_perfect():
    """Test perfect long retest grading"""
    retest_candle = {"Open": 100, "High": 101, "Low": 99, "Close": 100.5}
    retest_vol_ratio = 0.3
    level = 100.0
    direction = "long"

    grade, desc = grade_retest(retest_candle, retest_vol_ratio, level, direction)

    assert grade == "✅"
    assert "rejection" in desc.lower()


def test_grade_retest_short_weak():
    """Test weak short retest grading"""
    retest_candle = {"Open": 100, "High": 101, "Low": 99, "Close": 101}
    retest_vol_ratio = 0.8
    level = 100.0
    direction = "short"

    grade, desc = grade_retest(retest_candle, retest_vol_ratio, level, direction)

    assert grade in ["❌", "⚠️"]


def test_grade_risk_reward_excellent():
    """Test excellent R/R grading"""
    grade, desc = grade_risk_reward(3.5)

    assert grade == "✅"
    assert "3.5:1" in desc


def test_grade_risk_reward_poor():
    """Test poor R/R grading"""
    grade, desc = grade_risk_reward(1.0)

    assert grade == "❌"
    assert "1.0:1" in desc


def test_grade_market_context():
    """Test market context grading"""
    grade_bullish, desc_bullish = grade_market_context("bullish")
    assert grade_bullish == "✅"
    assert "NQ" in desc_bullish

    grade_bearish, desc_bearish = grade_market_context("bearish")
    assert grade_bearish == "⚠️"


def test_calculate_overall_grade_a_plus():
    """Test A+ grade calculation - all 4 pre-entry components perfect"""
    grades = {
        "breakout": "✅",
        "retest": "✅",
        "continuation": "✅",  # Included but not counted in grade
        "rr": "✅",
        "market": "✅",
    }

    overall = calculate_overall_grade(grades)
    assert overall == "A+"


def test_calculate_overall_grade_a():
    """Test A grade calculation - 3/4 perfect, 1 warning"""
    grades = {
        "breakout": "✅",
        "retest": "✅",
        "continuation": "❌",  # Included but not counted in grade
        "rr": "✅",
        "market": "⚠️",
    }

    overall = calculate_overall_grade(grades)
    assert overall == "A"


def test_calculate_overall_grade_b():
    """Test B grade calculation - 2/4 perfect, 2 warnings, no fails"""
    grades = {
        "breakout": "✅",
        "retest": "⚠️",
        "continuation": "❌",  # Included but not counted in grade
        "rr": "✅",
        "market": "⚠️",
    }

    overall = calculate_overall_grade(grades)
    assert overall == "B"


def test_calculate_overall_grade_c():
    """Test C grade calculation - has failures in pre-entry components"""
    grades = {
        "breakout": "✅",
        "retest": "❌",
        "continuation": "❌",  # Included but not counted in grade
        "rr": "✅",
        "market": "⚠️",
    }

    overall = calculate_overall_grade(grades)
    assert overall == "C"


def test_generate_signal_report():
    """Test complete signal report generation"""
    signal = {
        "ticker": "AAPL",
        "direction": "long",
        "level": 232.0,
        "entry": 231.8,
        "stop": 231.5,
        "target": 233.3,
        "breakout_body_pct": 0.75,
        "breakout_vol_ratio": 2.5,
        "retest_vol_ratio": 0.3,
        "ignition_vol_ratio": 1.2,
        "distance_to_target": 0.8,
        "ignition_body_pct": 0.7,
        "breakout_candle": {"Open": 230, "High": 232, "Low": 230, "Close": 231.8},
        "retest_candle": {"Open": 232.5, "High": 232.6, "Low": 231.8, "Close": 232.0},
        "ignition_candle": {"Open": 232, "High": 233, "Low": 232, "Close": 232.8},
    }

    report = generate_signal_report(signal)

    assert "AAPL" in report
    assert "5m Breakout & Retest" in report
    assert "Scarface Rules" in report
    assert "232.0" in report  # level
    assert "231.5" in report  # stop
    assert "233.3" in report  # target
    assert "resistance" in report or "support" in report
    assert "Grade:" in report
    assert "✅" in report or "⚠️" in report or "❌" in report
