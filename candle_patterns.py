"""
Candle Pattern Recognition Module
==================================

Provides candle pattern detection and classification using TA-Lib.

Pattern Strength Rankings:
---------------------------

Bullish Candles (most → least bullish):
1. Bullish Marubozu - Strong bullish candle with minimal wicks
2. Hammer / Dragonfly Doji - Long lower wick, small body near high
3. Normal Bullish Candle - Standard green candle with moderate body
4. Spinning Top (bullish close) - Small body, long wicks both sides
5. Inverted Hammer (weak bullish) - Long upper wick, small body near low

Bearish Candles (most → least bearish):
1. Bearish Marubozu - Strong bearish candle with minimal wicks
2. Shooting Star / Gravestone Doji - Long upper wick, small body near low
3. Normal Bearish Candle - Standard red candle with moderate body
4. Spinning Top (bearish close) - Small body, long wicks both sides
5. Inverted Hammer (weak bearish) - Long upper wick, small body

Usage:
------
    import pandas as pd
    from candle_patterns import detect_pattern, classify_candle_strength

    # Detect specific patterns
    df['hammer'] = detect_pattern(df, 'hammer')
    df['shooting_star'] = detect_pattern(df, 'shooting_star')

    # Classify candle strength
    df['candle_type'] = df.apply(lambda row: classify_candle_strength(row), axis=1)
"""

from typing import Dict

import pandas as pd

try:
    import talib

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("Warning: TA-Lib not available. Install with: pip install TA-Lib")


def detect_pattern(df: pd.DataFrame, pattern_name: str) -> pd.Series:
    """
    Detect a specific candlestick pattern using TA-Lib.

    Args:
        df: DataFrame with OHLC columns (Open, High, Low, Close)
        pattern_name: Name of pattern to detect. Options:
            - 'hammer': Hammer pattern
            - 'shooting_star': Shooting Star pattern
            - 'engulfing': Engulfing pattern (bullish/bearish)
            - 'doji': Doji pattern
            - 'marubozu': Marubozu pattern
            - 'spinning_top': Spinning Top pattern
            - 'inverted_hammer': Inverted Hammer pattern

    Returns:
        Series with pattern detection results:
            +100: Bullish pattern
            -100: Bearish pattern
            0: No pattern detected
    """
    if not TALIB_AVAILABLE:
        return pd.Series(0, index=df.index)

    open_prices = df["Open"].values
    high_prices = df["High"].values
    low_prices = df["Low"].values
    close_prices = df["Close"].values

    pattern_map = {
        "hammer": talib.CDLHAMMER,
        "shooting_star": talib.CDLSHOOTINGSTAR,
        "engulfing": talib.CDLENGULFING,
        "doji": talib.CDLDOJI,
        "marubozu": talib.CDLMARUBOZU,
        "spinning_top": talib.CDLSPINNINGTOP,
        "inverted_hammer": talib.CDLINVERTEDHAMMER,
        "dragonfly_doji": talib.CDLDRAGONFLYDOJI,
        "gravestone_doji": talib.CDLGRAVESTONEDOJI,
    }

    if pattern_name not in pattern_map:
        raise ValueError(f"Unknown pattern: {pattern_name}. Available: {list(pattern_map.keys())}")

    result = pattern_map[pattern_name](open_prices, high_prices, low_prices, close_prices)
    return pd.Series(result, index=df.index)


