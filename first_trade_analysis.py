#!/usr/bin/env python3
"""
Analyze "first trade of each day" from a backtest results JSON.

Scenarios:
- per-symbol: pick the earliest trade per symbol per calendar day
- global: pick the single earliest trade across all symbols per calendar day

Usage:
  python first_trade_analysis.py --input backtest_results/sep2025_level1.json \
    --output backtest_results/sep2025_level1_first_trade_summary.md

Options:
  --global-only to omit per-symbol analysis
  --symbol-only to omit global analysis
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_results(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r") as f:
        return json.load(f)


def day_key(dt_str: str) -> Tuple[str, str]:
    # Return (YYYY-MM-DD, full_datetime_str) for ordering
    # We avoid tz math and rely on ISO-like ordering of the string
    # dt_str examples: "2025-09-03 09:41:00+00:00"
    d = dt_str.split(" ")[0]
    return d, dt_str


def analyze_per_symbol(trades_by_symbol: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    selected: List[Dict[str, Any]] = []
    # pick earliest trade for each symbol/day
    for sym, tlist in trades_by_symbol.items():
        per_day: Dict[str, Dict[str, Any]] = {}
        for t in tlist:
            d, full = day_key(t.get("datetime", ""))
            cur = per_day.get(d)
            if cur is None or full < cur.get("datetime", "zzzz"):
                per_day[d] = t
        selected.extend(per_day.values())
    return summarize_selection(selected, label="per-symbol")


def analyze_global(all_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_day: Dict[str, Dict[str, Any]] = {}
    for t in all_trades:
        d, full = day_key(t.get("datetime", ""))
        cur = per_day.get(d)
        if cur is None or full < cur.get("datetime", "zzzz"):
            per_day[d] = t
    selected = list(per_day.values())
    return summarize_selection(selected, label="global")


def summarize_selection(selected: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    trades = len(selected)
    wins = sum(1 for t in selected if t.get("outcome") == "win")
    losses = sum(1 for t in selected if t.get("outcome") == "loss")
    pnl = sum(float(t.get("pnl", 0.0)) for t in selected)
    win_rate = (wins / trades) if trades else 0.0
    by_symbol: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    )
    for t in selected:
        # We need symbol: in results, symbol is attached at top-level,
        # but in trade we don't have it directly
        # Try to infer from path injected later; else leave blank
        sym = t.get("symbol") or t.get("ticker") or ""
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"] += float(t.get("pnl", 0.0))
        if t.get("outcome") == "win":
            by_symbol[sym]["wins"] += 1
        else:
            by_symbol[sym]["losses"] += 1
    return {
        "label": label,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": pnl,
        "by_symbol": by_symbol,
        "selected": selected,
    }


def attach_symbol_to_trades(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_trades: List[Dict[str, Any]] = []
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for sym_block in results:
        sym = sym_block.get("symbol")
        for t in sym_block.get("trades", []) or []:
            t = dict(t)
            t["symbol"] = sym
            all_trades.append(t)
            by_symbol.setdefault(sym, []).append(t)
    # sort within each symbol to ensure earliest selection is deterministic
    for sym, lst in by_symbol.items():
        lst.sort(key=lambda t: t.get("datetime", ""))
    all_trades.sort(key=lambda t: t.get("datetime", ""))
    return all_trades, by_symbol


def format_money(x: float) -> str:
    s = f"${x:,.2f}"
    return s


def write_markdown(
    out_path: Path,
    per_symbol: Dict[str, Any] | None,
    global_sel: Dict[str, Any] | None,
) -> None:
    lines: List[str] = []
    lines.append("## First trade of each day analysis\n")
    if per_symbol:
        lines.append("### Per symbol per day\n")
        summary = (
            "- Trades: "
            + f"{per_symbol['trades']}  |  Wins: {per_symbol['wins']}  |  "
            + f"Losses: {per_symbol['losses']}  |  "
            + f"Win rate: {per_symbol['win_rate']*100:.1f}%  |  "
            + f"P&L: {format_money(per_symbol['total_pnl'])}\n"
        )
        lines.append(summary)
        # Compact per-symbol row
        if per_symbol["by_symbol"]:
            syms = sorted(per_symbol["by_symbol"].items())
            rows = []
            for sym, v in syms:
                rate = v["wins"] / v["trades"] * 100 if v["trades"] else 0
                rows.append(
                    f"  - {sym}: {v['trades']} trades, win {v['wins']}/{v['trades']} "
                    f"({rate:.0f}%), P&L {format_money(v['pnl'])}"
                )
            lines.extend(rows)
        lines.append("")

    if global_sel:
        lines.append("### Global (one trade total per day)\n")
        gsummary = (
            "- Trades: "
            + f"{global_sel['trades']}  |  Wins: {global_sel['wins']}  |  "
            + f"Losses: {global_sel['losses']}  |  "
            + f"Win rate: {global_sel['win_rate']*100:.1f}%  |  "
            + f"P&L: {format_money(global_sel['total_pnl'])}\n"
        )
        lines.append(gsummary)
        lines.append("")

    out_path.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to backtest results JSON")
    ap.add_argument("--output", required=True, help="Path to write markdown summary")
    ap.add_argument(
        "--global-only",
        action="store_true",
        help="Only compute global per-day first trade",
    )
    ap.add_argument(
        "--symbol-only",
        action="store_true",
        help="Only compute per-symbol per-day first trade",
    )
    args = ap.parse_args()

    results = load_results(Path(args.input))
    all_trades, trades_by_symbol = attach_symbol_to_trades(results)

    per_symbol_summary = None if args.global_only else analyze_per_symbol(trades_by_symbol)
    global_summary = None if args.symbol_only else analyze_global(all_trades)

    write_markdown(Path(args.output), per_symbol_summary, global_summary)

    # Also print a one-line console summary
    if per_symbol_summary:
        print(
            f"Per-symbol: trades={per_symbol_summary['trades']} wins={per_symbol_summary['wins']} "
            f"losses={per_symbol_summary['losses']} "
            f"win_rate={per_symbol_summary['win_rate']*100:.1f}% "
            f"pnl={format_money(per_symbol_summary['total_pnl'])}"
        )
    if global_summary:
        print(
            f"Global:     trades={global_summary['trades']} wins={global_summary['wins']} "
            f"losses={global_summary['losses']} win_rate={global_summary['win_rate']*100:.1f}% "
            f"pnl={format_money(global_summary['total_pnl'])}"
        )


if __name__ == "__main__":
    main()
