#!/usr/bin/env python3
"""
Export breakout score distribution from a Level 1 backtest JSON and overlay which
signals would pass the Level 2 quality filter.

Outputs:
1) Per-signal CSV with columns: symbol, datetime, direction, breakout_points, l2_pass
2) Histogram CSV aggregated by integer breakout_points bucket with counts and pass rate

Usage:
    python export_breakout_score_distribution.py \
        --level1 backtest_results/level1_ALL_20250101_20251031_points_....json \
        [--level2 backtest_results/level2_ALL_20250101_20251031_points_....json] \
        [--output-dir backtest_results]

Notes:
    - Assumes Level 1 results include `signals` with `component_grades` and
        `breakout_points` fields (now computed for all levels in backtest.py).
    - Preferred overlay: if a Level 2 JSON is provided via --level2, we mark l2_pass
        based on whether that exact signal appears in the Level 2 results (post-filter).
        Matching key: (symbol, breakout_time_5m, retest_candle.Datetime, direction).
    - Fallback overlay (when --level2 is omitted): approximate Level 2 pass by checking
        component grades on the Level 1 JSON. We ignore continuation in this approximation
        because Level 1 does not evaluate ignition pre-entry; we require breakout/retest/rr/market
        to be not '❌'.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def load_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        return json.load(f)


def l2_pass_fallback(component_grades: Dict[str, str]) -> bool:
    """
    Approximate Level 2 pass using Level 1 component grades only.
    Continuation is ignored here because Level 1 doesn't evaluate ignition pre-entry.
    We require breakout/retest/rr/market to be not '❌'.
    """
    needed = ("breakout", "retest", "rr", "market")
    return all(component_grades.get(k, "❌") != "❌" for k in needed)


def build_l2_pass_keys(level2_results: List[Dict[str, Any]]) -> Set[Tuple[str, str, str, str]]:
    """
    Build a set of keys for signals that passed Level 2 quality filtering.
    Key: (symbol, breakout_time_5m, retest_datetime, direction)
    """
    keys: Set[Tuple[str, str, str, str]] = set()
    for sym_res in level2_results:
        symbol = sym_res.get("symbol", "?")
        for sig in sym_res.get("signals", []) or []:
            bt = str(sig.get("breakout_time_5m", ""))
            direction = str(sig.get("direction", ""))
            # retest candle timestamp (string in JSON)
            rc = sig.get("retest_candle", {}) or {}
            rt = str(rc.get("Datetime", ""))
            keys.add((symbol, bt, rt, direction))
    return keys


def timestamp_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_per_signal_csv(rows: Iterable[Tuple[str, str, str, float, bool]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "datetime", "direction", "breakout_points", "l2_pass"])
        for r in rows:
            w.writerow(r)


def write_histogram_csv(hist: Dict[int, Dict[str, int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score_bucket", "count_l2_pass", "count_l2_fail", "total", "pass_rate"])
        for bucket in sorted(hist.keys()):
            passed = hist[bucket]["pass"]
            failed = hist[bucket]["fail"]
            total = passed + failed
            rate = (passed / total) if total > 0 else 0.0
            w.writerow([bucket, passed, failed, total, f"{rate:.3f}"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Export breakout score distribution with L2 overlay")
    ap.add_argument("--level1", required=True, type=Path, help="Path to Level 1 JSON results")
    ap.add_argument(
        "--output-dir",
        default=Path("backtest_results"),
        type=Path,
        help="Directory to write the CSV outputs",
    )
    ap.add_argument(
        "--level2",
        type=Path,
        help=(
            "Optional: Path to Level 2 JSON results to overlay actual pass/fail. "
            "If omitted, a fallback approximation based on Level 1 component grades is used."
        ),
    )
    args = ap.parse_args()

    results = load_results(args.level1)
    l2_keys: Optional[Set[Tuple[str, str, str, str]]] = None
    if args.level2 and args.level2.exists():
        try:
            l2_results = load_results(args.level2)
            l2_keys = build_l2_pass_keys(l2_results)
            count_l2 = sum(len(r.get("signals", []) or []) for r in l2_results)
            print(f"Loaded Level 2 overlay from {args.level2} with {count_l2} signals")
        except Exception as e:
            # Wrapped for line-length compliance
            print(
                "WARNING: Failed to load/parse Level 2 file ("
                f"{args.level2}) : {e}. "
                "Falling back to approximation."
            )
            l2_keys = None

    per_signal_rows: List[Tuple[str, str, str, float, bool]] = []
    hist: Dict[int, Dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})

    total_signals = 0
    missing_scores = 0

    for sym_res in results:
        symbol = sym_res.get("symbol", "?")
        for sig in sym_res.get("signals", []) or []:
            total_signals += 1
            pts = sig.get("breakout_points")
            grades = sig.get("component_grades") or {}

            # Determine pass: prefer actual Level 2 membership when provided
            if l2_keys is not None:
                bt = str(sig.get("breakout_time_5m", ""))
                direction = str(sig.get("direction", ""))
                rc = sig.get("retest_candle", {}) or {}
                rt = str(rc.get("Datetime", ""))
                passed = (symbol, bt, rt, direction) in l2_keys
            else:
                passed = l2_pass_fallback(grades)
            dt = sig.get("datetime", "")
            direction = sig.get("direction", "")

            try:
                pts_f = float(pts) if pts is not None else None
            except Exception:
                pts_f = None

            if pts_f is None:
                missing_scores += 1
                continue

            # Bucket by integer points (0..30 typical)
            bucket = int(round(pts_f))

            if passed:
                hist[bucket]["pass"] += 1
            else:
                hist[bucket]["fail"] += 1

            per_signal_rows.append((symbol, str(dt), str(direction), pts_f, passed))

    ts = timestamp_tag()
    out1 = args.output_dir / f"breakout_score_distribution_by_signal_{ts}.csv"
    out2 = args.output_dir / f"breakout_score_histogram_{ts}.csv"

    write_per_signal_csv(per_signal_rows, out1)
    write_histogram_csv(hist, out2)

    print(f"Saved per-signal rows: {out1}")
    print(f"Saved histogram: {out2}")
    mode = "actual_l2" if l2_keys is not None else "approx_no_continuation"
    print(
        f"Summary ({mode}): total_signals={total_signals}, "
        f"exported={len(per_signal_rows)}, "
        f"missing_scores={missing_scores}"
    )


if __name__ == "__main__":
    main()
