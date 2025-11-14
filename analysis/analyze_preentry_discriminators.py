#!/usr/bin/env python3
"""
Analyze pre-entry feature discriminative power using latest backtest results.

Outputs:
- Markdown report summarizing baseline stats and binned win rates by feature
- One CSV per feature with bin stats (optional) consolidated to a single CSV

Usage:
  python analysis/analyze_preentry_discriminators.py \
    --input backtest_results/level1_ALL_..._profile_....json \
    --out backtest_results/preentry_discriminators.md

If --input is omitted, the most recent level1_ALL_*_profile_*.json is used.
"""

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def find_latest_level1_profile(results_dir: Path) -> Optional[Path]:
    cand = sorted(
        results_dir.glob("level1_ALL_*_profile_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cand[0] if cand else None


def load_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # legacy dict keyed by symbol
        out = []
        for k, v in data.items():
            if isinstance(v, dict):
                v.setdefault("symbol", k)
                out.append(v)
        return out
    raise ValueError("Unsupported results JSON structure")


def build_signal_index(groups: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for g in groups:
        sym = g.get("symbol") or g.get("ticker")
        for s in g.get("signals") or []:
            dt = s.get("datetime")
            if sym and dt:
                idx[(sym, dt)] = s
    return idx


def flatten_trades(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for g in groups:
        sym = g.get("symbol") or g.get("ticker")
        for t in g.get("trades") or []:
            dt = t.get("datetime")
            rows.append({"symbol": sym, **t, "_key": (sym, dt)})
    return rows


def to_float(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return float(v)
    except Exception:
        return None


def quantile_edges(values: List[float], q: int = 6) -> List[float]:
    # Defensive: small unique set -> return sorted uniques as edges
    uniq = sorted(set(values))
    if len(uniq) <= q:
        return uniq
    try:
        import numpy as np

        qs = np.linspace(0, 1, q + 1)
        edges = list(np.quantile(values, qs))
        # Deduplicate edges to avoid empty bins
        dedup: List[float] = []
        for e in edges:
            if not dedup or abs(e - dedup[-1]) > 1e-12:
                dedup.append(float(e))
        return dedup
    except Exception:
        return uniq[: q + 1]


@dataclass
class BinStat:
    lo: float
    hi: float
    n: int
    wins: int
    win_rate: float
    avg_pnl: float


def bin_and_score(
    rows: List[Dict[str, Any]],
    values: List[float],
    edges: List[float],
) -> List[BinStat]:
    # Build bins [edges[i], edges[i+1]) with last bin inclusive on upper
    bins: List[BinStat] = []
    for i in range(len(edges) - 1):
        lo = edges[i]
        hi = edges[i + 1]
        n = wins = 0
        pnl_sum = 0.0
        for r, v in zip(rows, values):
            if v is None:
                continue
            if v >= lo and (v < hi or (i == len(edges) - 2 and v <= hi)):
                n += 1
                if r.get("outcome") == "win":
                    wins += 1
                pnl_sum += float(r.get("pnl") or 0.0)
        wr = (wins / n * 100.0) if n else 0.0
        avg = (pnl_sum / n) if n else 0.0
        bins.append(BinStat(lo=lo, hi=hi, n=n, wins=wins, win_rate=wr, avg_pnl=avg))
    return bins


def fmt_edge(x: Optional[float]) -> str:
    if x is None:
        return ""
    try:
        return f"{x:.4g}"
    except Exception:
        return str(x)


def analyze(
    features: Dict[str, List[Optional[float]]], rows: List[Dict[str, Any]]
) -> Tuple[str, Dict[str, List[BinStat]]]:
    # Baseline stats
    base_n = len(rows)
    base_w = sum(1 for r in rows if r.get("outcome") == "win")
    base_wr = (base_w / base_n * 100.0) if base_n else 0.0
    base_pnl = sum(float(r.get("pnl") or 0.0) for r in rows)
    base_avg = (base_pnl / base_n) if base_n else 0.0

    md_lines: List[str] = []
    md_lines.append("\n## Pre-entry discriminators (Level 1)\n")
    md_lines.append(
        f"Baseline: n={base_n} wins={base_w} win%={base_wr:.1f} total_pnl={base_pnl:.2f} avg_pnl={base_avg:.2f}\n"
    )

    per_feature_bins: Dict[str, List[BinStat]] = {}
    uplifts: List[Tuple[str, float, float]] = []  # (feature, max_wr, max_uplift)

    for name, vals in features.items():
        series = [to_float(v) for v in vals if v is not None]
        if len(series) < 30:
            continue
        edges = quantile_edges(series, q=6)
        # Ensure at least two edges
        if len(edges) < 2:
            continue
        bins = bin_and_score(rows, [to_float(v) for v in vals], edges)
        per_feature_bins[name] = bins
        max_wr = 0.0
        max_uplift = -999.0
        best = None
        for b in bins:
            if b.n < max(50, int(0.01 * base_n)):
                continue
            if b.win_rate > max_wr:
                max_wr = b.win_rate
                best = b
        if best is not None:
            max_uplift = best.win_rate - base_wr
        uplifts.append((name, max_wr, max_uplift))

        # Add section for this feature
        md_lines.append(f"\n### {name}\n")
        md_lines.append("bin_low,bin_high,n,wins,win_pct,avg_pnl")
        for b in bins:
            md_lines.append(
                f"{fmt_edge(b.lo)},{fmt_edge(b.hi)},{b.n},{b.wins},{b.win_rate:.1f},{b.avg_pnl:.2f}"
            )

    # Top discriminators by max uplift
    uplifts = [u for u in uplifts if not math.isnan(u[2])]
    uplifts.sort(key=lambda x: x[2], reverse=True)
    md_lines.insert(2, "\nTop feature uplifts (win% vs baseline):")
    for name, max_wr, upl in uplifts[:8]:
        md_lines.insert(3, f"- {name}: best bin win%={max_wr:.1f} (uplift {upl:.1f}pp)")

    return "\n".join(md_lines) + "\n", per_feature_bins


def main():
    ap = argparse.ArgumentParser(
        description="Analyze pre-entry discriminators from backtest results"
    )
    ap.add_argument("--input", help="Path to backtest JSON (defaults to latest level1_ALL profile)")
    ap.add_argument("--out", help="Markdown output path", default=None)
    args = ap.parse_args()

    results_dir = Path("backtest_results")
    if args.input:
        in_path = Path(args.input)
    else:
        latest = find_latest_level1_profile(results_dir)
        if latest is None:
            raise SystemExit("No level1_ALL_*_profile_*.json found in backtest_results")
        in_path = latest

    groups = load_results(in_path)
    trades = flatten_trades(groups)
    if not trades:
        raise SystemExit(f"No trades in {in_path}; cannot analyze discriminators")
    sig_idx = build_signal_index(groups)

    # Build feature matrix aligned per trade
    rows: List[Dict[str, Any]] = []
    feats: Dict[str, List[Optional[float]]] = {
        # Volume ratios and body% already known discriminators
        "ignition_vol_ratio": [],
        "retest_vol_ratio": [],
        "breakout_vol_ratio": [],
        # New pre-entry metrics
        "breakout_or_dist_pct": [],
        "retest_touch_distance_pct_or": [],
        "retest_wick_penetration_pct": [],
        "minutes_since_open_retest": [],
        "minutes_since_open_ignition": [],
        "breakout_vwap_diff": [],
        "retest_vwap_diff": [],
        "atr14_5m": [],
        "breakout_dollar_vol": [],
        "retest_dollar_vol": [],
        "consolidation_minutes": [],
        "consolidation_bars_1m": [],
        # Points total for cross reference
        "score_total": [],
        # Boolean alignment (coerce to 0/1)
        "ignition_ema9_gt_ema20": [],
    }

    for t in trades:
        key = t.get("_key")
        sig = sig_idx.get(key, {})
        pre = sig.get("preentry") or {}
        rows.append(t)
        feats["ignition_vol_ratio"].append(to_float(sig.get("ignition_vol_ratio")))
        feats["retest_vol_ratio"].append(to_float(sig.get("retest_vol_ratio")))
        feats["breakout_vol_ratio"].append(to_float(sig.get("breakout_vol_ratio")))
        feats["breakout_or_dist_pct"].append(to_float(pre.get("breakout_or_dist_pct")))
        feats["retest_touch_distance_pct_or"].append(
            to_float(pre.get("retest_touch_distance_pct_or"))
        )
        feats["retest_wick_penetration_pct"].append(
            to_float(pre.get("retest_wick_penetration_pct"))
        )
        feats["minutes_since_open_retest"].append(to_float(pre.get("minutes_since_open_retest")))
        feats["minutes_since_open_ignition"].append(
            to_float(pre.get("minutes_since_open_ignition"))
        )
        feats["breakout_vwap_diff"].append(to_float(pre.get("breakout_vwap_diff")))
        feats["retest_vwap_diff"].append(to_float(pre.get("retest_vwap_diff")))
        feats["atr14_5m"].append(to_float(pre.get("atr14_5m")))
        feats["breakout_dollar_vol"].append(to_float(pre.get("breakout_dollar_vol")))
        feats["retest_dollar_vol"].append(to_float(pre.get("retest_dollar_vol")))
        feats["consolidation_minutes"].append(to_float(pre.get("consolidation_minutes")))
        feats["consolidation_bars_1m"].append(to_float(pre.get("consolidation_bars_1m")))
        # Points total can be on trade or embedded points dict
        score_total = t.get("score_total")
        if score_total is None:
            pts = t.get("points") or {}
            score_total = pts.get("total") if isinstance(pts, dict) else None
        feats["score_total"].append(to_float(score_total))
        # EMA alignment -> 1.0 if True, 0.0 if False, None if missing
        align = pre.get("ignition_ema9_gt_ema20")
        if align is True:
            feats["ignition_ema9_gt_ema20"].append(1.0)
        elif align is False:
            feats["ignition_ema9_gt_ema20"].append(0.0)
        else:
            feats["ignition_ema9_gt_ema20"].append(None)

    md, _ = analyze(feats, rows)

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out_md = (
        Path(args.out)
        if args.out
        else Path("backtest_results") / f"preentry_discriminators_{ts}.md"
    )
    out_md.write_text(md)
    print(f"Wrote Markdown: {out_md}")


if __name__ == "__main__":
    main()
