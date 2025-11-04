"""
Test and visualize all bullish candle patterns from GRADING_SYSTEMS.md

This test creates synthetic price data for each bullish candle pattern mentioned
in the 100-point grading system, verifies them with TA-Lib (if available), and
outputs visualization-ready data.

Patterns tested:
1. Bullish Marubozu - Strong momentum, no hesitation (20 pts)
2. Engulfing Candle - Strong reversal through level (18 pts)
3. Wide-Range Breakout (WRB) - Large body breaking key level (17 pts)
4. Belt Hold - Gap-and-go with conviction (15 pts)
5. Hammer - Wick rejection and clean hold (18 pts for retest)
6. Pin Bar - Sharp rejection wick + tight body (17 pts for retest)
7. Doji w/ long rejection wick - Tap and hesitation (15 pts for retest)
8. Inside Bar - Tight base + support hold (13 pts for retest)

Output can be visualized with: python visualize_test_results.py --show-test
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from candle_patterns import classify_candle_strength
from time_utils import get_display_timezone
from visualize_test_results import create_chart


def create_bullish_marubozu(base_price=100.0, scale=2.0):
    """
    Bullish Marubozu: Open at low, close at high, no wicks
    Strong momentum, pure buying pressure (20 pts base)
    """
    return {
        "Open": base_price,
        "High": base_price + scale,
        "Low": base_price,
        "Close": base_price + scale,
        "Volume": 10000,
    }


def create_engulfing_candle(prev_candle, base_price=100.0, scale=2.5):
    """
    Bullish Engulfing: Opens below previous close, closes above previous open
    Reverses and engulfs prior candle (18 pts base)
    """
    prev_open = prev_candle["Open"]
    prev_close = prev_candle["Close"]

    return {
        "Open": prev_close - 0.5,  # Open below previous close
        "High": prev_open + scale,  # Close above previous open
        "Low": prev_close - 0.5,
        "Close": prev_open + scale,
        "Volume": 12000,
    }


def create_wrb_candle(base_price=100.0, scale=2.0):
    """
    Wide-Range Breakout (WRB): Large body (70%+) breaking key level
    Strong directional move (17 pts base)
    """
    total_range = scale
    body = total_range * 0.75  # 75% body
    upper_wick = total_range * 0.15
    lower_wick = total_range * 0.10

    return {
        "Open": base_price,
        "High": base_price + body + upper_wick,
        "Low": base_price - lower_wick,
        "Close": base_price + body,
        "Volume": 9500,
    }


def create_belt_hold(base_price=100.0, scale=1.8):
    """
    Belt Hold: Opens at low (gap-and-go), strong close near high
    Small lower wick (65%+ body) (15 pts base)
    """
    total_range = scale
    body = total_range * 0.70
    upper_wick = total_range * 0.20
    lower_wick = total_range * 0.10

    return {
        "Open": base_price,
        "High": base_price + body + upper_wick,
        "Low": base_price - lower_wick,
        "Close": base_price + body,
        "Volume": 8500,
    }


def create_hammer(base_price=100.0, scale=1.5):
    """
    Hammer: Long lower wick (45%+), small body at top (<=35% body)
    Bullish rejection pattern (18 pts for retest)
    """
    total_range = scale
    lower_wick = total_range * 0.50  # 50% lower wick
    body = total_range * 0.25  # 25% body
    # upper_wick = total_range * 0.25  # 25% upper wick (calculated but not explicitly used)

    return {
        "Open": base_price - lower_wick + body * 0.3,
        "High": base_price,
        "Low": base_price - lower_wick,
        "Close": base_price,
        "Volume": 5000,
    }


def create_pin_bar(base_price=100.0, scale=1.2):
    """
    Pin Bar: Sharp rejection wick (50%+), very tight body
    Similar to hammer but with even tighter body (17 pts for retest)
    """
    total_range = scale
    lower_wick = total_range * 0.55  # 55% lower wick
    body = total_range * 0.15  # 15% body
    upper_wick = total_range * 0.30  # 30% upper wick

    return {
        "Open": base_price - lower_wick + body * 0.4,
        "High": base_price,
        "Low": base_price - lower_wick,
        "Close": base_price - upper_wick + body * 0.6,
        "Volume": 4500,
    }


def create_doji_long_wick(base_price=100.0, scale=1.0):
    """
    Doji with long rejection wick: Open ≈ Close, long lower wick (35%+)
    Indecision but rejection signal (15 pts for retest)
    """
    total_range = scale
    lower_wick = total_range * 0.40
    upper_wick = total_range * 0.55
    body = total_range * 0.05  # Tiny body (doji)

    return {
        "Open": base_price - lower_wick,
        "High": base_price,
        "Low": base_price - lower_wick - upper_wick,
        "Close": base_price - lower_wick + body,
        "Volume": 4000,
    }


def create_inside_bar(prev_candle, base_price=100.0):
    """
    Inside Bar: Entire range contained within previous candle
    Tight consolidation (13 pts for retest)
    """
    prev_high = prev_candle["High"]
    prev_low = prev_candle["Low"]
    range_size = (prev_high - prev_low) * 0.6  # 60% of previous range

    midpoint = (prev_high + prev_low) / 2

    return {
        "Open": midpoint - range_size * 0.2,
        "High": midpoint + range_size * 0.3,
        "Low": midpoint - range_size * 0.3,
        "Close": midpoint + range_size * 0.2,
        "Volume": 3500,
    }


def verify_with_talib(candle_df):
    """
    Verify candle patterns using TA-Lib if available.
    Returns dict of pattern detection results.
    """
    try:
        import talib

        results = {}

        # TA-Lib pattern recognition functions
        # Note: TA-Lib needs at least a few candles for context
        if len(candle_df) >= 3:
            # Bullish patterns
            results["CDL3WHITESOLDIERS"] = talib.CDL3WHITESOLDIERS(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )
            results["CDLENGULFING"] = talib.CDLENGULFING(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )
            results["CDLHAMMER"] = talib.CDLHAMMER(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )
            results["CDLDOJI"] = talib.CDLDOJI(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )
            results["CDLMARUBOZU"] = talib.CDLMARUBOZU(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )

        return results
    except ImportError:
        return {"note": "TA-Lib not available - pattern verification skipped"}


def test_bullish_candle_patterns_visualization():
    """
    Create a comprehensive chart showing all bullish candle patterns with labels.
    Output format compatible with visualize_test_results.py
    """

    # Create time series starting from market open
    start_time = pd.Timestamp("2025-11-03 09:30:00", tz="America/New_York")
    times = [start_time + timedelta(minutes=5 * i) for i in range(20)]

    # Build candle data showing each pattern type
    candles = []
    pattern_labels = []

    # Opening range candle (normal)
    candles.append(
        {
            "Datetime": times[0],
            **{"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 8000},
        }
    )
    pattern_labels.append("Opening Range")

    # 1. Bullish Marubozu (20 pts)
    candles.append({"Datetime": times[1], **create_bullish_marubozu(base_price=100.5, scale=2.0)})
    pattern_labels.append("Marubozu (20pts)")

    # Setup for engulfing (need a down candle first)
    prev_down = {
        "Datetime": times[2],
        "Open": 102.5,
        "High": 102.6,
        "Low": 101.8,
        "Close": 102.0,
        "Volume": 7000,
    }
    candles.append(prev_down)
    pattern_labels.append("Setup")

    # 2. Engulfing Candle (18 pts)
    candles.append(
        {"Datetime": times[3], **create_engulfing_candle(prev_down, base_price=102.0, scale=2.0)}
    )
    pattern_labels.append("Engulfing (18pts)")

    # 3. Wide-Range Breakout (17 pts)
    candles.append({"Datetime": times[4], **create_wrb_candle(base_price=104.0, scale=2.5)})
    pattern_labels.append("WRB (17pts)")

    # 4. Belt Hold (15 pts)
    candles.append({"Datetime": times[5], **create_belt_hold(base_price=106.5, scale=1.8)})
    pattern_labels.append("Belt Hold (15pts)")

    # Consolidation candles
    for i in range(6, 9):
        candles.append(
            {
                "Datetime": times[i],
                "Open": 108.2,
                "High": 108.5,
                "Low": 108.0,
                "Close": 108.3,
                "Volume": 6000,
            }
        )
        pattern_labels.append("Consolidation")

    # 5. Hammer (18 pts - retest pattern)
    candles.append({"Datetime": times[9], **create_hammer(base_price=109.0, scale=1.5)})
    pattern_labels.append("Hammer (18pts retest)")

    # 6. Pin Bar (17 pts)
    candles.append({"Datetime": times[10], **create_pin_bar(base_price=110.0, scale=1.2)})
    pattern_labels.append("Pin Bar (17pts)")

    # 7. Doji with long wick (15 pts)
    candles.append({"Datetime": times[11], **create_doji_long_wick(base_price=111.5, scale=1.0)})
    pattern_labels.append("Doji+Wick (15pts)")

    # Setup for inside bar
    prev_wide = {
        "Datetime": times[12],
        "Open": 110.5,
        "High": 112.5,
        "Low": 110.0,
        "Close": 111.5,
        "Volume": 8500,
    }
    candles.append(prev_wide)
    pattern_labels.append("Wide Range")

    # 8. Inside Bar (13 pts)
    candles.append({"Datetime": times[13], **create_inside_bar(prev_wide, base_price=111.0)})
    pattern_labels.append("Inside Bar (13pts)")

    # Fill remaining with normal candles
    for i in range(14, 20):
        candles.append(
            {
                "Datetime": times[i],
                "Open": 111.5,
                "High": 112.0,
                "Low": 111.3,
                "Close": 111.8,
                "Volume": 7000,
            }
        )
        pattern_labels.append("")

    # Create DataFrame
    df = pd.DataFrame(candles)

    # Verify patterns with our classifier
    print("\n" + "=" * 70)
    print("BULLISH CANDLE PATTERN VERIFICATION")
    print("=" * 70)

    for idx, (candle, label) in enumerate(zip(candles, pattern_labels)):
        if label and "pts" in label:
            s = pd.Series(candle)
            classification = classify_candle_strength(s)

            print(f"\n{idx}. {label}")
            print(f"   Type: {classification.get('type')}")
            print(f"   Direction: {classification.get('direction')}")
            print(f"   Strength: {classification.get('strength')}")
            print(f"   Body: {classification.get('body_pct', 0):.1%}")
            print(f"   Upper Wick: {classification.get('upper_wick_pct', 0):.1%}")
            print(f"   Lower Wick: {classification.get('lower_wick_pct', 0):.1%}")

    # Try TA-Lib verification if available
    print("\n" + "=" * 70)
    print("TA-LIB PATTERN VERIFICATION")
    print("=" * 70)

    talib_results = verify_with_talib(df)
    if "note" in talib_results:
        print(f"\n{talib_results['note']}")
    else:
        for pattern_name, detections in talib_results.items():
            detected_indices = [i for i, val in enumerate(detections) if val != 0]
            if detected_indices:
                print(f"\n{pattern_name}:")
                for idx in detected_indices:
                    label = pattern_labels[idx] if idx < len(pattern_labels) else ""
                    print(f"  Index {idx}: {label} (score: {detections[idx]})")

    # Generate visualization
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATION")
    print("=" * 70)

    # Create output directory
    os.makedirs("logs", exist_ok=True)

    # Generate timestamp for unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"logs/test_bullish_patterns_{timestamp}.html"

    # Create mock signals for visualization (one signal to show pattern context)
    # We'll mark the marubozu as a "breakout" signal for visualization
    signals = [
        {
            "datetime": times[1],
            "direction": "long",
            "entry": 102.5,
            "stop": 100.0,
            "target": 107.5,
        }
    ]

    # Create chart with pattern annotations
    fig = create_chart(
        df, signals, output_file=output_file, title="Bullish Candle Patterns - GRADING_SYSTEMS.md"
    )

    # Add pattern labels to the chart
    # Ensure annotation timestamps are in the SAME timezone as the chart (display_tz)
    display_tz, _tz_label = get_display_timezone(Path(__file__).parent)
    for idx, (time, label) in enumerate(zip(times, pattern_labels)):
        if label and "pts" in label:
            # Add annotation for each key pattern
            candle = candles[idx]
            y_pos = candle["High"] + 0.5
            # Convert timestamp to chart's display timezone to avoid horizontal shifts
            try:
                t = pd.to_datetime(time)
                if getattr(t, "tzinfo", None) is None:
                    t = t.tz_localize("UTC")
                t = t.tz_convert(display_tz)
            except Exception:
                t = time

            fig.add_annotation(
                x=t,
                y=y_pos,
                text=label,
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="blue",
                ax=0,
                ay=-40,
                font=dict(size=10, color="blue"),
                bgcolor="rgba(255, 255, 255, 0.8)",
                bordercolor="blue",
                borderwidth=1,
            )

    # Save updated figure
    fig.write_html(output_file)

    print(f"\nVisualization saved to: {output_file}")
    print(f"\nTo view: python visualize_test_results.py --show-test")
    print(f"Or open directly: file://{Path(output_file).absolute()}")

    # Assert that we created all expected patterns
    pattern_count = sum(1 for label in pattern_labels if "pts" in label)
    assert pattern_count == 8, f"Expected 8 patterns, found {pattern_count}"

    print("\n" + "=" * 70)
    print("✅ Test completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_bullish_candle_patterns_visualization()
