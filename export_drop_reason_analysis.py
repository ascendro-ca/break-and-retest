#!/usr/bin/env python3
# ruff: noqa: I001
"""
Export drop-reason analysis between pipeline levels to CSV files.

Outputs to backtest_results/:
  - l0_to_l1_drop_reasons_overall_{ts}.csv
  - l0_to_l1_drop_reasons_by_symbol_{ts}.csv
  - l1_to_l2_drop_reasons_overall_{ts}.csv
  - l1_to_l2_drop_reasons_by_symbol_{ts}.csv

It auto-discovers the latest matching Level 0/1/2 JSONs for the same
symbols/start/end/grading by parsing filenames created by backtest.py.

Usage:
  python export_drop_reason_analysis.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
import re

import pandas as pd

from cache_utils import load_cached_day
from grading import get_grader
from trade_setup_pipeline import run_pipeline


BACKTEST_DIR = Path(__file__).parent / "backtest_results"


def _parse_filename_meta(path: Path) -> Optional[Dict[str, str]]:
    name = path.stem
    parts = name.split("_")
    if len(parts) < 6:
        return None
    level_part = parts[0]
    if not level_part.startswith("level"):
        return None
    try:
        level = int(level_part.replace("level", ""))
    except ValueError:
        return None
    symbols = parts[1]
    start = parts[2]
    end = parts[3]
    grading = parts[4]
    timestamp = "_".join(parts[5:])
    if not re.fullmatch(r"\d{8}", start):
        return None
    if not re.fullmatch(r"\d{8}", end):
        return None
    return {
        "level": level,
        "symbols": symbols,
        "start": start,
        "end": end,
        "grading": grading,
        "timestamp": timestamp,
    }


def _find_latest_pairs() -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Find latest Level 0, Level 1, and Level 2 files for same range.

    Returns (l0_path, l1_path, l2_path). l2_path may be None if not found.
    """
    files = list(BACKTEST_DIR.glob("level*_*.json"))
    l0_index: Dict[Tuple[str, str, str, str], Tuple[str, Path]] = {}
    l1_index: Dict[Tuple[str, str, str, str], Tuple[str, Path]] = {}
    l2_index: Dict[Tuple[str, str, str, str], Tuple[str, Path]] = {}

    for p in files:
        meta = _parse_filename_meta(p)
        if not meta:
            continue
        key = (meta["symbols"], meta["start"], meta["end"], meta["grading"])
        ts = meta["timestamp"]
        lvl = int(meta["level"])  # type: ignore[arg-type]
        idx = l0_index if lvl == 0 else l1_index if lvl == 1 else l2_index if lvl == 2 else None
        if idx is None:
            continue
        prev = idx.get(key)
        if not prev or ts > prev[0]:
            idx[key] = (ts, p)

    # Find any key present in L0 and L1; pick the one with freshest min(ts)
    common = set(l0_index.keys()) & set(l1_index.keys())
    if not common:
        return None, None, None
    best_key = None
    best_score = None
    for k in common:
        ts0, _ = l0_index[k]
        ts1, _ = l1_index[k]
        score = min(ts0, ts1)
        if best_key is None or score > best_score:
            best_key = k
            best_score = score
    assert best_key is not None
    l0_path = l0_index[best_key][1]
    l1_path = l1_index[best_key][1]
    l2_path = l2_index.get(best_key, (None, None))[1] if best_key in l2_index else None
    return l0_path, l1_path, l2_path


def _norm_ts(ts) -> str:
    t = pd.to_datetime(ts)
    if getattr(t, "tzinfo", None) is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.isoformat(timespec="seconds")


