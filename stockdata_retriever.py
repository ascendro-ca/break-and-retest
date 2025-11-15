#!/usr/bin/env python3
"""
Stockdata.org intraday retriever for 1m and 5m OHLCV with daily caching.

- Uses env var STOCK_DATA_API_KEY (or --apikey) for auth
- Caches to cache/<SYMBOL>/<YYYY-MM-DD>_<interval>.csv to avoid wasting credits
- Fetches per day within the requested range (Basic tier supports ~1 year intraday)
- Prints summary counts and first/last timestamps to verify coverage

Notes for Basic tier (as of prompt):
- 2,500 requests/day, 1 symbol per intraday request, ~1 year of intraday data

Examples:
    python stockdata_retriever.py --symbols AAPL --intervals 1m 5m \
        --start 2025-10-15 --end 2025-10-16
    export STOCK_DATA_API_KEY=... \
        && python stockdata_retriever.py --symbols AAPL SPOT --intervals 1m \
        --start 2025-10-15 --end 2025-10-16
"""

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from cache_utils import (
    DEFAULT_CACHE_DIR as CU_DEFAULT_CACHE_DIR,
    load_cached_day as cu_load_cached_day,
    save_day as cu_save_day,
    integrity_check_cache,
)

BASE_URL = "https://api.stockdata.org/v1/data/intraday"
DEFAULT_CACHE_DIR = CU_DEFAULT_CACHE_DIR


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
    now = time.time()
    window = 60.0
    last_call_ts[:] = [t for t in last_call_ts if now - t < window]
    if len(last_call_ts) >= max_per_minute:
        earliest = min(last_call_ts)
        sleep_for = window - (now - earliest) + 0.1
        if sleep_for > 0:
            time.sleep(sleep_for)


def _load_cached_day(
    cache_dir: Path, symbol: str, date_str: str, interval: str
) -> Optional[pd.DataFrame]:
    return cu_load_cached_day(cache_dir, symbol, date_str, interval)


def _save_day(
    cache_dir: Path, symbol: str, date_str: str, interval: str, values: List[Dict]
) -> None:
    cu_save_day(cache_dir, symbol, date_str, interval, values)


def _days_per_call(requested_interval: str) -> int:
    """Return safe chunk size in days for a single API call.

    Per StockData.org docs, intraday interval options are minute|hour with max
    ranges per request of 7 days (minute) and 180 days (hour). We honor these
    hard limits and also keep calls under ~5,000 rows for safety.
    """
    # Normalize to canonical labels
    req = requested_interval.lower()
    if req in {"1min", "minute", "m", "min"}:
        # Minute data: fetch strictly one day per call to avoid pagination/truncation
        # and prevent accidental multi-day contamination of per-day cache files.
        return 1
    if req in {"hour", "1h", "60min", "h"}:
        # Hourly data: max 180 days
        return 180
    # Fallback: conservative default
    return 7


def _flatten_intraday_values(values: List[Dict]) -> List[Dict]:
    """Flatten StockData.org intraday payload into a simple OHLCV row list.

    Input shape examples:
    {"date": "2023-09-12T15:59:00.000Z", "ticker": "AAPL", "data": {"open":..., "high":..., ...}}
    {"datetime": "2023-09-12T15:59:00.000Z", "open":..., "high":..., ...}
    """
    flat: List[Dict] = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        dt = item.get("datetime") or item.get("date") or item.get("time")
        d = item.get("data") if isinstance(item.get("data"), dict) else item
        flat.append(
            {
                "datetime": dt,
                "open": d.get("open"),
                "high": d.get("high"),
                "low": d.get("low"),
                "close": d.get("close"),
                "volume": d.get("volume"),
            }
        )
    flat.sort(key=lambda x: x.get("datetime") or "")
    return flat


def _fetch_intraday_window(
    symbol: str, api_interval: str, date_from: datetime, date_to: datetime, apikey: str
) -> List[Dict]:
    """Call Stockdata.org intraday endpoint for a date window.

    Attempt with common parameter names. If the API returns an error body,
    raise a RuntimeError with details so we can adjust.
    """
    # Per docs: interval options are minute|hour; date formats support Y-m-d
    params = {
        "symbols": symbol,  # 1 symbol per intraday request per docs
        "interval": api_interval,  # 'minute' or 'hour'
        "date_from": date_from.strftime("%Y-%m-%d"),
        "date_to": date_to.strftime("%Y-%m-%d"),
        "sort": "asc",
        "api_token": apikey,
    }
    resp = requests.get(BASE_URL, params=params, timeout=45)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} {resp.text}")
    data = resp.json()
    # Common response shape: { 'data': [...], 'meta': {...} } or error { 'error': { ... } }
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"API error: {data.get('error')}")
    values: List[Dict] = []
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            values = data["data"]
        elif "values" in data and isinstance(data["values"], list):
            values = data["values"]
    return _flatten_intraday_values(values)


