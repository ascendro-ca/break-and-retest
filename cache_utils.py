from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

DEFAULT_CACHE_DIR = Path("cache")


def canonical_interval(interval: str) -> str:
    i = (interval or "").lower()
    if i in {"1m", "1min", "minute", "m", "min"}:
        return "1m"
    if i in {"5m", "5min"}:
        return "5m"
    if i in {"1h", "60min", "hour", "h"}:
        return "1h"
    return i


def get_cache_path(cache_dir: Path, symbol: str, date_str: str, interval: str) -> Path:
    symbol_dir = cache_dir / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    return symbol_dir / f"{date_str}_{interval}.csv"


def load_cached_day(
    cache_dir: Path, symbol: str, date_str: str, interval: str
) -> Optional[pd.DataFrame]:
    canon = canonical_interval(interval)
    path = get_cache_path(cache_dir, symbol, date_str, canon)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["Datetime"], dtype={"Volume": float})
        # standardize columns and timezone to America/New_York
        req = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
        if all(c in df.columns for c in req):
            df = df[req].copy()
            # Ensure tz-aware in America/New_York for consistency with market hours
            ny = ZoneInfo("America/New_York")
            # Convert to datetime first (if parse_dates missed or mixed types)
            df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
            if getattr(df["Datetime"].dt, "tz", None) is None:
                df["Datetime"] = df["Datetime"].dt.tz_localize(ny)
            else:
                df["Datetime"] = df["Datetime"].dt.tz_convert(ny)
            df = df.sort_values("Datetime")
        return df
    except Exception:
        return None


