#!/usr/bin/env python3
"""
This script has been removed. The project now uses Stockdata.org for intraday data.

Please use stockdata_test.py instead.
"""

# Early exit if executed directly
if __name__ == "__main__":
        import sys
        print("twelvedata_test.py has been removed. Use stockdata_test.py instead.")
        sys.exit(0)

import argparse  # legacy (unused; kept for compatibility)
import json  # legacy
import os  # legacy
import time  # legacy
from datetime import datetime, timedelta  # legacy
from typing import Dict, List, Tuple, Optional  # legacy

import requests  # legacy
import pandas as pd  # legacy
from pathlib import Path  # legacy

BASE_URL = "https://api.twelvedata.com/time_series"
DEFAULT_CACHE_DIR = Path("cache")


def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    else:
        return {"tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"]}


CONFIG = load_config()
DEFAULT_TICKERS = CONFIG["tickers"]


def rate_limit_sleep(last_call_ts: List[float], max_per_minute: int) -> None:
    """Ensure we don't exceed max_per_minute calls per 60 seconds.

    We keep timestamps of recent calls and sleep if needed so that the
    number of calls within the last 60s stays <= max_per_minute.
    """
    now = time.time()
    window = 60.0
    # drop timestamps older than 60 seconds
    last_call_ts[:] = [t for t in last_call_ts if now - t < window]
    if len(last_call_ts) >= max_per_minute:
        # Sleep until we fall under the limit
        earliest = min(last_call_ts)
        sleep_for = window - (now - earliest) + 0.1
        if sleep_for > 0:
            time.sleep(sleep_for)


def _cache_path(cache_dir: Path, symbol: str, date_str: str, interval: str) -> Path:
    sym_dir = cache_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    return sym_dir / f"{date_str}_{interval}.csv"


def _load_cached_day(
    cache_dir: Path, symbol: str, date_str: str, interval: str
) -> Optional[pd.DataFrame]:
    path = _cache_path(cache_dir, symbol, date_str, interval)
    if path.exists():
        try:
            return pd.read_csv(path, parse_dates=["Datetime"], dtype={"Volume": float})
        except Exception:
            return None
    return None


