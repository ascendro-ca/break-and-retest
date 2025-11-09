#!/usr/bin/env python3
"""
Repair 5m cache by resampling from 1m data for a date range.

Usage:
  python repair_cache_5m_from_1m.py --symbols UBER --start 2025-01-01 --end 2025-01-31
  python repair_cache_5m_from_1m.py --symbols AAPL MSFT --start 2025-01-02 --end 2025-01-10

This overwrites cache/<SYMBOL>/<YYYY-MM-DD>_5m.csv using 1m source.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from cache_utils import DEFAULT_CACHE_DIR, load_cached_day, save_day


def resample_one_day(symbol: str, date_str: str, cache_dir: Path) -> bool:
    df1 = load_cached_day(cache_dir, symbol, date_str, "1m")
    if df1 is None or df1.empty:
        print(f"[{symbol} {date_str}] missing 1m; skip")
        return False
    df1 = df1.sort_values("Datetime").set_index("Datetime")
    rs = (
        df1[["Open", "High", "Low", "Close", "Volume"]]
        .resample("5min", label="right", closed="right")
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna(subset=["Open", "High", "Low", "Close"])
        .reset_index()
    )
    # Conform to save_day expected schema
    out = rs.rename(
        columns={
            "Datetime": "datetime",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).to_dict(orient="records")
    save_day(cache_dir, symbol, date_str, "5m", out)
    print(f"[{symbol} {date_str}] wrote 5m ({len(out)} rows) from 1m")
    return True


def main():
    p = argparse.ArgumentParser(description="Repair 5m cache by resampling 1m")
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    args = p.parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")
    cache_dir = Path(args.cache_dir)

    day = start_dt
    while day <= end_dt:
        if day.weekday() < 5:  # weekdays only
            date_str = day.strftime("%Y-%m-%d")
            for sym in args.symbols:
                try:
                    resample_one_day(sym, date_str, cache_dir)
                except Exception as e:
                    print(f"[{sym} {date_str}] error: {e}")
        day += timedelta(days=1)


if __name__ == "__main__":
    main()