def _classify_l0_to_l1(l0_path: Path, l1_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    l0 = json.load(open(l0_path))
    l1 = json.load(open(l1_path))

    # Build set of L1 signal keys by (symbol, breakout_time_5m)
    l1_keys = set()
    for d in l1:
        sym = d.get("symbol")
        for s in d.get("signals", []) or []:
            l1_keys.add((sym, _norm_ts(s.get("breakout_time_5m"))))

    # Identify L0 candidates absent in L1
    dropped = []  # list of (sym, candidate)
    for d in l0:
        sym = d.get("symbol")
        for c in d.get("candidates", []) or []:
            key = (sym, _norm_ts(c.get("breakout_time_5m")))
            if key not in l1_keys:
                dropped.append((sym, c))

    reason_counts = {
        "no_ignition_close": 0,
        "entry_after_90min": 0,
        "missing_next_bar": 0,
    }
    per_symbol: Dict[str, Dict[str, int]] = {}

    for sym, c in dropped:
        per_symbol.setdefault(sym, {k: 0 for k in reason_counts})
        # Parse retest/breakout time
        rt = pd.to_datetime(c.get("datetime"))
        bt = pd.to_datetime(c.get("breakout_time_5m"))
        if getattr(rt, "tzinfo", None) is None:
            rt = rt.tz_localize("UTC")
        else:
            rt = rt.tz_convert("UTC")
        if getattr(bt, "tzinfo", None) is None:
            bt = bt.tz_localize("UTC")
        else:
            bt = bt.tz_convert("UTC")

        day = rt.date()
        df5 = load_cached_day(Path("cache"), sym, str(day), "5m")
        df1 = load_cached_day(Path("cache"), sym, str(day), "1m")
        if df5 is None or df5.empty or df1 is None or df1.empty:
            reason_counts["no_ignition_close"] += 1
            per_symbol[sym]["no_ignition_close"] += 1
            continue
        df5 = df5.copy()
        df5["Datetime"] = pd.to_datetime(df5["Datetime"], utc=True)
        df5 = df5.sort_values("Datetime")
        df1 = df1.copy()
        df1["Datetime"] = pd.to_datetime(df1["Datetime"], utc=True)
        df1 = df1.sort_values("Datetime")
        session_df_5m = df5[
            (df5["Datetime"].dt.strftime("%H:%M") >= "09:30")
            & (df5["Datetime"].dt.strftime("%H:%M") < "16:00")
        ]
        session_start = (
            session_df_5m["Datetime"].iloc[0]
            if not session_df_5m.empty
            else df5["Datetime"].iloc[0]
        )
        end_time = session_start + timedelta(minutes=90)

        direction = c.get("direction")
        breakout_up = direction == "long"
        retest_close = float((c.get("retest_candle") or {}).get("Close", 0.0))
        after_retest = df1[df1["Datetime"] > rt]
        if after_retest.empty:
            reason_counts["no_ignition_close"] += 1
            per_symbol[sym]["no_ignition_close"] += 1
            continue
        ignition_idx = None
        for idx, row in after_retest.iterrows():
            close = float(row.get("Close", 0.0))
            if (breakout_up and close > retest_close) or (
                (not breakout_up) and close < retest_close
            ):
                ignition_idx = idx
                break
        if ignition_idx is None:
            reason_counts["no_ignition_close"] += 1
            per_symbol[sym]["no_ignition_close"] += 1
            continue
        ignition_time = after_retest.loc[ignition_idx, "Datetime"]
        next_bars = df1[df1["Datetime"] > ignition_time]
        if next_bars.empty:
            reason_counts["missing_next_bar"] += 1
            per_symbol[sym]["missing_next_bar"] += 1
            continue
        entry_time = next_bars.iloc[0]["Datetime"]
        if entry_time >= end_time:
            reason_counts["entry_after_90min"] += 1
            per_symbol[sym]["entry_after_90min"] += 1
            continue
        # Fallback
        reason_counts["no_ignition_close"] += 1
        per_symbol[sym]["no_ignition_close"] += 1

    # Convert to DataFrames
    overall_df = pd.DataFrame(
        [{"reason": k, "count": v} for k, v in reason_counts.items()]
    ).sort_values("reason")
    rows = []
    for sym, d in per_symbol.items():
        total = sum(d.values())
        rows.append({"symbol": sym, **d, "total": total})
    by_sym_df = (
        pd.DataFrame(rows).sort_values("symbol")
        if rows
        else pd.DataFrame(
            columns=[
                "symbol",
                "no_ignition_close",
                "entry_after_90min",
                "missing_next_bar",
                "total",
            ]
        )
    )
    return overall_df, by_sym_df


def _classify_l1_to_l2(l1_path: Path, l2_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    l1 = json.load(open(l1_path))
    l2 = json.load(open(l2_path))

    # Build L1 signals map by (symbol -> breakout_time -> signal)
    l1_map: Dict[str, Dict[str, dict]] = {}
    for d in l1:
        sym = d.get("symbol")
        for s in d.get("signals", []) or []:
            bt = _norm_ts(s.get("breakout_time_5m"))
            l1_map.setdefault(sym, {})[bt] = s

    # Build L2 keys set
    l2_keys = set()
    for d in l2:
        sym = d.get("symbol")
        for s in d.get("signals", []) or []:
            l2_keys.add((sym, _norm_ts(s.get("breakout_time_5m"))))

    grader = get_grader("points")

    def compute_grades(sig_like: dict, session_df_5m: pd.DataFrame) -> Dict[str, str]:
        breakout = sig_like.get("breakout_candle", {})
        if hasattr(breakout, "to_dict"):
            breakout = breakout.to_dict()
        prev = sig_like.get("prev_breakout_candle", None)
        if prev is not None and hasattr(prev, "to_dict"):
            prev = prev.to_dict()
        retest = sig_like.get("retest_candle", {})
        if hasattr(retest, "to_dict"):
            retest = retest.to_dict()
        ignition = sig_like.get("ignition_candle", {})
        if hasattr(ignition, "to_dict"):
            ignition = ignition.to_dict()

        # Breakout body pct
        try:
            bbp = abs(float(breakout.get("Close", 0)) - float(breakout.get("Open", 0))) / max(
                float(breakout.get("High", 0)) - float(breakout.get("Low", 0)), 1e-9
            )
        except Exception:
            bbp = 0.0

        try:
            br_vol = float(breakout.get("Volume", 0))
            br_time = pd.to_datetime(sig_like.get("breakout_time_5m"))
            row = session_df_5m.loc[session_df_5m["Datetime"] == br_time]
            br_ma = (
                float(row["vol_ma"].iloc[0]) if not row.empty and "vol_ma" in row.columns else 1e-9
            )
            breakout_vol_ratio = br_vol / br_ma
        except Exception:
            breakout_vol_ratio = 0.0

        try:
            retest_vol_ratio = float(retest.get("Volume", 0)) / max(
                float(breakout.get("Volume", 0)), 1e-9
            )
        except Exception:
            retest_vol_ratio = 0.0

        breakout_grade, _ = grader.grade_breakout_candle(
            breakout,
            breakout_vol_ratio,
            bbp,
            sig_like.get("level"),
            sig_like.get("direction"),
            a_upper_wick_max=0.15,
            b_body_max=0.65,
            prev_candle=prev,
        )
        retest_grade, _ = grader.grade_retest(
            retest,
            retest_vol_ratio,
            sig_like.get("level", 0.0),
            sig_like.get("direction", "long"),
            retest_volume_a_max_ratio=0.30,
            retest_volume_b_max_ratio=0.60,
            b_level_epsilon_pct=0.10,
            b_structure_soft=True,
        )

        # Continuation on (next) ignition bar
        ign = ignition
        try:
            ign_open = float(ign.get("Open", 0))
            ign_high = float(ign.get("High", 0))
            ign_low = float(ign.get("Low", 0))
            ign_close = float(ign.get("Close", 0))
            ign_vol = float(ign.get("Volume", 0))
            ign_range = max(ign_high - ign_low, 1e-9)
            ignition_body_pct = abs(ign_close - ign_open) / ign_range
        except Exception:
            ignition_body_pct = 0.0
            ign_vol = 0.0
        try:
            ret_vol = float(retest.get("Volume", 0))
            ignition_vol_ratio = ign_vol / ret_vol if ret_vol > 0 else 0.0
        except Exception:
            ignition_vol_ratio = 0.0
        continuation_grade, _ = grader.grade_continuation(
            ign, ignition_vol_ratio, 0.5, ignition_body_pct
        )
        rr_grade, _ = grader.grade_risk_reward(2.0)
        market_grade, _ = grader.grade_market_context("slightly_red")

        return {
            "breakout": breakout_grade,
            "retest": retest_grade,
            "continuation": continuation_grade,
            "rr": rr_grade,
            "market": market_grade,
        }

    # Top-level L1->L2 drop reasons
    reasons = {
        "no_ignition_detected": 0,
        "entry_after_90min": 0,
        "missing_next_bar": 0,
        "quality_filter_rejection": 0,
    }
    per_symbol: Dict[str, Dict[str, int]] = {}

    # Quality-filter sub-breakdown
    # Overlapping counts: a single signal can fail multiple components
    quality_overlap = {
        "breakout_fail": 0,
        "retest_fail": 0,
        "continuation_fail": 0,
        "rr_fail": 0,
        "market_fail": 0,
    }
    quality_overlap_by_symbol: Dict[str, Dict[str, int]] = {}

    # Quality-filter primary reason (exclusive, precedence order)
    QUAL_PRECEDENCE = ["breakout", "retest", "continuation", "rr", "market"]
    quality_primary = {f"primary_{c}_fail": 0 for c in QUAL_PRECEDENCE}
    quality_primary_by_symbol: Dict[str, Dict[str, int]] = {}

    # Iterate per symbol
    for d in l1:
        sym = d.get("symbol")
        per_symbol.setdefault(sym, {k: 0 for k in reasons})
        quality_overlap_by_symbol.setdefault(sym, {k: 0 for k in quality_overlap})
        quality_primary_by_symbol.setdefault(sym, {k: 0 for k in quality_primary})

        # Lazy per-day cache
        cache_per_date: Dict[
            str,
            Tuple[
                Optional[pd.DataFrame],
                Optional[pd.DataFrame],
                Optional[pd.Timestamp],
                Optional[pd.Timestamp],
            ],
        ] = {}

        def get_session(day_ts: pd.Timestamp):
            day_utc = day_ts.tz_convert("UTC").date()
            key = str(day_utc)
            if key in cache_per_date:
                return cache_per_date[key]
            df5 = load_cached_day(Path("cache"), sym, key, "5m")
            df1 = load_cached_day(Path("cache"), sym, key, "1m")
            if df5 is None or df5.empty or df1 is None or df1.empty:
                cache_per_date[key] = (None, None, None, None)
                return cache_per_date[key]
            df5 = df5.copy()
            df5["Datetime"] = pd.to_datetime(df5["Datetime"], utc=True)
            df5 = df5.sort_values("Datetime")
            df1 = df1.copy()
            df1["Datetime"] = pd.to_datetime(df1["Datetime"], utc=True)
            df1 = df1.sort_values("Datetime")
            session_df_5m = df5[
                (df5["Datetime"].dt.strftime("%H:%M") >= "09:30")
                & (df5["Datetime"].dt.strftime("%H:%M") < "16:00")
            ]
            session_start = (
                session_df_5m["Datetime"].iloc[0]
                if not session_df_5m.empty
                else df5["Datetime"].iloc[0]
            )
            end_time = session_start + timedelta(minutes=90)
            cache_per_date[key] = (session_df_5m, df1, session_start, end_time)
            return cache_per_date[key]

        for bt_norm, s in (l1_map.get(sym) or {}).items():
            if (sym, bt_norm) in l2_keys:
                continue
            bt_local = pd.to_datetime(s.get("breakout_time_5m"))
            session_df_5m, df1, session_start, end_time = get_session(bt_local)
            if session_df_5m is None or df1 is None:
                reasons["no_ignition_detected"] += 1
                per_symbol[sym]["no_ignition_detected"] += 1
                continue

            # Detect stage 4 (no quality filters)
            cands = run_pipeline(session_df_5m=session_df_5m, session_df_1m=df1, pipeline_level=2)
            mt = None
            for c in cands:
                if pd.to_datetime(c.get("breakout_time")) == bt_local:
                    mt = c
                    break
            if mt is None or not mt.get("ignition_time"):
                reasons["no_ignition_detected"] += 1
                per_symbol[sym]["no_ignition_detected"] += 1
                continue

            ign_time = pd.to_datetime(mt.get("ignition_time"))
            next_bars = df1[df1["Datetime"] > ign_time]
            if next_bars.empty:
                reasons["missing_next_bar"] += 1
                per_symbol[sym]["missing_next_bar"] += 1
                continue
            entry_time = next_bars.iloc[0]["Datetime"]
            if entry_time >= end_time:
                reasons["entry_after_90min"] += 1
                per_symbol[sym]["entry_after_90min"] += 1
                continue

            # Apply Level 2 quality filter
            sig_like = {
                "breakout_candle": mt.get("breakout_candle", {}),
                "prev_breakout_candle": mt.get("prev_breakout_candle"),
                "retest_candle": mt.get("retest_candle", {}),
                "ignition_candle": mt.get("ignition_candle", {}),
                "breakout_time_5m": s.get("breakout_time_5m"),
                "direction": s.get("direction"),
                "level": s.get("level"),
            }
            grades = compute_grades(sig_like, session_df_5m)
            if any(v == "❌" for v in grades.values()):
                # Count top-level rejection
                reasons["quality_filter_rejection"] += 1
                per_symbol[sym]["quality_filter_rejection"] += 1

                # Overlapping component failures
                fails = [comp for comp, g in grades.items() if g == "❌"]
                for comp in fails:
                    key = f"{comp}_fail"
                    if key in quality_overlap:
                        quality_overlap[key] += 1
                        quality_overlap_by_symbol[sym][key] += 1

                # Primary reason by precedence
                primary = next(
                    (c for c in QUAL_PRECEDENCE if c in [f for f in grades if grades[f] == "❌"]),
                    None,
                )
                if primary is not None:
                    pkey = f"primary_{primary}_fail"
                    quality_primary[pkey] += 1
                    quality_primary_by_symbol[sym][pkey] += 1
                continue

            # Fallback
            reasons["no_ignition_detected"] += 1
            per_symbol[sym]["no_ignition_detected"] += 1

    overall_df = pd.DataFrame([{"reason": k, "count": v} for k, v in reasons.items()]).sort_values(
        "reason"
    )
    rows = []
    for sym, d in per_symbol.items():
        total = sum(d.values())
        rows.append({"symbol": sym, **d, "total": total})
    by_sym_df = (
        pd.DataFrame(rows).sort_values("symbol")
        if rows
        else pd.DataFrame(
            columns=[
                "symbol",
                "no_ignition_detected",
                "entry_after_90min",
                "missing_next_bar",
                "quality_filter_rejection",
                "total",
            ]
        )
    )

    # Build quality breakdown DataFrames (overlap and primary)
    quality_overlap_df = pd.DataFrame(
        [{"component": k, "count": v} for k, v in quality_overlap.items()]
    ).sort_values("component")
    q_rows = []
    for sym, d in quality_overlap_by_symbol.items():
        q_total = sum(d.values())
        q_rows.append({"symbol": sym, **d, "total": q_total})
    quality_overlap_by_sym_df = (
        pd.DataFrame(q_rows).sort_values("symbol")
        if q_rows
        else pd.DataFrame(
            columns=[
                "symbol",
                "breakout_fail",
                "retest_fail",
                "continuation_fail",
                "rr_fail",
                "market_fail",
                "total",
            ]
        )
    )

    quality_primary_df = pd.DataFrame(
        [{"component": k.replace("primary_", ""), "count": v} for k, v in quality_primary.items()]
    ).sort_values("component")
    qp_rows = []
    for sym, d in quality_primary_by_symbol.items():
        qp_total = sum(d.values())
        qp_rows.append({"symbol": sym, **d, "total": qp_total})
    quality_primary_by_sym_df = (
        pd.DataFrame(qp_rows).sort_values("symbol")
        if qp_rows
        else pd.DataFrame(columns=["symbol", *quality_primary.keys(), "total"])
    )

    # Attach extra frames as attributes for the caller
    overall_df._quality_overlap_df = quality_overlap_df  # type: ignore[attr-defined]
    overall_df._quality_overlap_by_sym_df = quality_overlap_by_sym_df  # type: ignore[attr-defined]
    overall_df._quality_primary_df = quality_primary_df  # type: ignore[attr-defined]
    overall_df._quality_primary_by_sym_df = quality_primary_by_sym_df  # type: ignore[attr-defined]

    return overall_df, by_sym_df


def main():
    l0_path, l1_path, l2_path = _find_latest_pairs()
    if not l0_path or not l1_path:
        raise SystemExit("Could not find matching Level 0 and Level 1 results in backtest_results/")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # L0 -> L1
    l0l1_overall, l0l1_by_sym = _classify_l0_to_l1(l0_path, l1_path)
    out1 = BACKTEST_DIR / f"l0_to_l1_drop_reasons_overall_{ts}.csv"
    out2 = BACKTEST_DIR / f"l0_to_l1_drop_reasons_by_symbol_{ts}.csv"
    l0l1_overall.to_csv(out1, index=False)
    l0l1_by_sym.to_csv(out2, index=False)
    print(f"Saved: {out1}")
    print(f"Saved: {out2}")

    # L1 -> L2 (if L2 available)
    if l2_path:
        l1l2_overall, l1l2_by_sym = _classify_l1_to_l2(l1_path, l2_path)
        out3 = BACKTEST_DIR / f"l1_to_l2_drop_reasons_overall_{ts}.csv"
        out4 = BACKTEST_DIR / f"l1_to_l2_drop_reasons_by_symbol_{ts}.csv"
        l1l2_overall.to_csv(out3, index=False)
        l1l2_by_sym.to_csv(out4, index=False)
        print(f"Saved: {out3}")
        print(f"Saved: {out4}")

        # Also export the Level 2 quality rejection breakdowns
        q_overlap = getattr(l1l2_overall, "_quality_overlap_df", None)
        q_overlap_by_sym = getattr(l1l2_overall, "_quality_overlap_by_sym_df", None)
        q_primary = getattr(l1l2_overall, "_quality_primary_df", None)
        q_primary_by_sym = getattr(l1l2_overall, "_quality_primary_by_sym_df", None)
        if q_overlap is not None and q_primary is not None:
            out5 = BACKTEST_DIR / f"l1_to_l2_quality_overlap_{ts}.csv"
            out6 = BACKTEST_DIR / f"l1_to_l2_quality_overlap_by_symbol_{ts}.csv"
            out7 = BACKTEST_DIR / f"l1_to_l2_quality_primary_{ts}.csv"
            out8 = BACKTEST_DIR / f"l1_to_l2_quality_primary_by_symbol_{ts}.csv"
            q_overlap.to_csv(out5, index=False)
            (q_overlap_by_sym if q_overlap_by_sym is not None else pd.DataFrame()).to_csv(
                out6, index=False
            )
            q_primary.to_csv(out7, index=False)
            (q_primary_by_sym if q_primary_by_sym is not None else pd.DataFrame()).to_csv(
                out8, index=False
            )
            print(f"Saved: {out5}")
            print(f"Saved: {out6}")
            print(f"Saved: {out7}")
            print(f"Saved: {out8}")
    else:
        print("No Level 2 results found for same range; skipping L1→L2 export.")


if __name__ == "__main__":
    main()