def _resample_minute_to_five(minute_rows: List[Dict]) -> List[Dict]:
    if not minute_rows:
        return []
    df = pd.DataFrame(minute_rows)
    if df.empty or "datetime" not in df.columns:
        return []

    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    # Check if timestamps are from API (mislabeled UTC that's actually ET)
    # or from cache (correct UTC)
    # If already in correct UTC (from cache), no conversion needed
    # If from API with 'Z' (mislabeled), needs ET→UTC conversion
    current_tz = getattr(df["datetime"].dt, "tz", None)

    if current_tz is not None and str(current_tz) == "UTC":
        # Check if this looks like API data (09:30 UTC) or cache data (13:30 UTC)
        # Market open in correct UTC should be around 13:30-14:30 depending on DST
        sample_hour = df["datetime"].iloc[0].hour if len(df) > 0 else 0

        if 8 <= sample_hour <= 11:
            # Looks like mislabeled API data (09:30 labeled as UTC but actually ET)
            df["datetime"] = df["datetime"].dt.tz_localize(None)
            df["datetime"] = df["datetime"].dt.tz_localize("America/New_York")
            df["datetime"] = df["datetime"].dt.tz_convert("UTC")
        # else: already correct UTC from cache, keep as-is
    elif current_tz is None:
        # Timezone-naive, assume it's from API and is actually ET
        df["datetime"] = df["datetime"].dt.tz_localize("America/New_York")
        df["datetime"] = df["datetime"].dt.tz_convert("UTC")

    df = df.set_index("datetime").sort_index()
    # Use label='right' so each 5T bar ends at its timestamp (e.g., 09:35 covers 09:31-09:35)
    ohlc = (
        df[["open", "high", "low", "close", "volume"]]
        .resample("5min", label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    ohlc = ohlc.reset_index()
    out = []
    for _, r in ohlc.iterrows():
        out.append(
            {
                "datetime": r["datetime"].isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]) if pd.notna(r["volume"]) else None,
            }
        )
    return out


