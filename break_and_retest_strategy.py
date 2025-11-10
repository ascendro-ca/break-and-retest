"""
Break & Re-Test Scalp Strategy Scanner
Scans 5-min intraday data for configured tickers
Detects break and re-test long/short setups using:
- Key levels (premarket high, opening range)
- Breakout candle (strong body, above-average volume)
- Re-test (price returns, holds level, tight candle, lower volume)
- Ignition candle (strong body, breaks re-test high/low, volume increases)
- Entry, stop, target logic
"""

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from break_and_retest_detection_mt import scan_for_setups
from signal_grader import (
    calculate_overall_grade,
    generate_signal_report,
    grade_breakout_candle,
    grade_market_context,
    grade_retest,
    grade_risk_reward,
)
from time_utils import get_display_timezone

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds


def _derive_tickers_from_cache(cache_dir: Path) -> list[str]:
    """Derive ticker list from cache subdirectories.

    Returns a sorted unique list of directory names (uppercased) that look like tickers.
    """
    tickers: set[str] = set()
    try:
        if cache_dir.exists():
            for child in cache_dir.iterdir():
                if child.is_dir():
                    name = child.name.strip().upper()
                    # Basic sanity filter: letters/numbers only, length 1-5
                    if 1 <= len(name) <= 6 and name.replace("-", "").isalnum():
                        tickers.add(name)
    except Exception:
        # Be resilient; fall back to defaults if anything goes wrong
        pass
    return sorted(tickers)


# Load configuration
def load_config():
    """Load configuration from config.json.

    If no config.json or if the tickers list is missing/empty, derive tickers from the
    cache/ directory and persist back to config.json.
    """
    config_path = Path(__file__).parent / "config.json"
    default_config = {
        "tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"],
        "timeframe_5m": "5m",
        "lookback": "2d",
        "session_start_et": "09:30",
        "session_end_et": "16:00",
        "market_open_minutes": 90,
    }

    config = default_config.copy()

    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                on_disk = json.load(f)
            if isinstance(on_disk, dict):
                # Shallow merge to preserve any new defaults when missing on disk
                config.update(on_disk)
        except Exception:
            # If parsing fails, proceed with defaults and rebuild below if needed
            pass

    # If tickers missing/empty, derive from cache and write back to disk
    if not config.get("tickers"):
        cache_dir = Path(__file__).parent / "cache"
        derived = _derive_tickers_from_cache(cache_dir)
        if derived:
            config["tickers"] = derived
        # Persist the updated config (creating file if missing)
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            # Non-fatal; continue with in-memory config
            pass

    return config


CONFIG = load_config()
TICKERS = CONFIG["tickers"]
TIMEFRAME = CONFIG["timeframe_5m"]
LOOKBACK = CONFIG["lookback"]
SESSION_START = CONFIG.get("session_start_et", "09:30")
SESSION_END = CONFIG.get("session_end_et", "16:00")
MARKET_OPEN_MINUTES = CONFIG["market_open_minutes"]
RETEST_VOL_GATE = CONFIG.get("retest_volume_gate_ratio", 0.20)
BREAKOUT_A_UW_MAX = CONFIG.get("breakout_A_upper_wick_max", 0.15)
BREAKOUT_B_BODY_MAX = CONFIG.get("breakout_B_body_max", 0.65)
RETEST_B_EPSILON = CONFIG.get("retest_B_level_epsilon_pct", 0.10)
RETEST_B_SOFT = CONFIG.get("retest_B_structure_soft", True)