def _save_day(
    cache_dir: Path, symbol: str, date_str: str, interval: str, values: List[Dict]
) -> None:
    # Convert Twelve Data values to DataFrame with our standard columns
    if not values:
        # Save an empty file to mark day as checked (optional: skip saving)
        df = pd.DataFrame(columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    else:
        df = pd.DataFrame(values)
        # Normalize column names and types
        df.rename(
            columns={
                "datetime": "Datetime",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            },
            inplace=True,
        )
        # Ensure proper types
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Sort ascending
        df = df.sort_values("Datetime")

    out_path = _cache_path(cache_dir, symbol, date_str, interval)
    df.to_csv(out_path, index=False)


def fetch_timeseries(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    apikey: str,
    timezone: str = "America/New_York",
    max_per_minute: int = 8,
) -> List[Dict]:
    """Fetch OHLCV from Twelve Data day-by-day with caching to avoid wasting credits.

    - For each day in [start, end], check cache first.
    - If missing, call API for that single day and save to cache.
    - Merge all values and return as a single ascending list of dicts.
    """
    cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(exist_ok=True)

    last_call_ts: List[float] = []
    all_values: List[Dict] = []

    cur = start
    day_idx = 0
    while cur <= end:
        day_idx += 1
        day_str = cur.strftime("%Y-%m-%d")
        cached = _load_cached_day(cache_dir, symbol, day_str, interval)
        if cached is not None and not cached.empty:
            # Append cached values
            for _, row in cached.iterrows():
                all_values.append(
                    {
                        "datetime": row["Datetime"].isoformat(),
                        "open": row.get("Open"),
                        "high": row.get("High"),
                        "low": row.get("Low"),
                        "close": row.get("Close"),
                        "volume": row.get("Volume"),
                    }
                )
            print(f"Cache hit {symbol} {interval} {day_str}: {len(cached)} rows")
            cur += timedelta(days=1)
            continue

        # Not cached: fetch for this single day (00:00:00 to 23:59:59)
        rate_limit_sleep(last_call_ts, max_per_minute)
        cstart = datetime.strptime(day_str + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        cend = datetime.strptime(day_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        params = {
            "symbol": symbol,
            "interval": interval,
            "start_date": cstart.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": cend.strftime("%Y-%m-%d %H:%M:%S"),
            "apikey": apikey,
            "timezone": timezone,
            "outputsize": 5000,
            "format": "JSON",
        }
        resp = requests.get(BASE_URL, params=params, timeout=30)
        last_call_ts.append(time.time())
        if resp.status_code != 200:
            raise RuntimeError(
                f"HTTP {resp.status_code} for {symbol} {interval} {day_str}: {resp.text}"
            )
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            code = data.get("code")
            message = data.get("message")
            raise RuntimeError(f"API error for {symbol} {interval} {day_str}: {code} {message}")
        values = data.get("values", []) if isinstance(data, dict) else []
        # Save to cache as CSV for this day
        _save_day(cache_dir, symbol, day_str, interval, values)
        # Extend all_values
        all_values.extend(values)
        print(f"Fetched {symbol} {interval} {day_str}: {len(values)} rows (saved to cache)")

        cur += timedelta(days=1)

    # Sort ascending by datetime
    all_values.sort(key=lambda x: x.get("datetime", ""))
    return all_values


def summarize(values: List[Dict]) -> Tuple[int, str, str]:
    if not values:
        return 0, "", ""
    return (
        len(values),
        values[0].get("datetime", ""),
        values[-1].get("datetime", ""),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Test Twelve Data API for 1m/5m across a month",
        epilog=f"Default symbols from config.json: {', '.join(DEFAULT_TICKERS)}",
    )
    parser.add_argument(
        "--apikey", help="Twelve Data API key (or set TWELVE_DATA_API_KEY/TWELVEDATA_API_KEY)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Symbols to test (default: from config.json)",
    )
    parser.add_argument(
        "--intervals", nargs="+", default=["1min", "5min"], help="Intervals to test"
    )
    parser.add_argument("--start", default="2025-09-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2025-09-30", help="End date YYYY-MM-DD")
    parser.add_argument("--timezone", default="America/New_York", help="Timezone for timestamps")
    parser.add_argument("--max-per-minute", type=int, default=8, help="Max API calls per minute")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Cache directory")
    args = parser.parse_args()

    # Accept either TWELVE_DATA_API_KEY or TWELVEDATA_API_KEY
    apikey = (
        args.apikey or os.environ.get("TWELVE_DATA_API_KEY") or os.environ.get("TWELVEDATA_API_KEY")
    )
    if not apikey:
        raise SystemExit("Provide --apikey or set TWELVE_DATA_API_KEY / TWELVEDATA_API_KEY.")

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(exist_ok=True)

    print(
        f"Testing Twelve Data time_series for {', '.join(args.symbols)}; "
        f"intervals: {', '.join(args.intervals)}; range: {args.start} to {args.end}\n"
        f"Rate limit: <= {args.max_per_minute} calls/min; Credit limit: 1 credit per call (<=5000 rows)."
    )

    for sym in args.symbols:
        for interval in args.intervals:
            try:
                vals = fetch_timeseries(
                    symbol=sym,
                    interval=interval,
                    start=start_dt,
                    end=end_dt,
                    apikey=apikey,
                    timezone=args.timezone,
                    max_per_minute=args.max_per_minute,
                )
            except Exception as e:
                print(f"ERROR fetching {sym} {interval}: {e}")
                continue

            n, first_dt, last_dt = summarize(vals)
            print(f"Summary {sym} {interval}: rows={n}, first={first_dt}, last={last_dt}")

    print("\nDone.")


if __name__ == "__main__":
    main()
