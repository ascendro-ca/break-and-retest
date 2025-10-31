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
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import argparse
import os
import json
from pathlib import Path

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds

# Load configuration
def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Default config if file doesn't exist
        return {
            "tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"],
            "timeframe_5m": "5m",
            "lookback": "2d",
            "session_start": "09:30",
            "session_end": "16:00",
            "market_open_minutes": 90
        }

CONFIG = load_config()
TICKERS = CONFIG["tickers"]
TIMEFRAME = CONFIG["timeframe_5m"]
LOOKBACK = CONFIG["lookback"]
SESSION_START = CONFIG["session_start"]
SESSION_END = CONFIG["session_end"]
MARKET_OPEN_MINUTES = CONFIG["market_open_minutes"]

# --- Helper Functions ---
def get_intraday_data(ticker, retries=DEFAULT_RETRIES, retry_delay=DEFAULT_RETRY_DELAY, timeframe=TIMEFRAME, lookback=LOOKBACK):
    """Download intraday data with simple retry/backoff. Returns a DataFrame (may be empty).

    Always returns a DataFrame (possibly empty) instead of raising so callers can handle missing data.
    """
    attempt = 0
    last_exc = None
    while attempt < retries:
        try:
            df = yf.download(ticker, period=lookback, interval=timeframe, progress=False, auto_adjust=True)
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

def is_strong_body(row):
    body = abs(row["Close"] - row["Open"])
    range_ = row["High"] - row["Low"]
    return body >= 0.6 * range_  # strong body: >=60% of range

def scan_ticker(ticker, timeframe=TIMEFRAME, lookback=LOOKBACK, retries=DEFAULT_RETRIES, retry_delay=DEFAULT_RETRY_DELAY, market_open_minutes=MARKET_OPEN_MINUTES):
    df = get_intraday_data(ticker, retries=retries, retry_delay=retry_delay, timeframe=timeframe, lookback=lookback)
    if df is None or df.empty:
        print(f"{ticker}: No data returned (empty). Skipping.")
        return [], pd.DataFrame()
    if len(df) < 20:
        print(f"{ticker}: Not enough data for scan.")
        return [], df
    # Use first 5-min candle after market open as range
    or_high, or_low = find_first_candle_range(df)
    if or_high is None or or_low is None:
        print(f"{ticker}: No opening range found.")
        return [], df
    # Restrict detection to first 90 min after open
    session = df[df["Datetime"].dt.strftime("%H:%M") >= SESSION_START]
    if len(session) == 0:
        print(f"{ticker}: No session data.")
        return [], df
    start_time = session["Datetime"].iloc[0]
    end_time = start_time + timedelta(minutes=MARKET_OPEN_MINUTES)
    scan_df = session[(session["Datetime"] >= start_time) & (session["Datetime"] < end_time)].copy()
    if len(scan_df) < 10:
        print(f"{ticker}: Not enough data in first {market_open_minutes} min.")
        return [], scan_df
    # Compute rolling volume mean for above-average checks
    scan_df["vol_ma"] = scan_df["Volume"].rolling(window=10, min_periods=1).mean()
    signals = []
    lvl_high = or_high
    lvl_low = or_low
    # --- 1. Breakout Detection ---
    for i in range(1, len(scan_df)-2):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i-1]
        # Breakout up: breaks opening range high
        breakout_up = (
            prev["High"] <= lvl_high and
            row["High"] > lvl_high and
            is_strong_body(row) and
            row["Volume"] > row["vol_ma"] * 1.2 and
            row["Close"] > lvl_high
        )
        # Breakout down: breaks opening range low
        breakout_down = (
            prev["Low"] >= lvl_low and
            row["Low"] < lvl_low and
            is_strong_body(row) and
            row["Volume"] > row["vol_ma"] * 1.2 and
            row["Close"] < lvl_low
        )
        if breakout_up or breakout_down:
            # --- 2. Re-Test Detection ---
            re_test_idx = i+1
            if re_test_idx >= len(scan_df):
                continue
            re_test = scan_df.iloc[re_test_idx]
            # Price returns to level
            returns_to_level = (
                (breakout_up and abs(re_test["Low"] - lvl_high) < 0.1) or
                (breakout_down and abs(re_test["High"] - lvl_low) < 0.1)
            )
            # Tight candle, lower volume
            tight_candle = (re_test["High"] - re_test["Low"] < 0.5 * (row["High"] - row["Low"]))
            lower_vol = re_test["Volume"] < row["Volume"]
            if returns_to_level and tight_candle and lower_vol:
                # --- 3. Ignition Candle ---
                ign_idx = i+2
                if ign_idx >= len(scan_df):
                    continue
                ign = scan_df.iloc[ign_idx]
                # Strong body, breaks re-test high/low, volume increases
                ignition = (
                    is_strong_body(ign) and
                    (
                        (breakout_up and ign["High"] > re_test["High"]) or
                        (breakout_down and ign["Low"] < re_test["Low"])
                    ) and
                    ign["Volume"] > re_test["Volume"]
                )
                if ignition:
                    # --- 4. Entry, Stop, Target ---
                    entry = ign["High"] if breakout_up else ign["Low"]
                    stop = re_test["Low"] - 0.05 if breakout_up else re_test["High"] + 0.05
                    risk = abs(entry - stop)
                    target = entry + 2*risk if breakout_up else entry - 2*risk
                    signals.append({
                        "ticker": ticker,
                        "datetime": ign["Datetime"],
                        "direction": "long" if breakout_up else "short",
                        "level": lvl_high if breakout_up else lvl_low,
                        "entry": entry,
                        "stop": stop,
                        "target": target,
                        "risk": risk,
                        "vol_breakout": row["Volume"],
                        "vol_retest": re_test["Volume"],
                        "vol_ignition": ign["Volume"]
                    })
    # --- Print Results ---
    if signals:
        for sig in signals:
            print(f"{sig['ticker']} {sig['datetime']} {sig['direction'].upper()} | Level: {sig['level']:.2f} Entry: {sig['entry']:.2f} Stop: {sig['stop']:.2f} Target: {sig['target']:.2f} Vol(Break): {sig['vol_breakout']} Vol(Retest): {sig['vol_retest']} Vol(Ign): {sig['vol_ignition']}")
    else:
        print(f"{ticker}: No setups found.")

    # Return signals and the scan dataframe for downstream use (visualization, backtesting)
    return signals, scan_df