# --- Helper Functions ---
def get_intraday_data(
    ticker,
    retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
    timeframe=TIMEFRAME,
    lookback=LOOKBACK,
):
    """Download intraday data with simple retry/backoff.

    Returns a DataFrame (may be empty).
    Always returns a DataFrame (possibly empty) instead of raising so
    callers can handle missing data.
    """
    attempt = 0
    last_exc = None
    while attempt < retries:
        try:
            df = yf.download(
                ticker, period=lookback, interval=timeframe, progress=False, auto_adjust=True
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            df["Datetime"] = pd.to_datetime(df["Datetime"])
            # Filter for today's session
            today = datetime.now().date()
            df_today = df[df["Datetime"].dt.date == today]
            return df_today
        except Exception as e:
            last_exc = e
            attempt += 1
            print(f"{ticker}: data download failed (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(retry_delay * attempt)
    # If we get here, return empty DataFrame and log last exception
    print(f"{ticker}: failed to download data after {retries} attempts. Last error: {last_exc}")
    return pd.DataFrame()


def find_premarket_high(df):
    # Premarket: before 09:30
    premarket = df[df["Datetime"].dt.strftime("%H:%M") < SESSION_START]
    if len(premarket) == 0:
        return None
    return premarket["High"].max()


def find_first_candle_range(df):
    # Find first 5-min candle after market open (09:30)
    session = df[df["Datetime"].dt.strftime("%H:%M") >= SESSION_START]
    if len(session) == 0:
        return None, None
    first_candle = session.iloc[0]
    return first_candle["High"], first_candle["Low"]


def scan_ticker(
    ticker,
    timeframe=TIMEFRAME,
    lookback=LOOKBACK,
    retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
    market_open_minutes=MARKET_OPEN_MINUTES,
):
    """
    Scan ticker for break and retest setups using multi-timeframe analysis.

    Uses 5-minute timeframe for breakout detection and 1-minute timeframe
    for retest/ignition detection (matching backtest behavior).

    Args:
        ticker: Stock ticker symbol
        timeframe: Not used (kept for backward compatibility)
        lookback: Lookback period for data fetching
        retries: Number of retry attempts for data fetching
        retry_delay: Delay between retries
        market_open_minutes: Minutes after market open to scan

    Returns:
        (signals, scan_df_5m) tuple
    """
    # Fetch 5-minute data for breakout detection
    df_5m = get_intraday_data(
        ticker, retries=retries, retry_delay=retry_delay, timeframe="5m", lookback=lookback
    )
    if df_5m is None or df_5m.empty:
        print(f"{ticker}: No 5m data returned (empty). Skipping.")
        return [], pd.DataFrame()
    if len(df_5m) < 20:
        print(f"{ticker}: Not enough 5m data for scan.")
        return [], df_5m

    # Fetch 1-minute data for retest/ignition detection
    df_1m = get_intraday_data(
        ticker, retries=retries, retry_delay=retry_delay, timeframe="1m", lookback=lookback
    )
    if df_1m is None or df_1m.empty:
        print(f"{ticker}: No 1m data returned. Skipping (multi-timeframe required).")
        return [], df_5m

    # Use first 5-min candle after market open as range
    or_high, or_low = find_first_candle_range(df_5m)
    if or_high is None or or_low is None:
        print(f"{ticker}: No opening range found.")
        return [], df_5m

    # Restrict detection to first N minutes after open
    session_5m = df_5m[df_5m["Datetime"].dt.strftime("%H:%M") >= SESSION_START]
    if len(session_5m) == 0:
        print(f"{ticker}: No session data.")
        return [], df_5m

    start_time = session_5m["Datetime"].iloc[0]
    end_time = start_time + timedelta(minutes=market_open_minutes)
    scan_df_5m = session_5m[
        (session_5m["Datetime"] >= start_time) & (session_5m["Datetime"] < end_time)
    ].copy()

    if len(scan_df_5m) < 10:
        print(f"{ticker}: Not enough data in first {market_open_minutes} min.")
        return [], scan_df_5m

    # Compute rolling volume mean for breakout detection
    scan_df_5m["vol_ma"] = scan_df_5m["Volume"].rolling(window=10, min_periods=1).mean()

    # Calculate VWAP for trend filtering
    scan_df_5m["typical_price"] = (scan_df_5m["High"] + scan_df_5m["Low"] + scan_df_5m["Close"]) / 3
    scan_df_5m["tp_volume"] = scan_df_5m["typical_price"] * scan_df_5m["Volume"]
    scan_df_5m["vwap"] = scan_df_5m["tp_volume"].cumsum() / scan_df_5m["Volume"].cumsum()

    # Also filter 1m data to same session window if available
    session_df_1m = None
    if df_1m is not None:
        session_df_1m = df_1m[
            (df_1m["Datetime"] >= start_time) & (df_1m["Datetime"] < end_time)
        ].copy()

    # Use shared detection module to find setups (multi-timeframe only)
    setups = scan_for_setups(
        df_5m=scan_df_5m,
        df_1m=session_df_1m,
        or_high=or_high,
        or_low=or_low,
        vol_threshold=1.0,  # Match backtest volume threshold
    )

    signals = []
    for setup in setups:
        breakout_candle = setup["breakout"]["candle"]
        retest_candle = setup["retest"]
        ignition_candle = setup["ignition"]
        direction = setup["direction"]
        level = setup["level"]

        breakout_up = direction == "long"

        # Calculate entry, stop, target
        entry = ignition_candle["High"] if breakout_up else ignition_candle["Low"]
        stop = retest_candle["Low"] - 0.05 if breakout_up else retest_candle["High"] + 0.05
        risk = abs(entry - stop)
        target = entry + 2 * risk if breakout_up else entry - 2 * risk

        # Calculate grading metrics
        breakout_body = abs(breakout_candle["Close"] - breakout_candle["Open"])
        breakout_range = breakout_candle["High"] - breakout_candle["Low"]
        breakout_body_pct = breakout_body / breakout_range if breakout_range > 0 else 0
        breakout_vol_ratio = (
            breakout_candle["Volume"] / breakout_candle["vol_ma"]
            if breakout_candle["vol_ma"] > 0
            else 1.0
        )

        # For multi-timeframe, compare 1m retest volume to 5m breakout volume
        retest_vol_ratio = (
            retest_candle["Volume"] / breakout_candle["Volume"]
            if breakout_candle["Volume"] > 0
            else 1.0
        )

        ignition_body = abs(ignition_candle["Close"] - ignition_candle["Open"])
        ignition_range = ignition_candle["High"] - ignition_candle["Low"]
        ignition_body_pct = ignition_body / ignition_range if ignition_range > 0 else 0
        ignition_vol_ratio = (
            ignition_candle["Volume"] / retest_candle["Volume"]
            if retest_candle["Volume"] > 0
            else 1.0
        )

        rr_ratio = abs(target - entry) / risk if risk > 0 else 0
        distance_to_target = 0.0  # Placeholder for live scanner

        # Grade each component
        breakout_grade, breakout_desc = grade_breakout_candle(
            {
                "Open": breakout_candle["Open"],
                "High": breakout_candle["High"],
                "Low": breakout_candle["Low"],
                "Close": breakout_candle["Close"],
            },
            breakout_vol_ratio,
            breakout_body_pct,
            level,
            direction,
            a_upper_wick_max=BREAKOUT_A_UW_MAX,
            b_body_max=BREAKOUT_B_BODY_MAX,
        )
        breakout_tier = "A" if breakout_grade == "✅" else ("B" if breakout_grade == "⚠️" else "C")
        retest_candle_dict = {
            "Open": retest_candle["Open"],
            "High": retest_candle["High"],
            "Low": retest_candle["Low"],
            "Close": retest_candle["Close"],
        }
        retest_grade, retest_desc = grade_retest(
            retest_candle_dict,
            retest_vol_ratio,
            level,
            direction,
            retest_volume_a_max_ratio=0.30,
            retest_volume_b_max_ratio=0.60,
            b_level_epsilon_pct=RETEST_B_EPSILON,
            b_structure_soft=RETEST_B_SOFT,
        )
        rr_grade, rr_desc = grade_risk_reward(rr_ratio)
        market_grade, market_desc = grade_market_context("slightly_red")

        # Calculate overall grade (4 components: breakout, retest, RR, market)
        # Note: continuation excluded as it requires post-entry data
        grades = {
            "breakout": breakout_grade,
            "retest": retest_grade,
            "risk_reward": rr_grade,
            "market": market_grade,
        }
        overall_grade = calculate_overall_grade(grades)

        signal = {
            "ticker": ticker,
            "datetime": ignition_candle["Datetime"],
            "direction": direction,
            "level": level,
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk": risk,
            "vol_breakout": breakout_candle["Volume"],
            "vol_retest": retest_candle["Volume"],
            "vol_ignition": ignition_candle["Volume"],
            "breakout_tier": breakout_tier,
            "vwap": setup.get("vwap"),  # VWAP at breakout time
            # Grading metrics
            "breakout_body_pct": breakout_body_pct,
            "breakout_vol_ratio": breakout_vol_ratio,
            "retest_vol_ratio": retest_vol_ratio,
            "ignition_vol_ratio": ignition_vol_ratio,
            "ignition_body_pct": ignition_body_pct,
            "distance_to_target": distance_to_target,
            # Candle data for report generation
            "breakout_candle": {
                "Open": breakout_candle["Open"],
                "High": breakout_candle["High"],
                "Low": breakout_candle["Low"],
                "Close": breakout_candle["Close"],
            },
            "retest_candle": {
                "Open": retest_candle["Open"],
                "High": retest_candle["High"],
                "Low": retest_candle["Low"],
                "Close": retest_candle["Close"],
            },
            "ignition_candle": {
                "Open": ignition_candle["Open"],
                "High": ignition_candle["High"],
                "Low": ignition_candle["Low"],
                "Close": ignition_candle["Close"],
            },
            # Grades
            "grades": grades,
            "overall_grade": overall_grade,
        }
        signals.append(signal)

    # Print Results
    if signals:
        for sig in signals:
            # Generate and print Scarface Rules report for this signal
            report = generate_signal_report(
                sig,
                retest_volume_a_max_ratio=0.30,
                retest_volume_b_max_ratio=0.60,
                a_upper_wick_max=BREAKOUT_A_UW_MAX,
                b_body_max=BREAKOUT_B_BODY_MAX,
                b_level_epsilon_pct=RETEST_B_EPSILON,
                b_structure_soft=RETEST_B_SOFT,
            )
            print(report)
            print()  # Blank line between signals
    else:
        print(f"{ticker}: No setups found.")

    # Return signals and the scan dataframe for downstream use
    return signals, scan_df_5m


def scan_dataframe(df_5m, df_1m=None, market_open_minutes=MARKET_OPEN_MINUTES):
    """
    Scan pre-loaded intraday DataFrames for break and retest setups.

    Args:
        df_5m: DataFrame with 5-minute candles (Datetime, OHLCV)
        df_1m: Optional DataFrame with 1-minute candles for multi-timeframe analysis
        market_open_minutes: Minutes after market open to scan

    Returns:
        (signals, scan_df_5m) tuple where scan_df_5m is the restricted session slice
    """
    if df_5m is None or df_5m.empty:
        return [], pd.DataFrame()

    # Ensure Datetime is datetime
    df_5m = df_5m.copy()
    df_5m["Datetime"] = pd.to_datetime(df_5m["Datetime"])

    # Use first 5-min candle after market open as range
    session = df_5m[df_5m["Datetime"].dt.strftime("%H:%M") >= SESSION_START]
    if len(session) == 0:
        return [], pd.DataFrame()

    first = session.iloc[0]
    or_high, or_low = first.get("High"), first.get("Low")
    if or_high is None or or_low is None:
        return [], pd.DataFrame()

    start_time = session["Datetime"].iloc[0]
    end_time = start_time + timedelta(minutes=market_open_minutes)
    scan_df_5m = session[
        (session["Datetime"] >= start_time) & (session["Datetime"] < end_time)
    ].copy()

    if len(scan_df_5m) < 1:
        return [], scan_df_5m

    scan_df_5m["vol_ma"] = scan_df_5m["Volume"].rolling(window=10, min_periods=1).mean()

    # Filter 1m data to same session window if available
    session_df_1m = None
    if df_1m is not None:
        df_1m = df_1m.copy()
        df_1m["Datetime"] = pd.to_datetime(df_1m["Datetime"])
        session_df_1m = df_1m[
            (df_1m["Datetime"] >= start_time) & (df_1m["Datetime"] < end_time)
        ].copy()

    # Use shared detection module (requires 1m data)
    if df_1m is None:
        return [], scan_df_5m
    vol_threshold = 1.0
    setups = scan_for_setups(
        df_5m=scan_df_5m,
        df_1m=session_df_1m,
        or_high=or_high,
        or_low=or_low,
        vol_threshold=vol_threshold,
    )

    signals = []
    for setup in setups:
        breakout_candle = setup["breakout"]["candle"]
        retest_candle = setup["retest"]
        ignition_candle = setup["ignition"]
        direction = setup["direction"]
        level = setup["level"]

        breakout_up = direction == "long"

        # Calculate entry, stop, target
        entry = ignition_candle["High"] if breakout_up else ignition_candle["Low"]
        stop = retest_candle["Low"] - 0.05 if breakout_up else retest_candle["High"] + 0.05
        risk = abs(entry - stop)
        target = entry + 2 * risk if breakout_up else entry - 2 * risk

        # Calculate grading metrics
        breakout_body = abs(breakout_candle["Close"] - breakout_candle["Open"])
        breakout_range = breakout_candle["High"] - breakout_candle["Low"]
        breakout_body_pct = breakout_body / breakout_range if breakout_range > 0 else 0
        breakout_vol_ratio = (
            breakout_candle["Volume"] / breakout_candle["vol_ma"]
            if breakout_candle["vol_ma"] > 0
            else 1.0
        )

        retest_vol_ratio = (
            retest_candle["Volume"] / breakout_candle["Volume"]
            if breakout_candle["Volume"] > 0
            else 1.0
        )

        ignition_body = abs(ignition_candle["Close"] - ignition_candle["Open"])
        ignition_range = ignition_candle["High"] - ignition_candle["Low"]
        ignition_body_pct = ignition_body / ignition_range if ignition_range > 0 else 0
        ignition_vol_ratio = (
            ignition_candle["Volume"] / retest_candle["Volume"]
            if retest_candle["Volume"] > 0
            else 1.0
        )

        rr_ratio = abs(target - entry) / risk if risk > 0 else 0
        distance_to_target = 0.0  # Placeholder for live scanner

        # Grade each component
        breakout_grade, breakout_desc = grade_breakout_candle(
            {
                "Open": breakout_candle["Open"],
                "High": breakout_candle["High"],
                "Low": breakout_candle["Low"],
                "Close": breakout_candle["Close"],
            },
            breakout_vol_ratio,
            breakout_body_pct,
            level,
            direction,
            a_upper_wick_max=BREAKOUT_A_UW_MAX,
            b_body_max=BREAKOUT_B_BODY_MAX,
        )
        breakout_tier = "A" if breakout_grade == "✅" else ("B" if breakout_grade == "⚠️" else "C")
        retest_candle_dict = {
            "Open": retest_candle["Open"],
            "High": retest_candle["High"],
            "Low": retest_candle["Low"],
            "Close": retest_candle["Close"],
        }
        retest_grade, retest_desc = grade_retest(
            retest_candle_dict,
            retest_vol_ratio,
            level,
            direction,
            retest_vol_threshold=RETEST_VOL_GATE,
            b_level_epsilon_pct=RETEST_B_EPSILON,
            b_structure_soft=RETEST_B_SOFT,
        )
        rr_grade, rr_desc = grade_risk_reward(rr_ratio)
        market_grade, market_desc = grade_market_context("slightly_red")

        # Calculate overall grade (4 components: breakout, retest, RR, market)
        # Note: continuation excluded as it requires post-entry data
        grades = {
            "breakout": breakout_grade,
            "retest": retest_grade,
            "risk_reward": rr_grade,
            "market": market_grade,
        }
        overall_grade = calculate_overall_grade(grades)

        signals.append(
            {
                "direction": direction,
                "entry": entry,
                "stop": stop,
                "target": target,
                "risk": risk,
                "vol_breakout": breakout_candle["Volume"],
                "vol_retest": retest_candle["Volume"],
                "vol_ignition": ignition_candle["Volume"],
                "datetime": ignition_candle["Datetime"],
                "level": level,
                "breakout_tier": breakout_tier,
                # Grading metrics
                "breakout_body_pct": breakout_body_pct,
                "breakout_vol_ratio": breakout_vol_ratio,
                "retest_vol_ratio": retest_vol_ratio,
                "ignition_vol_ratio": ignition_vol_ratio,
                "ignition_body_pct": ignition_body_pct,
                "distance_to_target": distance_to_target,
                # Candle data
                "breakout_candle": {
                    "Open": breakout_candle["Open"],
                    "High": breakout_candle["High"],
                    "Low": breakout_candle["Low"],
                    "Close": breakout_candle["Close"],
                },
                "retest_candle": {
                    "Open": retest_candle["Open"],
                    "High": retest_candle["High"],
                    "Low": retest_candle["Low"],
                    "Close": retest_candle["Close"],
                },
                "ignition_candle": {
                    "Open": ignition_candle["Open"],
                    "High": ignition_candle["High"],
                    "Low": ignition_candle["Low"],
                    "Close": ignition_candle["Close"],
                },
                # Grades
                "grades": grades,
                "overall_grade": overall_grade,
            }
        )

    return signals, scan_df_5m


def _parse_tickers(s: str):
    return [t.strip().upper() for t in s.split(",")] if s else TICKERS


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="5-min Break & Re-Test Scalp Strategy Scanner (CLI)")
    p.add_argument(
        "--tickers",
        default=",".join(TICKERS),
        help="Comma-separated tickers to scan (default: common list)",
    )
    p.add_argument("--timeframe", default=TIMEFRAME)
    p.add_argument("--lookback", default=LOOKBACK)
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    p.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY)
    p.add_argument("--open-minutes", type=int, default=MARKET_OPEN_MINUTES)
    p.add_argument(
        "--min-grade",
        type=str,
        choices=["A", "B", "C"],
        help="Minimum grade filter (A, B, or C). Only show signals with this grade or higher.",
    )
    args = p.parse_args()

    # Resolve display timezone and show it once for clarity
    display_tz, tz_label = get_display_timezone(Path(__file__).parent)

    tickers = _parse_tickers(args.tickers)
    print("\n=== 5-Min Break & Re-Test Scalp Strategy Scanner (CLI) ===\n")
    print(f"Timezone: {tz_label}\n")

    # Define grade hierarchy for filtering
    grade_order = {"A": 3, "B": 2, "C": 1}
    min_grade_value = grade_order.get(args.min_grade, 0) if args.min_grade else 0

    for ticker in tickers:
        try:
            signals, scan_df = scan_ticker(
                ticker,
                timeframe=args.timeframe,
                lookback=args.lookback,
                retries=args.retries,
                retry_delay=args.retry_delay,
                market_open_minutes=args.open_minutes,
            )

            # Apply grade filter if specified
            if args.min_grade and signals:
                filtered_signals = []
                for sig in signals:
                    sig_grade = sig.get("overall_grade", "C")
                    sig_grade_value = grade_order.get(sig_grade, 0)
                    if sig_grade_value >= min_grade_value:
                        filtered_signals.append(sig)

                # Replace signals with filtered list
                signals = filtered_signals

                if not signals:
                    print(f"{ticker}: No signals found matching grade {args.min_grade}+ filter.")
                    continue

            # Default behavior: save scan CSV and signals JSON into logs/ with timestamp
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Ensure both data/ and logs/ exist. CSVs go to data/, JSON signals remain in logs/
            os.makedirs("data", exist_ok=True)
            os.makedirs("logs", exist_ok=True)
            if scan_df is not None and not scan_df.empty:
                scan_path = os.path.join("data", f"{ticker}_scan_{ts}.csv")
                try:
                    scan_df.to_csv(scan_path, index=False)
                    print(f"Saved scan dataframe to {scan_path}")
                except Exception as e:
                    print(f"{ticker}: Failed to save scan dataframe: {e}")
            if signals:
                signals_path = os.path.join("logs", f"{ticker}_signals_{ts}.json")
                try:
                    with open(signals_path, "w") as fh:
                        json.dump(signals, fh, default=str, indent=2)
                    print(f"Saved signals to {signals_path}")
                except Exception as e:
                    print(f"{ticker}: Failed to save signals: {e}")
        except Exception as e:
            print(f"{ticker}: Unexpected error during scan: {e}")
