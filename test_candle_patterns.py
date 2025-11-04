"""
Tests for Candle Pattern Recognition Module
"""

import pandas as pd
import pytest

from candle_patterns import (
    analyze_candle_patterns,
    classify_candle_strength,
    get_candle_strength_score,
)


def test_classify_bullish_marubozu():
    """Test detection of bullish marubozu pattern."""
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 110.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "bullish_marubozu"
    assert result["direction"] == "bullish"
    assert result["strength"] == 1
    assert result["body_pct"] >= 0.90


def test_classify_bearish_marubozu():
    """Test detection of bearish marubozu pattern."""
    candle = pd.Series(
        {
            "Open": 110.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 100.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "bearish_marubozu"
    assert result["direction"] == "bearish"
    assert result["strength"] == 1
    assert result["body_pct"] >= 0.90


def test_classify_hammer():
    """Test detection of hammer pattern (long lower wick)."""
    candle = pd.Series(
        {
            "Open": 108.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 109.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "hammer"
    assert result["direction"] == "bullish"
    assert result["strength"] == 2
    assert result["lower_wick_pct"] >= 0.50


def test_classify_shooting_star():
    """Test detection of shooting star pattern (long upper wick)."""
    candle = pd.Series(
        {
            "Open": 102.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 101.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "shooting_star"
    assert result["direction"] == "bearish"
    assert result["strength"] == 2
    assert result["upper_wick_pct"] >= 0.50


def test_classify_dragonfly_doji():
    """Test detection of dragonfly doji (long lower wick, tiny body)."""
    candle = pd.Series(
        {
            "Open": 109.5,
            "High": 110.0,
            "Low": 100.0,
            "Close": 109.6,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "dragonfly_doji"
    assert result["direction"] == "bullish"
    assert result["strength"] == 2
    assert result["lower_wick_pct"] >= 0.50
    assert result["body_pct"] <= 0.05


def test_classify_gravestone_doji():
    """Test detection of gravestone doji (long upper wick, tiny body)."""
    candle = pd.Series(
        {
            "Open": 100.4,
            "High": 110.0,
            "Low": 100.0,
            "Close": 100.5,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "gravestone_doji"
    assert result["direction"] == "bearish"
    assert result["strength"] == 2
    assert result["upper_wick_pct"] >= 0.50
    assert result["body_pct"] <= 0.05


def test_classify_spinning_top_bullish():
    """Test detection of spinning top with bullish close."""
    candle = pd.Series(
        {
            "Open": 104.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 106.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "spinning_top_bullish"
    assert result["direction"] == "bullish"
    assert result["strength"] == 4
    assert result["body_pct"] <= 0.20
    assert result["upper_wick_pct"] >= 0.30
    assert result["lower_wick_pct"] >= 0.30


def test_classify_spinning_top_bearish():
    """Test detection of spinning top with bearish close."""
    candle = pd.Series(
        {
            "Open": 106.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 104.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "spinning_top_bearish"
    assert result["direction"] == "bearish"
    assert result["strength"] == 4
    assert result["body_pct"] <= 0.20


def test_classify_inverted_hammer_bullish():
    """Test detection of inverted hammer with bullish close."""
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 110.0,
            "Low": 99.0,
            "Close": 101.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "inverted_hammer_bullish"
    assert result["direction"] == "bullish"
    assert result["strength"] == 5
    assert result["upper_wick_pct"] >= 0.50


def test_classify_normal_bullish():
    """Test detection of normal bullish candle."""
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 108.0,
            "Low": 98.0,
            "Close": 106.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "normal_bullish"
    assert result["direction"] == "bullish"
    assert result["strength"] == 3


def test_classify_normal_bearish():
    """Test detection of normal bearish candle."""
    candle = pd.Series(
        {
            "Open": 106.0,
            "High": 108.0,
            "Low": 98.0,
            "Close": 100.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "normal_bearish"
    assert result["direction"] == "bearish"
    assert result["strength"] == 3


def test_classify_doji():
    """Test detection of standard doji (open == close)."""
    candle = pd.Series(
        {
            "Open": 105.0,
            "High": 108.0,
            "Low": 102.0,
            "Close": 105.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "doji"
    assert result["direction"] == "neutral"
    assert result["strength"] == 4
    assert result["body_pct"] == 0.0


def test_get_candle_strength_score_matching_direction():
    """Test strength score when candle matches expected direction."""
    # Strong bullish marubozu
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 110.0,
        }
    )

    score = get_candle_strength_score(candle, "long")

    assert score > 0.9  # Should be very high for marubozu in matching direction


def test_get_candle_strength_score_opposite_direction():
    """Test strength score penalization for opposite direction."""
    # Strong bullish marubozu
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 110.0,
            "Low": 100.0,
            "Close": 110.0,
        }
    )

    score = get_candle_strength_score(candle, "short")

    assert score < 0.6  # Should be penalized for wrong direction


def test_analyze_candle_patterns():
    """Test analyzing patterns across multiple candles."""
    df = pd.DataFrame(
        {
            "Open": [100.0, 110.0, 104.0, 100.0],
            "High": [110.0, 110.0, 110.0, 108.0],
            "Low": [100.0, 100.0, 100.0, 98.0],
            "Close": [110.0, 100.0, 106.0, 106.0],
        }
    )

    result = analyze_candle_patterns(df)

    assert "candle_type" in result.columns
    assert "candle_direction" in result.columns
    assert "candle_strength" in result.columns
    assert "body_pct" in result.columns

    # First candle should be bullish marubozu
    assert result.iloc[0]["candle_type"] == "bullish_marubozu"
    assert result.iloc[0]["candle_strength"] == 1

    # Second candle should be bearish marubozu
    assert result.iloc[1]["candle_type"] == "bearish_marubozu"
    assert result.iloc[1]["candle_strength"] == 1


def test_invalid_candle_zero_range():
    """Test handling of invalid candle with zero range."""
    candle = pd.Series(
        {
            "Open": 100.0,
            "High": 100.0,
            "Low": 100.0,
            "Close": 100.0,
        }
    )

    result = classify_candle_strength(candle)

    assert result["type"] == "invalid"
    assert result["direction"] == "neutral"
    assert result["strength"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