def fetch_timeseries(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    apikey: str,
    timezone: str = "America/New_York",  # Deprecated: timestamps stored in UTC
    max_per_minute: int = 8,
) -> List[Dict]:
    cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(exist_ok=True)

    last_call_ts: List[float] = []
    all_values: List[Dict] = []

    # Normalize requested interval to our internal labels and API labels
    req = interval.lower()
    if req in {"1m", "1min", "minute", "m", "min"}:
        api_interval = "minute"
        cache_interval = "1m"
    elif req in {"5m", "5min"}:
        # We'll fetch minute and resample
        api_interval = "minute"
        cache_interval = "5m"
    elif req in {"hour", "1h", "60min", "h"}:
        api_interval = "hour"
        cache_interval = "1h"
    else:
        raise ValueError(f"Unsupported interval '{interval}'. Use 1min, 5min, or hour.")

    cur = start
    days_batch = _days_per_call(api_interval)

    # Helper to append from cache
    def append_cached(day_str: str) -> bool:
        # 1) Try direct cache for requested interval
        cached = _load_cached_day(cache_dir, symbol, day_str, cache_interval)
        if cached is not None and not cached.empty:
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
            print(f"Cache hit {symbol} {cache_interval} {day_str}: {len(cached)} rows")
            return True
        # 2) If requesting 5min and no 5min cache, try resample from 1min cache to avoid API calls
        if cache_interval == "5m":
            cached_1m = _load_cached_day(cache_dir, symbol, day_str, "1m")
            if cached_1m is not None and not cached_1m.empty:
                # Convert 1min cached day to rows and resample (preserve timezone)
                rows = [
                    {
                        "datetime": (
                            r["Datetime"].isoformat()
                            if hasattr(r["Datetime"], "isoformat")
                            else str(r["Datetime"])
                        ),
                        "open": r.get("Open"),
                        "high": r.get("High"),
                        "low": r.get("Low"),
                        "close": r.get("Close"),
                        "volume": r.get("Volume"),
                    }
                    for _, r in cached_1m.iterrows()
                ]
                resampled = _resample_minute_to_five(rows)
                _save_day(
                    cache_dir,
                    symbol,
                    day_str,
                    "5m",
                    pd.DataFrame(resampled)
                    .rename(
                        columns={
                            "datetime": "Datetime",
                            "open": "Open",
                            "high": "High",
                            "low": "Low",
                            "close": "Close",
                            "volume": "Volume",
                        }
                    )
                    .to_dict("records"),
                )
                for itm in resampled:
                    all_values.append(itm)
                print(f"Cache synth {symbol} 5m from 1m {day_str}: {len(resampled)} rows")
                return True
        return False

    while cur <= end:
        day_str = cur.strftime("%Y-%m-%d")
        if append_cached(day_str):
            cur += timedelta(days=1)
            continue

        # Determine batch window up to days_batch missing days
        run_start = cur
        run_end = min(end, run_start + timedelta(days=days_batch - 1))

        # Shrink if mid-run days are already cached
        tmp = run_start
        while tmp <= run_end:
            tmp_str = tmp.strftime("%Y-%m-%d")
            if _load_cached_day(cache_dir, symbol, tmp_str, cache_interval) is not None:
                run_end = tmp - timedelta(days=1)
                break
            tmp += timedelta(days=1)

        # If 5min requested, try to satisfy entirely from 1min cache before calling API
        if cache_interval == "5m":
            # Attempt to process each day in the window purely from 1min cache
            satisfied_all = True
            tmpd = run_start
            # temp_values: List[Dict] = []  # Removed unused variable
            while tmpd <= run_end:
                dstr = tmpd.strftime("%Y-%m-%d")
                if not append_cached(dstr):
                    satisfied_all = False
                    break
                tmpd += timedelta(days=1)
            if satisfied_all:
                # Already appended via cache; move to next window
                cur = run_end + timedelta(days=1)
                continue

        # Call API for [run_start, run_end] if not fully satisfied from cache
        rate_limit_sleep(last_call_ts, max_per_minute)
        minute_values = _fetch_intraday_window(symbol, api_interval, run_start, run_end, apikey)
        last_call_ts.append(time.time())

        # If 5min requested, resample; otherwise use as-is
        # Track provenance so we don't double-apply timezone conversions when saving.
        if cache_interval == "5m":
            use_values = _resample_minute_to_five(minute_values)
            use_values_from_resample = True
        else:
            use_values = minute_values
            use_values_from_resample = False

        # Save split per day for the requested cache interval
        if use_values:
            df = pd.DataFrame(use_values)
            if not df.empty:
                # Normalize timestamps to UTC for storage.
                # Rules:
                # - Resampled 5m values are already in correct UTC; do NOT re-interpret as ET.
                # - Raw API minute/hour values may be tz-aware ('Z') but actually represent ET;
                #   in that case, drop tz, localize to America/New_York, then convert to UTC.
                df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
                try:
                    tzinfo_present = getattr(df["datetime"].dt, "tz", None) is not None
                    if use_values_from_resample:
                        # Keep as UTC if tz-aware; if naive, assume already UTC and localize.
                        if tzinfo_present:
                            df["datetime"] = df["datetime"].dt.tz_convert("UTC")
                        else:
                            df["datetime"] = df["datetime"].dt.tz_localize("UTC")
                    else:
                        # Raw API path: treat tz-aware stamps as mislabeled ET ('Z');
                        # re-interpret in America/New_York then convert to UTC.
                        if tzinfo_present:
                            df["datetime"] = df["datetime"].dt.tz_localize(None)
                            df["datetime"] = df["datetime"].dt.tz_localize("America/New_York")
                            df["datetime"] = df["datetime"].dt.tz_convert("UTC")
                        else:
                            df["datetime"] = df["datetime"].dt.tz_localize("America/New_York")
                            df["datetime"] = df["datetime"].dt.tz_convert("UTC")
                except Exception:
                    pass
                # Use UTC date for grouping per-day files
                df["_date"] = df["datetime"].dt.strftime("%Y-%m-%d")
                for d, ddf in df.groupby("_date"):
                    _save_day(cache_dir, symbol, d, cache_interval, ddf.to_dict("records"))

        print(
            f"Fetched {symbol} {cache_interval} "
            f"{run_start.date()}..{run_end.date()}: "
            f"{len(use_values)} rows"
        )

        # Merge into all_values
        all_values.extend(use_values)

        cur = run_end + timedelta(days=1)

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