def _normalize_df_like(values: Union[pd.DataFrame, List[Dict]]) -> pd.DataFrame:
    if isinstance(values, pd.DataFrame):
        df = values.copy()
    else:
        df = pd.DataFrame(values or [])
    if df.empty:
        return pd.DataFrame(columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])

    # rename common variants
    lower = {c.lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in lower:
                return lower[n]
        return None

    tcol = pick("datetime", "date", "time")
    ocol = pick("open")
    hcol = pick("high")
    lcol = pick("low")
    ccol = pick("close")
    vcol = pick("volume")
    ren = {}
    if tcol:
        ren[tcol] = "Datetime"
    if ocol:
        ren[ocol] = "Open"
    if hcol:
        ren[hcol] = "High"
    if lcol:
        ren[lcol] = "Low"
    if ccol:
        ren[ccol] = "Close"
    if vcol:
        ren[vcol] = "Volume"
    df = df.rename(columns=ren)

    if "Datetime" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
        # Normalize timezone to America/New_York
        ny = ZoneInfo("America/New_York")
        if getattr(df["Datetime"].dt, "tz", None) is None:
            df["Datetime"] = df["Datetime"].dt.tz_localize(ny)
        else:
            df["Datetime"] = df["Datetime"].dt.tz_convert(ny)
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    cols = [c for c in ["Datetime", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols]
    df = df.sort_values("Datetime")
    return df


def save_day(
    cache_dir: Path,
    symbol: str,
    date_str: str,
    interval: str,
    values: Union[pd.DataFrame, List[Dict]],
) -> Path:
    # Normalize interval to canonical write form (1m/5m/1h)
    i = (interval or "").lower()
    if i in {"1m", "1min", "minute", "m", "min"}:
        write_int = "1m"
    elif i in {"5m", "5min"}:
        write_int = "5m"
    elif i in {"1h", "60min", "hour", "h"}:
        write_int = "1h"
    else:
        write_int = interval

    df = _normalize_df_like(values)
    out_path = get_cache_path(cache_dir, symbol, date_str, write_int)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return out_path


# -----------------------------
# Cache integrity verification
# -----------------------------


def _infer_step_seconds(interval: str) -> Optional[int]:
    i = canonical_interval(interval)
    if i == "1m":
        return 60
    if i == "5m":
        return 300
    if i == "1h":
        return 3600
    return None


def integrity_check_day(
    cache_dir: Path,
    symbol: str,
    date_str: str,
    interval: str,
    check_alignment: bool = True,
) -> Dict:
    """Validate a single cached day file and return a report.

    Returns dict with keys: symbol, date, interval, status, errors, warnings, stats
    """
    report = {
        "symbol": symbol,
        "date": date_str,
        "interval": canonical_interval(interval),
        "status": "ok",
        "errors": [],
        "warnings": [],
        "stats": {},
        "path": str(get_cache_path(cache_dir, symbol, date_str, canonical_interval(interval))),
    }

    df = load_cached_day(cache_dir, symbol, date_str, interval)
    if df is None:
        report["status"] = "error"
        report["errors"].append("missing-file")
        return report

    # Basic schema
    req_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in req_cols):
        report["status"] = "error"
        report["errors"].append("missing-columns")
        report["stats"]["present_cols"] = [c for c in df.columns]
        return report

    nrows = int(len(df))
    report["stats"]["rows"] = nrows
    if nrows == 0:
        report["status"] = "error"
        report["errors"].append("empty-file")
        return report

    # Ensure tz-aware America/New_York and sorting
    try:
        ser = pd.to_datetime(df["Datetime"], errors="coerce")
        if getattr(ser.dt, "tz", None) is None:
            ser = ser.dt.tz_localize(ZoneInfo("America/New_York"))
        else:
            ser = ser.dt.tz_convert(ZoneInfo("America/New_York"))
    except Exception:
        report["status"] = "error"
        report["errors"].append("invalid-datetime")
        return report

    # Multi-day contamination: all rows must match file date
    dates = ser.dt.strftime("%Y-%m-%d").unique().tolist()
    report["stats"]["unique_dates"] = dates
    if len(dates) != 1 or (dates and dates[0] != date_str):
        report["status"] = "error"
        report["errors"].append("multi-day-file")

    # Duplicates and order
    dup_count = int(ser.duplicated().sum())
    if dup_count > 0:
        report["status"] = "error"
        report["errors"].append(f"duplicate-timestamps:{dup_count}")
    if not ser.is_monotonic_increasing:
        report["warnings"].append("not-sorted-ascending")

    # OHLC sanity
    o = pd.to_numeric(df["Open"], errors="coerce")
    h = pd.to_numeric(df["High"], errors="coerce")
    lo = pd.to_numeric(df["Low"], errors="coerce")
    c = pd.to_numeric(df["Close"], errors="coerce")
    v = pd.to_numeric(df["Volume"], errors="coerce")
    nan_ohlc = int((o.isna() | h.isna() | lo.isna() | c.isna()).sum())
    if nan_ohlc > 0:
        report["status"] = "error"
        report["errors"].append(f"nan-ohlc:{nan_ohlc}")
    neg_vol = int((v < 0).sum()) if v.notna().any() else 0
    if neg_vol > 0:
        report["status"] = "error"
        report["errors"].append(f"negative-volume:{neg_vol}")
    # candle range sanity
    bad_hilo = int(((h < lo) | (h < o) | (h < c) | (lo > o) | (lo > c)).sum())
    if bad_hilo > 0:
        report["status"] = "error"
        report["errors"].append(f"inconsistent-ohlc:{bad_hilo}")

    # Cadence and gap estimation
    step = _infer_step_seconds(interval)
    if step is not None:
        diffs = ser.sort_values().diff().dropna().dt.total_seconds()
        # missing intervals where diff > step and an integer multiple of step
        missing = 0
        for d in diffs:
            try:
                if d > step and abs(d % step) < 1e-6:
                    missing += int(round(d / step - 1))
            except Exception:
                pass
        report["stats"]["missing_intervals_est"] = int(missing)
        if missing > 0:
            # Treat small gaps as warnings; large gaps as errors
            if missing >= 20:  # heuristically large
                report["status"] = "error"
                report["errors"].append(f"large-gaps:{missing}")
            else:
                report["warnings"].append(f"gaps:{missing}")

        # Alignment check for 5m timestamps to :00/:05/etc
        if check_alignment and canonical_interval(interval) == "5m":
            bad_align = int((ser.dt.minute % 5 != 0).sum())
            if bad_align > 0:
                report["warnings"].append(f"misaligned-5m-stamps:{bad_align}")

    # Fill in first/last for convenience
    try:
        report["stats"]["first"] = str(ser.min())
        report["stats"]["last"] = str(ser.max())
    except Exception:
        pass

    # Final status: error if any errors; warning if any warnings and not error
    if report["errors"]:
        report["status"] = "error"
    elif report["warnings"]:
        report["status"] = "warning"
    else:
        report["status"] = "ok"

    return report


def _list_symbol_dates(cache_dir: Path, symbol: str) -> List[Tuple[str, str]]:
    """List (date_str, interval) tuples present for a symbol in cache."""
    out: List[Tuple[str, str]] = []
    sym_dir = cache_dir / symbol
    if not sym_dir.exists() or not sym_dir.is_dir():
        return out
    for p in sym_dir.glob("*.csv"):
        name = p.name
        if "_" not in name:
            continue
        date_part, rest = name.split("_", 1)
        interval = rest.replace(".csv", "")
        out.append((date_part, interval))
    return sorted(out)


def integrity_check_range(
    cache_dir: Path,
    symbols: List[str],
    start_date: str,
    end_date: str,
    intervals: Optional[List[str]] = None,
    cross_interval: bool = True,
    skip_weekends: bool = False,
) -> Dict:
    """Run integrity checks for given symbols and inclusive date range.

    Returns summary with per-day issues.
    """
    from datetime import datetime, timedelta

    intervals = intervals or ["1m", "5m"]
    intervals = [canonical_interval(i) for i in intervals]

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    summary = {
        "checked_files": 0,
        "errors": 0,
        "warnings": 0,
        "missing_files": 0,
        "issues": [],
    }

    day = start_dt
    while day <= end_dt:
        if skip_weekends and day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        dstr = day.strftime("%Y-%m-%d")
        for sym in symbols:
            for itv in intervals:
                rep = integrity_check_day(cache_dir, sym, dstr, itv)
                # Count missing-file separately; don't also double-count as an error
                if rep["status"] == "error" and rep.get("errors") == ["missing-file"]:
                    summary["missing_files"] += 1
                else:
                    summary["checked_files"] += 1
                if rep["status"] == "error" and rep.get("errors") != ["missing-file"]:
                    summary["errors"] += 1
                    summary["issues"].append(rep)
                elif rep["status"] == "warning":
                    summary["warnings"] += 1
                    summary["issues"].append(rep)

            # Optional: cross-interval consistency (only when both exist)
            if cross_interval:
                rep_1m = load_cached_day(cache_dir, sym, dstr, "1m")
                rep_5m = load_cached_day(cache_dir, sym, dstr, "5m")
                if rep_1m is not None and rep_5m is not None:
                    try:
                        # Resample 1m to 5m boundaries and compare timestamps count
                        df1 = rep_1m.copy()
                        df1 = df1.sort_values("Datetime")
                        df1 = df1.set_index("Datetime")
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
                        )
                        rs = rs.reset_index()
                        # Compare on timestamp alignment and count
                        ts_5m = (
                            pd.to_datetime(rep_5m["Datetime"]).sort_values().reset_index(drop=True)
                        )
                        ts_rs = pd.to_datetime(rs["Datetime"]).sort_values().reset_index(drop=True)
                        if len(ts_5m) != len(ts_rs):
                            summary["warnings"] += 1
                            summary["issues"].append(
                                {
                                    "symbol": sym,
                                    "date": dstr,
                                    "interval": "xcheck-1m-5m",
                                    "status": "warning",
                                    "errors": [],
                                    "warnings": [
                                        f"5m-count-mismatch: cache={len(ts_5m)} rs1m={len(ts_rs)}"
                                    ],
                                    "stats": {},
                                }
                            )
                        else:
                            # Timestamp equality check (allow any order by sorting)
                            mismatch = int((ts_5m != ts_rs).sum())
                            if mismatch > 0:
                                summary["warnings"] += 1
                                summary["issues"].append(
                                    {
                                        "symbol": sym,
                                        "date": dstr,
                                        "interval": "xcheck-1m-5m",
                                        "status": "warning",
                                        "errors": [],
                                        "warnings": [f"5m-timestamp-mismatch:{mismatch}"],
                                        "stats": {},
                                    }
                                )
                    except Exception:
                        # Non-fatal
                        pass

        day += timedelta(days=1)

    return summary