def classify_candle_strength(candle: pd.Series) -> Dict[str, any]:
    """
    Classify a single candle's strength and type.

    Args:
        candle: Series with Open, High, Low, Close values

    Returns:
        Dict with classification:
            - 'type': str - Pattern type (e.g., 'bullish_marubozu', 'hammer', 'normal_bullish')
            - 'direction': str - 'bullish', 'bearish', or 'neutral'
            - 'strength': int - Strength ranking (1=strongest, 5=weakest)
            - 'body_pct': float - Body as percentage of range
            - 'upper_wick_pct': float - Upper wick as percentage of range
            - 'lower_wick_pct': float - Lower wick as percentage of range
    """
    open_price = float(candle["Open"])
    high = float(candle["High"])
    low = float(candle["Low"])
    close = float(candle["Close"])

    # Calculate measurements
    candle_range = high - low
    if candle_range == 0:
        return {
            "type": "invalid",
            "direction": "neutral",
            "strength": 0,
            "body_pct": 0,
            "upper_wick_pct": 0,
            "lower_wick_pct": 0,
        }

    body = abs(close - open_price)
    body_pct = body / candle_range

    upper_wick = high - max(open_price, close)
    upper_wick_pct = upper_wick / candle_range

    lower_wick = min(open_price, close) - low
    lower_wick_pct = lower_wick / candle_range

    is_bullish = close > open_price
    is_bearish = close < open_price
    is_doji = abs(close - open_price) <= (candle_range * 0.05)  # Body <= 5% of range

    # Classification logic - Check for special doji patterns first
    if is_doji:
        if upper_wick_pct >= 0.40 and lower_wick_pct <= 0.10:
            return {
                "type": "gravestone_doji",
                "direction": "bearish",
                "strength": 2,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif lower_wick_pct >= 0.40 and upper_wick_pct <= 0.10:
            return {
                "type": "dragonfly_doji",
                "direction": "bullish",
                "strength": 2,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        else:
            return {
                "type": "doji",
                "direction": "neutral",
                "strength": 4,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }

    if is_bullish:
        # Bullish patterns (ranked by strength)
        if body_pct >= 0.90 and upper_wick_pct <= 0.05 and lower_wick_pct <= 0.05:
            return {
                "type": "bullish_marubozu",
                "direction": "bullish",
                "strength": 1,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif lower_wick_pct >= 0.50 and body_pct <= 0.20 and upper_wick_pct <= 0.20:
            # Hammer / Dragonfly Doji
            pattern_type = "dragonfly_doji" if body_pct <= 0.05 else "hammer"
            return {
                "type": pattern_type,
                "direction": "bullish",
                "strength": 2,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif upper_wick_pct >= 0.50 and body_pct <= 0.20 and lower_wick_pct <= 0.20:
            # Inverted Hammer (weak bullish)
            return {
                "type": "inverted_hammer_bullish",
                "direction": "bullish",
                "strength": 5,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif body_pct <= 0.20 and upper_wick_pct >= 0.30 and lower_wick_pct >= 0.30:
            # Spinning Top (bullish close)
            return {
                "type": "spinning_top_bullish",
                "direction": "bullish",
                "strength": 4,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        else:
            # Normal Bullish Candle
            return {
                "type": "normal_bullish",
                "direction": "bullish",
                "strength": 3,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }

    elif is_bearish:
        # Bearish patterns (ranked by strength)
        if body_pct >= 0.90 and upper_wick_pct <= 0.05 and lower_wick_pct <= 0.05:
            return {
                "type": "bearish_marubozu",
                "direction": "bearish",
                "strength": 1,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif upper_wick_pct >= 0.50 and body_pct <= 0.20 and lower_wick_pct <= 0.20:
            # Shooting Star / Gravestone Doji
            pattern_type = "gravestone_doji" if body_pct <= 0.05 else "shooting_star"
            return {
                "type": pattern_type,
                "direction": "bearish",
                "strength": 2,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif lower_wick_pct >= 0.50 and body_pct <= 0.20 and upper_wick_pct <= 0.20:
            # Inverted Hammer (weak bearish in this context)
            return {
                "type": "inverted_hammer_bearish",
                "direction": "bearish",
                "strength": 5,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        elif body_pct <= 0.20 and upper_wick_pct >= 0.30 and lower_wick_pct >= 0.30:
            # Spinning Top (bearish close)
            return {
                "type": "spinning_top_bearish",
                "direction": "bearish",
                "strength": 4,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }
        else:
            # Normal Bearish Candle
            return {
                "type": "normal_bearish",
                "direction": "bearish",
                "strength": 3,
                "body_pct": body_pct,
                "upper_wick_pct": upper_wick_pct,
                "lower_wick_pct": lower_wick_pct,
            }

    else:
        # Should not reach here
        return {
            "type": "unknown",
            "direction": "neutral",
            "strength": 0,
            "body_pct": body_pct,
            "upper_wick_pct": upper_wick_pct,
            "lower_wick_pct": lower_wick_pct,
        }


def get_candle_strength_score(candle: pd.Series, direction: str) -> float:
    """
    Get a numerical strength score for a candle in a given direction context.

    Args:
        candle: Series with OHLC data
        direction: Expected direction ('long' or 'short')

    Returns:
        Strength score from 0.0 (weakest) to 1.0 (strongest)
    """
    classification = classify_candle_strength(candle)

    # Check if candle direction matches expected direction
    expected_dir = "bullish" if direction == "long" else "bearish"
    direction_match = classification["direction"] == expected_dir

    # Base score from strength ranking (inverted: 1=strongest=1.0, 5=weakest=0.2)
    strength_score = (6 - classification["strength"]) / 5.0

    # Penalize if direction doesn't match
    if not direction_match:
        strength_score *= 0.5

    # Bonus for strong body
    body_bonus = min(classification["body_pct"], 0.9) * 0.1

    return min(strength_score + body_bonus, 1.0)


def analyze_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add candle pattern analysis columns to a DataFrame.

    Args:
        df: DataFrame with OHLC columns

    Returns:
        DataFrame with added columns:
            - candle_type: Pattern type
            - candle_direction: bullish/bearish/neutral
            - candle_strength: Strength ranking (1-5)
            - body_pct: Body percentage
    """
    result_df = df.copy()

    # Classify each candle
    classifications = df.apply(classify_candle_strength, axis=1)

    result_df["candle_type"] = classifications.apply(lambda x: x["type"])
    result_df["candle_direction"] = classifications.apply(lambda x: x["direction"])
    result_df["candle_strength"] = classifications.apply(lambda x: x["strength"])
    result_df["body_pct"] = classifications.apply(lambda x: x["body_pct"])
    result_df["upper_wick_pct"] = classifications.apply(lambda x: x["upper_wick_pct"])
    result_df["lower_wick_pct"] = classifications.apply(lambda x: x["lower_wick_pct"])

    return result_df


def detect_engulfing(prev: pd.Series, curr: pd.Series, tol: float = 1e-6) -> Dict[str, any]:
    """
    Detect true two-candle Engulfing pattern using the prior candle.

    - Bullish Engulfing: prev bearish, curr bullish, curr body engulfs prev body
    - Bearish Engulfing: prev bullish, curr bearish, curr body engulfs prev body

    Returns a dict:
      { 'detected': bool, 'direction': 'bullish'|'bearish'|'neutral',
        'strength': int, 'reason': str }
    """
    try:
        po, pc = (
            float(prev["Open"]),
            float(prev["Close"]),
        )
        co, cc = (
            float(curr["Open"]),
            float(curr["Close"]),
        )
    except Exception:
        return {"detected": False, "direction": "neutral", "strength": 0, "reason": "invalid_ohlc"}

    prev_bear = pc < po
    prev_bull = pc > po
    curr_bear = cc < co
    curr_bull = cc > co

    prev_body = abs(pc - po)
    curr_body = abs(cc - co)

    if max(prev_body, curr_body) <= 0:
        return {"detected": False, "direction": "neutral", "strength": 0, "reason": "zero_body"}

    # Bullish engulfing: current body spans from <= prev close to >= prev open
    if (
        prev_bear
        and curr_bull
        and (co <= pc + tol)
        and (cc >= po - tol)
        and (curr_body >= prev_body * 0.95)
    ):
        return {
            "detected": True,
            "direction": "bullish",
            "strength": 1,
            "reason": "bullish_engulfing",
        }

    # Bearish engulfing: current body spans from >= prev close to <= prev open
    if (
        prev_bull
        and curr_bear
        and (co >= pc - tol)
        and (cc <= po + tol)
        and (curr_body >= prev_body * 0.95)
    ):
        return {
            "detected": True,
            "direction": "bearish",
            "strength": 1,
            "reason": "bearish_engulfing",
        }

    return {"detected": False, "direction": "neutral", "strength": 0, "reason": "no_match"}
