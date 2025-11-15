#!/usr/bin/env python3
"""
Repair script to fill missing 1-minute bars within the regular session for a given
symbol and date range. It forward-fills OHLC from the previous close and sets Volume=0
for the synthesized rows, preserving UTC storage.

Usage examples:
  python repair_cache_1m_fill_gaps.py --symbols SPOT --start 2025-11-10 --end 2025-11-10

Notes:
  - Only fills gaps between session_start_et and session_end_et from config.json
  - Leaves existing rows untouched; only inserts missing timestamps
  - After repair, you may want to regenerate 5m from 1m for those dates
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from cache_utils import DEFAULT_CACHE_DIR, load_cached_day, save_day


def load_config():
    cfg_path = Path(__file__).parent / "config.json"
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            return json.load(f)
    return {}


def fill_1m_gaps_for_day(
    symbol: str, date_str: str, session_start_et: str, session_end_et: str
) -> bool:
    """Fill intra-session 1m gaps for symbol/date. Returns True if a change was saved."""
    df = load_cached_day(DEFAULT_CACHE_DIR, symbol, date_str, "1m")
    if df is None or df.empty:
        print(f"{symbol} {date_str} 1m: missing file; skip")
        return False

    # Convert to America/New_York for session window checks
    ser = pd.to_datetime(df["Datetime"], errors="coerce")
    if getattr(ser.dt, "tz", None) is None:
        ser = ser.dt.tz_localize("UTC")
    ser = ser.dt.tz_convert("America/New_York")
    df = df.copy()
    df["ET"] = ser

    # Build full minute index between session bounds (inclusive of start, exclusive of end+1)
    start_dt = pd.Timestamp(f"{date_str} {session_start_et}", tz="America/New_York")
    end_dt = pd.Timestamp(f"{date_str} {session_end_et}", tz="America/New_York")
    full_idx = pd.date_range(start_dt, end_dt, freq="1min", inclusive="both")

    # Reindex to full minute grid
    keyed = df.set_index("ET").sort_index()
    reindexed = keyed.reindex(full_idx)

    # Identify missing rows to be synthesized
    missing_mask = (
        reindexed["Open"].isna()
        | reindexed["High"].isna()
        | reindexed["Low"].isna()
        | reindexed["Close"].isna()
    )

    if not missing_mask.any():
        print(f"{symbol} {date_str} 1m: no gaps detected within session")
        return False

    # Forward-fill OHLC from previous Close; if none, use first non-null Close in window
    # First propagate Close, then set O/H/L to that value
    reindexed["Close"] = reindexed["Close"].ffill()
    for col in ["Open", "High", "Low"]:
        reindexed[col] = reindexed[col].fillna(reindexed["Close"])
    # Volume for synthesized rows -> 0
    reindexed["Volume"] = reindexed["Volume"].fillna(0.0)

    # Sanity: after fill, ensure no NaNs remain in OHLC within session
    if reindexed[["Open", "High", "Low", "Close"]].isna().any().any():
        print(f"{symbol} {date_str} 1m: unable to fully fill OHLC; skip write")
        return False

    # Restore UTC timestamps for saving
    reindexed = reindexed.reset_index().rename(columns={"index": "ET"})
    reindexed["Datetime"] = pd.to_datetime(reindexed["ET"]).dt.tz_convert("UTC")
    out = reindexed[["Datetime", "Open", "High", "Low", "Close", "Volume"]]

    save_day(DEFAULT_CACHE_DIR, symbol, date_str, "1m", out)
    print(f"{symbol} {date_str} 1m: filled {int(missing_mask.sum())} gaps")
    return True


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description="Fill intra-session 1m gaps with zero-volume forward-filled bars"
    )
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to repair")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--session-start-et", default=cfg.get("session_start_et", "09:30"))
    parser.add_argument("--session-end-et", default=cfg.get("session_end_et", "16:00"))
    args = parser.parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    changed = 0
    day = start_dt
    while day <= end_dt:
        if day.weekday() < 5:  # weekdays only
            dstr = day.strftime("%Y-%m-%d")
            for sym in args.symbols:
                if fill_1m_gaps_for_day(sym, dstr, args.session_start_et, args.session_end_et):
                    changed += 1
        day += timedelta(days=1)

    print(f"Done. Days changed: {changed}")


if __name__ == "__main__":
    main()
