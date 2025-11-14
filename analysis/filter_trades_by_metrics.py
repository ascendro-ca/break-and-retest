#!/usr/bin/env python3
"""
Filter trades from an existing backtest results JSON by pre-entry metrics
and generate a Markdown summary and CSV for workflow evaluation.

Usage:
  python analysis/filter_trades_by_metrics.py \
    --input backtest_results/level1_...json \
    --ivr-min 2.0 --rvr-min 1.5 \
    --out-prefix backtest_results/filtered_ivr2_rvr1p5

Notes:
  - Matches trades to their corresponding signals by (symbol, datetime)
    to access pre-entry metrics such as ignition_vol_ratio and retest_vol_ratio.
  - Uses backtest.generate_markdown_trade_summary to render a familiar summary table.
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is on sys.path for local imports
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Local imports from project
from backtest import generate_markdown_trade_summary  # noqa: E402
from time_utils import get_display_timezone  # noqa: E402


def load_results(path: str) -> List[Dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # Some older runs may store a dict keyed by symbol
    if isinstance(data, dict):
        out = []
        for k, v in data.items():
            if isinstance(v, dict):
                v.setdefault("symbol", k)
                out.append(v)
        return out
    raise ValueError("Unsupported JSON structure for results")


def build_signal_index(groups: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for g in groups:
        sym = g.get("symbol") or g.get("ticker")
        for s in g.get("signals") or []:
            dt = s.get("datetime")
            if sym and dt:
                idx[(sym, dt)] = s
    return idx


def to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def filter_trades(
    groups: List[Dict[str, Any]],
    ivr_min: float,
    rvr_min: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    sig_idx = build_signal_index(groups)
    filtered_groups: List[Dict[str, Any]] = []
    flat_rows: List[Dict[str, Any]] = []

    for g in groups:
        sym = g.get("symbol") or g.get("ticker")
        trades = g.get("trades") or []
        kept: List[Dict[str, Any]] = []
        # Build quick lookup of signals for this symbol by datetime
        for t in trades:
            dt = t.get("datetime")
            sig = sig_idx.get((sym, dt), {})
            ivr = to_float(sig.get("ignition_vol_ratio"))
            rvr = to_float(sig.get("retest_vol_ratio"))
            # Apply filters
            if ivr is None or rvr is None:
                continue
            if ivr < ivr_min or rvr < rvr_min:
                continue

            kept.append(t)
            row = {
                "symbol": sym,
                "datetime": dt,
                "outcome": t.get("outcome"),
                "pnl": t.get("pnl"),
                "entry": t.get("entry"),
                "exit": t.get("exit"),
                "stop": t.get("stop"),
                "target": t.get("target"),
                "rr_ratio": t.get("rr_ratio"),
                "shares": t.get("shares"),
                "ivr": ivr,
                "rvr": rvr,
                "bvr": to_float(sig.get("breakout_vol_ratio")),
                "score_total": (t.get("score_total") or (t.get("points") or {}).get("total")),
                "grade_letter": (t.get("grade_letter") or (t.get("points") or {}).get("letter")),
            }
            flat_rows.append(row)

        # Preserve group-level fields, but only kept trades
        new_g = dict(g)
        new_g["trades"] = kept
        filtered_groups.append(new_g)

    return filtered_groups, flat_rows


def compute_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = [r for r in rows if (r.get("outcome") in ("win", "loss", "forced"))]
    n = len(base)
    wins = sum(1 for r in base if r.get("outcome") == "win")
    pnl = sum(float(r.get("pnl") or 0.0) for r in base)
    wr = (wins / n * 100.0) if n else 0.0
    avg = (pnl / n) if n else 0.0
    return {"n": n, "wins": wins, "win_rate": wr, "total_pnl": pnl, "avg_pnl": avg}


def write_markdown(groups: List[Dict[str, Any]], out_path: Path):
    tz = get_display_timezone()
    md = generate_markdown_trade_summary(groups, tzinfo=tz, tz_label=str(tz))
    out_path.write_text(md)


def write_csv(rows: List[Dict[str, Any]], out_path: Path):
    if not rows:
        out_path.write_text("")
        return
    cols = [
        "symbol",
        "datetime",
        "outcome",
        "pnl",
        "entry",
        "exit",
        "stop",
        "target",
        "rr_ratio",
        "shares",
        "ivr",
        "rvr",
        "bvr",
        "score_total",
        "grade_letter",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


def main():
    ap = argparse.ArgumentParser(description="Filter trades by pre-entry volume metrics")
    ap.add_argument("--input", required=True, help="Path to backtest results JSON")
    ap.add_argument("--ivr-min", type=float, default=2.0, help="Min ignition_vol_ratio")
    ap.add_argument("--rvr-min", type=float, default=1.5, help="Min retest_vol_ratio")
    ap.add_argument(
        "--out-prefix",
        default=None,
        help="Output prefix (default: backtest_results/filtered_<timestamp>)",
    )
    args = ap.parse_args()

    groups = load_results(args.input)
    filtered_groups, rows = filter_trades(groups, args.ivr_min, args.rvr_min)
    summary = compute_summary(rows)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.out_prefix:
        base = Path(args.out_prefix)
    else:
        base = Path("backtest_results") / f"filtered_ivr{args.ivr_min:g}_rvr{args.rvr_min:g}_{ts}"

    base.parent.mkdir(parents=True, exist_ok=True)
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")

    write_markdown(filtered_groups, md_path)
    write_csv(rows, csv_path)

    print("Filtered summary:")
    print(
        "  n={n} wins={w} win%={wr:.1f} total_pnl={tp:.2f} avg_pnl={ap:.2f}".format(
            n=summary["n"],
            w=summary["wins"],
            wr=summary["win_rate"],
            tp=summary["total_pnl"],
            ap=summary["avg_pnl"],
        )
    )
    print(f"  Markdown: {md_path}")
    print(f"  CSV:      {csv_path}")


if __name__ == "__main__":
    main()