def integrity_check_cache(
    cache_dir: Path,
    intervals: Optional[List[str]] = None,
    cross_interval: bool = True,
) -> Dict:
    """Scan the entire cache and return issues summary."""
    intervals = intervals or ["1m", "5m"]
    intervals = [canonical_interval(i) for i in intervals]

    symbols = [
        p.name
        for p in (cache_dir if isinstance(cache_dir, Path) else Path(cache_dir)).iterdir()
        if p.is_dir()
    ]

    summary = {
        "checked_files": 0,
        "errors": 0,
        "warnings": 0,
        "missing_files": 0,
        "issues": [],
    }

    for sym in symbols:
        entries = _list_symbol_dates(cache_dir, sym)
        by_date: Dict[str, List[str]] = {}
        for d, itv in entries:
            by_date.setdefault(d, []).append(itv)
        for d, present_itvs in by_date.items():
            for itv in intervals:
                if itv in present_itvs:
                    rep = integrity_check_day(cache_dir, sym, d, itv)
                    if rep["status"] == "error":
                        summary["errors"] += 1
                        summary["issues"].append(rep)
                    elif rep["status"] == "warning":
                        summary["warnings"] += 1
                        summary["issues"].append(rep)
                    summary["checked_files"] += 1
                else:
                    summary["missing_files"] += 1

            if cross_interval and all(x in present_itvs for x in ["1m", "5m"]):
                try:
                    df1 = load_cached_day(cache_dir, sym, d, "1m")
                    df5 = load_cached_day(cache_dir, sym, d, "5m")
                    if df1 is not None and df5 is not None:
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
                        ).reset_index()
                        ts_5 = pd.to_datetime(df5["Datetime"]).sort_values().reset_index(drop=True)
                        ts_rs = pd.to_datetime(rs["Datetime"]).sort_values().reset_index(drop=True)
                        if len(ts_5) != len(ts_rs) or int((ts_5 != ts_rs).sum()) > 0:
                            summary["warnings"] += 1
                            summary["issues"].append(
                                {
                                    "symbol": sym,
                                    "date": d,
                                    "interval": "xcheck-1m-5m",
                                    "status": "warning",
                                    "errors": [],
                                    "warnings": [
                                        f"5m-mismatch: cache={len(ts_5)} rs1m={len(ts_rs)}"
                                    ],
                                    "stats": {},
                                }
                            )
                except Exception:
                    pass

    return summary