def scan_dataframe(df, market_open_minutes=MARKET_OPEN_MINUTES):
    """Scan a pre-loaded intraday DataFrame (same detection logic as scan_ticker).

    Expects a DataFrame with columns: Datetime, Open, High, Low, Close, Volume.
    Returns (signals, scan_df) where scan_df is the restricted first-N-minutes session slice.
    """
    if df is None or df.empty:
        return [], pd.DataFrame()
    # Ensure Datetime is datetime
    df = df.copy()
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    # Use first 5-min candle after market open as range
    session = df[df["Datetime"].dt.strftime("%H:%M") >= SESSION_START]
    if len(session) == 0:
        return [], pd.DataFrame()
    or_high, or_low = None, None
    first = session.iloc[0]
    or_high, or_low = first.get("High"), first.get("Low")
    if or_high is None or or_low is None:
        return [], pd.DataFrame()
    start_time = session["Datetime"].iloc[0]
    end_time = start_time + timedelta(minutes=market_open_minutes)
    scan_df = session[(session["Datetime"] >= start_time) & (session["Datetime"] < end_time)].copy()
    if len(scan_df) < 1:
        return [], scan_df
    scan_df["vol_ma"] = scan_df["Volume"].rolling(window=10, min_periods=1).mean()

    signals = []
    lvl_high = or_high
    lvl_low = or_low
    for i in range(1, len(scan_df)-2):
        row = scan_df.iloc[i]
        prev = scan_df.iloc[i-1]
        breakout_up = (
            prev["High"] <= lvl_high and
            row["High"] > lvl_high and
            is_strong_body(row) and
            row["Volume"] > row["vol_ma"] * 1.2 and
            row["Close"] > lvl_high
        )
        breakout_down = (
            prev["Low"] >= lvl_low and
            row["Low"] < lvl_low and
            is_strong_body(row) and
            row["Volume"] > row["vol_ma"] * 1.2 and
            row["Close"] < lvl_low
        )
        if breakout_up or breakout_down:
            re_test_idx = i+1
            if re_test_idx >= len(scan_df):
                continue
            re_test = scan_df.iloc[re_test_idx]
            returns_to_level = (
                (breakout_up and abs(re_test["Low"] - lvl_high) < 0.1) or
                (breakout_down and abs(re_test["High"] - lvl_low) < 0.1)
            )
            tight_candle = (re_test["High"] - re_test["Low"] < 0.5 * (row["High"] - row["Low"]))
            lower_vol = re_test["Volume"] < row["Volume"]
            if returns_to_level and tight_candle and lower_vol:
                ign_idx = i+2
                if ign_idx >= len(scan_df):
                    continue
                ign = scan_df.iloc[ign_idx]
                ignition = (
                    is_strong_body(ign) and
                    (
                        (breakout_up and ign["High"] > re_test["High"]) or
                        (breakout_down and ign["Low"] < re_test["Low"]) 
                    ) and
                    ign["Volume"] > re_test["Volume"]
                )
                if ignition:
                    entry = ign["High"] if breakout_up else ign["Low"]
                    stop = re_test["Low"] - 0.05 if breakout_up else re_test["High"] + 0.05
                    risk = abs(entry - stop)
                    target = entry + 2*risk if breakout_up else entry - 2*risk
                    signals.append({
                        "direction": "long" if breakout_up else "short",
                        "entry": entry,
                        "stop": stop,
                        "target": target,
                        "risk": risk,
                        "vol_breakout": row["Volume"],
                        "vol_retest": re_test["Volume"],
                        "vol_ignition": ign["Volume"],
                        "datetime": ign["Datetime"],
                        "level": lvl_high if breakout_up else lvl_low,
                    })
    return signals, scan_df

def _parse_tickers(s: str):
    return [t.strip().upper() for t in s.split(",")] if s else TICKERS


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="5-min Break & Re-Test Scalp Strategy Scanner (CLI)")
    p.add_argument("--tickers", default=",".join(TICKERS), help="Comma-separated tickers to scan (default: common list)")
    p.add_argument("--timeframe", default=TIMEFRAME)
    p.add_argument("--lookback", default=LOOKBACK)
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    p.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY)
    p.add_argument("--open-minutes", type=int, default=MARKET_OPEN_MINUTES)
    args = p.parse_args()

    tickers = _parse_tickers(args.tickers)
    print("\n=== 5-Min Break & Re-Test Scalp Strategy Scanner (CLI) ===\n")
    for ticker in tickers:
        try:
            signals, scan_df = scan_ticker(ticker, timeframe=args.timeframe, lookback=args.lookback, retries=args.retries, retry_delay=args.retry_delay, market_open_minutes=args.open_minutes)
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

if __name__ == "__main__":
    print("\n=== 5-Min Break & Re-Test Scalp Strategy Scanner ===\n")
    for ticker in TICKERS:
        scan_ticker(ticker)
