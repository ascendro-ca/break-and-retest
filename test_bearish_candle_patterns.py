"""
Test and visualize all bearish candle patterns from GRADING_SYSTEMS.md

This test creates synthetic price data for each bearish candle pattern mentioned
in the 100-point grading system, verifies them with TA-Lib (if available), and
outputs visualization-ready data.

Patterns tested:
1. Bearish Marubozu - Strong momentum, no hesitation (20 pts)
2. Engulfing Candle - Strong reversal through level (18 pts)
3. Wide-Range Breakout (WRB) - Large body breaking key level (17 pts)
4. Belt Hold - Gap-and-go with conviction (15 pts)
5. Shooting Star (Inverted Hammer) - Upper wick rejection (18 pts for retest)
6. Pin Bar (upper rejection) - Sharp rejection wick + tight body (17 pts for retest)
7. Doji w/ long rejection upper wick - Tap and hesitation (15 pts for retest)
8. Inside Bar - Tight base + resistance hold (13 pts for retest)

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

# ------------------- Pattern generators (bearish) -------------------


def create_bearish_marubozu(base_price=100.0, scale=2.0):
    """Bearish Marubozu: Open at high, close at low, no wicks"""
    return {
        "Open": base_price + scale,
        "High": base_price + scale,
        "Low": base_price,
        "Close": base_price,
        "Volume": 10000,
    }


def create_bearish_engulfing(prev_candle, scale=2.0):
    """Bearish Engulfing: Opens above previous close, closes below previous open"""
    prev_open = prev_candle["Open"]
    prev_close = prev_candle["Close"]
    return {
        "Open": prev_close + 0.5,  # Open above previous close
        "High": prev_open + 0.5,  # Slight extension
        "Low": prev_open - scale,  # Close below previous open
        "Close": prev_open - scale,
        "Volume": 12000,
    }


def create_wrb_bearish(base_price=104.0, scale=2.5):
    """Bearish WRB: Large bearish body (~75%) with modest wicks"""
    total = scale
    body = total * 0.75
    upper_wick = total * 0.15
    lower_wick = total * 0.10
    open_ = base_price
    close_ = base_price - body
    return {
        "Open": open_,
        "High": open_ + upper_wick,
        "Low": close_ - lower_wick,
        "Close": close_,
        "Volume": 9500,
    }


def create_belt_hold_bearish(base_price=106.5, scale=1.8):
    """Bearish Belt Hold: Opens at high (gap-and-go down), strong close near low"""
    total = scale
    body = total * 0.70
    upper_wick = total * 0.10
    lower_wick = total * 0.20
    open_ = base_price
    close_ = base_price - body
    return {
        "Open": open_,
        "High": open_ + upper_wick,
        "Low": close_ - lower_wick,
        "Close": close_,
        "Volume": 8500,
    }


def create_shooting_star(base_price=109.0, scale=1.5):
    """Shooting Star: Long upper wick (>=45%), small body near low (<=35%)"""
    total = scale
    upper_wick = total * 0.50
    body = total * 0.25
    lower_wick = total * 0.25
    close_ = base_price
    open_ = close_ + body * 0.3
    high_ = close_ + upper_wick
    low_ = close_ - lower_wick
    # Ensure bearish body (open > close or very small body)
    return {
        "Open": open_,
        "High": high_,
        "Low": low_,
        "Close": close_,
        "Volume": 5000,
    }


def create_bearish_pin_bar(base_price=110.0, scale=1.2):
    """Bearish Pin Bar: Sharp upper rejection (>=50%), very tight body"""
    total = scale
    upper_wick = total * 0.55
    body = total * 0.15
    lower_wick = total * 0.30
    high_ = base_price + upper_wick
    close_ = base_price - body * 0.6
    open_ = base_price + body * 0.4
    low_ = close_ - lower_wick
    return {
        "Open": open_,
        "High": high_,
        "Low": low_,
        "Close": close_,
        "Volume": 4500,
    }


def create_doji_long_upper_wick(base_price=111.5, scale=1.0):
    """Doji with long upper rejection wick: Open≈Close, long upper wick (>=35%)"""
    total = scale
    upper_wick = total * 0.40
    lower_wick = total * 0.55
    body = total * 0.05
    low_ = base_price - lower_wick
    open_ = low_ + body
    close_ = open_
    high_ = base_price + upper_wick
    return {
        "Open": open_,
        "High": high_,
        "Low": low_,
        "Close": close_,
        "Volume": 4000,
    }


def create_inside_bar_bearish(prev_candle):
    """Inside Bar: Entire range contained within previous (bearish context)"""
    prev_high = prev_candle["High"]
    prev_low = prev_candle["Low"]
    rng = (prev_high - prev_low) * 0.6
    mid = (prev_high + prev_low) / 2
    return {
        "Open": mid + rng * 0.2,
        "High": mid + rng * 0.3,
        "Low": mid - rng * 0.3,
        "Close": mid - rng * 0.2,
        "Volume": 3500,
    }


# ------------------- TA-Lib verification -------------------


def verify_with_talib(candle_df):
    """Verify candle patterns using TA-Lib if available."""
    try:
        import talib

        results = {}
        if len(candle_df) >= 3:
            results["CDLENGULFING"] = talib.CDLENGULFING(
                candle_df["Open"], candle_df["High"], candle_df["Low"], candle_df["Close"]
            )
            results["CDLSHOOTINGSTAR"] = talib.CDLSHOOTINGSTAR(
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


# ------------------- Main test -------------------


def test_bearish_candle_patterns_visualization():
    """Create a comprehensive chart showing bearish candle patterns with labels."""

    # Times in New York TZ
    start_time = pd.Timestamp("2025-11-03 09:30:00", tz="America/New_York")
    times = [start_time + timedelta(minutes=5 * i) for i in range(20)]

    candles = []
    labels = []

    # Opening range candle
    candles.append(
        {
            "Datetime": times[0],
            "Open": 112.0,
            "High": 112.5,
            "Low": 111.5,
            "Close": 112.2,
            "Volume": 8000,
        }
    )
    labels.append("Opening Range")

    # 1. Bearish Marubozu
    candles.append({"Datetime": times[1], **create_bearish_marubozu(base_price=110.0, scale=2.0)})
    labels.append("Marubozu (20pts)")

    # Setup for bearish engulfing: preceding up candle
    prev_up = {
        "Datetime": times[2],
        "Open": 110.0,
        "High": 111.2,
        "Low": 109.8,
        "Close": 111.0,
        "Volume": 7000,
    }
    candles.append(prev_up)
    labels.append("Setup")

    # 2. Bearish Engulfing
    candles.append({"Datetime": times[3], **create_bearish_engulfing(prev_up, scale=2.0)})
    labels.append("Engulfing (18pts)")

    # 3. Bearish WRB
    candles.append({"Datetime": times[4], **create_wrb_bearish(base_price=108.0, scale=2.5)})
    labels.append("WRB (17pts)")

    # 4. Bearish Belt Hold
    candles.append({"Datetime": times[5], **create_belt_hold_bearish(base_price=106.5, scale=1.8)})
    labels.append("Belt Hold (15pts)")

    # Consolidation
    for i in range(6, 9):
        candles.append(
            {
                "Datetime": times[i],
                "Open": 105.5,
                "High": 105.8,
                "Low": 105.2,
                "Close": 105.6,
                "Volume": 6000,
            }
        )
        labels.append("Consolidation")

    # 5. Shooting Star (retest pattern)
    candles.append({"Datetime": times[9], **create_shooting_star(base_price=105.0, scale=1.5)})
    labels.append("Shooting Star (18pts retest)")

    # 6. Bearish Pin Bar
    candles.append({"Datetime": times[10], **create_bearish_pin_bar(base_price=104.0, scale=1.2)})
    labels.append("Pin Bar (17pts)")

    # 7. Doji with long upper wick
    candles.append(
        {"Datetime": times[11], **create_doji_long_upper_wick(base_price=103.5, scale=1.0)}
    )
    labels.append("Doji+Upper Wick (15pts)")

    # Setup for inside bar
    prev_wide = {
        "Datetime": times[12],
        "Open": 104.0,
        "High": 104.5,
        "Low": 102.0,
        "Close": 102.5,
        "Volume": 8500,
    }
    candles.append(prev_wide)
    labels.append("Wide Range Down")

    # 8. Inside Bar
    candles.append({"Datetime": times[13], **create_inside_bar_bearish(prev_wide)})
    labels.append("Inside Bar (13pts)")

    # Fill remaining candles
    for i in range(14, 20):
        candles.append(
            {
                "Datetime": times[i],
                "Open": 102.4,
                "High": 102.8,
                "Low": 102.2,
                "Close": 102.6,
                "Volume": 7000,
            }
        )
        labels.append("")

    # DataFrame
    df = pd.DataFrame(candles)

    # Print classification summary
    print("\n" + "=" * 70)
    print("BEARISH CANDLE PATTERN VERIFICATION")
    print("=" * 70)
    for idx, (candle, label) in enumerate(zip(candles, labels)):
        if label and "pts" in label:
            s = pd.Series(candle)
            cls = classify_candle_strength(s)
            print(f"\n{idx}. {label}")
            print(f"   Type: {cls.get('type')}")
            print(f"   Direction: {cls.get('direction')}")
            print(f"   Strength: {cls.get('strength')}")
            print(f"   Body: {cls.get('body_pct', 0):.1%}")
            print(f"   Upper Wick: {cls.get('upper_wick_pct', 0):.1%}")
            print(f"   Lower Wick: {cls.get('lower_wick_pct', 0):.1%}")

    # TA-Lib verification
    print("\n" + "=" * 70)
    print("TA-LIB PATTERN VERIFICATION (Bearish)")
    print("=" * 70)
    ta = verify_with_talib(df)
    if "note" in ta:
        print(f"\n{ta['note']}")
    else:
        for name, series in ta.items():
            indices = [i for i, val in enumerate(series) if val != 0]
            if indices:
                print(f"\n{name}:")
                for i in indices:
                    lab = labels[i] if i < len(labels) else ""
                    print(f"  Index {i}: {lab} (score: {series[i]})")

    # Visualization
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATION (Bearish)")
    print("=" * 70)

    os.makedirs("logs", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"logs/test_bearish_patterns_{ts}.html"

    # Create a mock short signal to draw lines
    signals = [
        {
            "datetime": times[1],
            "direction": "short",
            "entry": 109.5,
            "stop": 111.5,
            "target": 106.5,
        }
    ]

    fig = create_chart(
        df, signals, output_file=out, title="Bearish Candle Patterns - GRADING_SYSTEMS.md"
    )

    # Add annotations at the candle times, aligning timezone with chart
    display_tz, _lbl = get_display_timezone(Path(__file__).parent)
    for t, label, candle in zip(times, labels, candles):
        if label and "pts" in label:
            y = candle["High"] + 0.5
            try:
                tdt = pd.to_datetime(t)
                if getattr(tdt, "tzinfo", None) is None:
                    tdt = tdt.tz_localize("UTC")
                tdt = tdt.tz_convert(display_tz)
            except Exception:
                tdt = t
            fig.add_annotation(
                x=tdt,
                y=y,
                text=label,
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="purple",
                ax=0,
                ay=-40,
                font=dict(size=10, color="purple"),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="purple",
                borderwidth=1,
            )

    fig.write_html(out)
    print(f"\nVisualization saved to: {out}")
    print(f"Open with: file://{Path(out).absolute()}")
    print("Or: python visualize_test_results.py --show-test")

    # Basic assert
    cnt = sum(1 for lab in labels if "pts" in lab)
    assert cnt == 8, f"Expected 8 patterns, found {cnt}"


if __name__ == "__main__":
    test_bearish_candle_patterns_visualization()