def _canonicalize_intervals(req_intervals: List[str]) -> List[str]:
    """Map user-provided interval labels to canonical cache labels.

    Supported canonical labels: 1m, 5m, 1h
    """
    out: List[str] = []
    for it in req_intervals:
        s = it.lower()
        if s in {"1m", "1min", "minute", "m", "min"}:
            c = "1m"
        elif s in {"5m", "5min"}:
            c = "5m"
        elif s in {"hour", "1h", "60min", "h"}:
            c = "1h"
        else:
            continue
        if c not in out:
            out.append(c)
    return out or ["1m", "5m"]


def _compute_cache_coverage(
    cache_dir: Path, intervals: List[str]
) -> Dict[str, Dict[str, Optional[str]]]:
    """Scan cache to find earliest and latest dates available per interval and overall.

    Returns a dict:
      {
        'overall': { 'start': 'YYYY-MM-DD'|None, 'end': 'YYYY-MM-DD'|None },
        '1m': { 'start': ..., 'end': ... },
        '5m': { ... },
        '1h': { ... }
      }
    """
    from datetime import date

    intervals = list(dict.fromkeys(intervals))  # dedupe, preserve order
    date_sets: Dict[str, set] = {it: set() for it in intervals}

    if not cache_dir.exists():
        per = {it: {"start": None, "end": None} for it in intervals}
        return {"overall": {"start": None, "end": None}, **per}

    for sym_dir in cache_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        for it in intervals:
            for f in sym_dir.glob(f"*_" + it + ".csv"):
                name = f.name
                try:
                    # Expect pattern: YYYY-MM-DD_<interval>.csv
                    dstr = name.split("_" + it)[0]
                    dstr = dstr.split("_")[0]  # left part before any other underscores
                    # validate
                    _ = date.fromisoformat(dstr)
                    date_sets[it].add(dstr)
                except Exception:
                    continue

    def _minmax(ds: set) -> Tuple[Optional[str], Optional[str]]:
        if not ds:
            return None, None
        s = sorted(ds)
        return s[0], s[-1]

    result: Dict[str, Dict[str, Optional[str]]] = {}
    overall_dates: set = set()
    for it, ds in date_sets.items():
        start, end = _minmax(ds)
        result[it] = {"start": start, "end": end}
        overall_dates |= ds
    ostart, oend = _minmax(overall_dates)
    result = {"overall": {"start": ostart, "end": oend}, **result}
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test Stockdata.org intraday API for 1m/5m with caching (unadjusted intraday)",
        epilog=f"Default symbols from config.json: {', '.join(DEFAULT_TICKERS)}",
    )
    parser.add_argument("--apikey", help="Stockdata.org API key (or set STOCK_DATA_API_KEY)")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Symbols to test (default: from config.json)",
    )
    parser.add_argument(
        "--intervals",
        nargs="+",
        default=["1m", "5m"],
        help="Intervals to test: 1m, 5m, or hour (hourly); 1min/5min also accepted",
    )
    parser.add_argument(
        "--normalize-cache",
        action="store_true",
        help="Duplicate legacy *_1min/*_5min cache files to *_1m/*_5m without overwriting",
    )
    parser.add_argument("--start", default="2025-10-15", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2025-10-16", help="End date YYYY-MM-DD")
    parser.add_argument("--timezone", default="America/New_York", help="Timezone for timestamps")
    parser.add_argument(
        "--max-per-minute",
        type=int,
        default=20,
        help="Max API calls per minute (Basic tier: 2,500 requests/day; default: 20)",
    )
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="Cache directory")
    # Cleanup options removed after cache migration to canonical 1m/5m
    parser.add_argument(
        "--repair-cache-splits",
        action="store_true",
        help=(
            "Scan canonical *_1m/*_5m files for multiple dates and split them into "
            "proper per-day files. Original file is backed up with .bak suffix."
        ),
    )
    args = parser.parse_args()

    # Optional: normalize cache and exit
    if args.normalize_cache:
        cache_dir = DEFAULT_CACHE_DIR
        normalized = 0
        skipped = 0
        for sym_dir in cache_dir.iterdir() if cache_dir.exists() else []:
            if not sym_dir.is_dir():
                continue
            for p in sym_dir.glob("*_1min.csv"):
                target = Path(str(p).replace("_1min.csv", "_1m.csv"))
                if not target.exists():
                    shutil.copy2(p, target)
                    normalized += 1
                else:
                    skipped += 1
            for p in sym_dir.glob("*_5min.csv"):
                target = Path(str(p).replace("_5min.csv", "_5m.csv"))
                if not target.exists():
                    shutil.copy2(p, target)
                    normalized += 1
                else:
                    skipped += 1
        print(f"Normalization complete: created {normalized}, skipped {skipped}")
        return

    # Optional: repair any canonical files that accidentally contain multiple days
    if args.repair_cache_splits:
        cache_dir = DEFAULT_CACHE_DIR
        repaired = 0
        checked = 0
        for sym_dir in cache_dir.iterdir() if cache_dir.exists() else []:
            if not sym_dir.is_dir():
                continue
            for canon in list(sym_dir.glob("*_1m.csv")) + list(sym_dir.glob("*_5m.csv")):
                checked += 1
                try:
                    df = pd.read_csv(canon, parse_dates=["Datetime"]) if canon.exists() else None
                except Exception:
                    continue
                if df is None or df.empty or "Datetime" not in df.columns:
                    continue
                # Determine date by America/New_York session date, not raw UTC date
                dtser = pd.to_datetime(df["Datetime"], errors="coerce")
                if getattr(dtser.dt, "tz", None) is None:
                    dtser = dtser.dt.tz_localize("UTC")
                dtser = dtser.dt.tz_convert("America/New_York")
                df["_date"] = dtser.dt.strftime("%Y-%m-%d")
                unique_dates = df["_date"].dropna().unique().tolist()
                if len(unique_dates) <= 1:
                    continue
                # Backup original
                backup = canon.with_suffix(canon.suffix + ".bak")
                try:
                    if not backup.exists():
                        shutil.copy2(canon, backup)
                except Exception:
                    pass
                # Split and overwrite per day
                for d, ddf in df.groupby("_date"):
                    cu_save_day(
                        cache_dir,
                        sym_dir.name,
                        d,
                        canon.name.split("_")[-1].replace(".csv", ""),
                        ddf,
                    )
                # Replace the original file with the proper day's data if present, else remove it
                # We choose to remove the oversized original after successful split
                try:
                    canon.unlink()
                except Exception:
                    pass
                repaired += 1
        print(f"Repair complete: repaired={repaired}, checked={checked}")
        return

    # Cleanup feature removed (legacy migration completed)

    apikey = args.apikey or os.environ.get("STOCK_DATA_API_KEY")
    if not apikey:
        raise SystemExit("Provide --apikey or set STOCK_DATA_API_KEY.")

    start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    end_dt = datetime.strptime(args.end, "%Y-%m-%d")

    print(
        f"Testing Stockdata.org intraday for {', '.join(args.symbols)}; "
        f"intervals: {', '.join(args.intervals)}; range: {args.start} to {args.end}\n"
        f"Rate limit: <= {args.max_per_minute} calls/min; "
        "Intraday interval options: minute|hour (we resample 5min)."
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

    # Run a full-cache integrity check at the end to catch any issues introduced
    try:
        summary = integrity_check_cache(
            DEFAULT_CACHE_DIR, intervals=["1m", "5m"], cross_interval=True
        )
        print(
            "\nIntegrity check (full cache): "
            f"checked={summary.get('checked_files')} errors={summary.get('errors')} "
            f"warnings={summary.get('warnings')} missing={summary.get('missing_files')}"
        )
        # Persist detailed report under logs/
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            logs_dir = Path(__file__).parent / "logs"
            logs_dir.mkdir(exist_ok=True)
            out_path = logs_dir / f"integrity_fullcache_{ts}.json"
            with open(out_path, "w") as f:
                json.dump(summary, f, indent=2)
            print(f"Integrity report saved to {out_path}")
        except Exception:
            pass
    except Exception as e:
        print(f"Integrity check failed to run: {e}")

    # Report cache coverage by date range
    try:
        intervals = _canonicalize_intervals(args.intervals)
        coverage = _compute_cache_coverage(Path(args.cache_dir), intervals)
        o = coverage.get("overall", {})
        print(
            "\nCache coverage (overall): " f"{o.get('start') or 'N/A'} to {o.get('end') or 'N/A'}"
        )
        for it in intervals:
            rng = coverage.get(it, {})
            print(f"  {it}: {rng.get('start') or 'N/A'} to {rng.get('end') or 'N/A'}")
    except Exception as e:
        print(f"Cache coverage computation failed: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
