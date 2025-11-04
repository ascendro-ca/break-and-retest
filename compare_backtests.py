#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        return json.load(f)


def pct(x: float) -> str:
    return f"{x*100:.1f}%" if isinstance(x, (int, float)) else "-"


def fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def main():
    p = argparse.ArgumentParser(
        description="Compare Level 1 vs Level 2 backtest outputs and include L2 rejection counts."
    )
    p.add_argument("--level1", required=True, type=Path, help="Path to Level 1 JSON results")
    p.add_argument("--level2", required=True, type=Path, help="Path to Level 2 JSON results")
    p.add_argument("--output", required=True, type=Path, help="Path to write Markdown comparison")
    args = p.parse_args()

    l1 = load_results(args.level1)
    l2 = load_results(args.level2)

    l1_by_sym: Dict[str, Dict[str, Any]] = {r["symbol"]: r for r in l1}
    l2_by_sym: Dict[str, Dict[str, Any]] = {r["symbol"]: r for r in l2}

    symbols = sorted(set(l1_by_sym.keys()) | set(l2_by_sym.keys()))

    # Header
    lines = []
    lines.append("# Level 1 vs Level 2 Comparison (with Level 2 rejections)")
    lines.append("")
    lines.append(f"L1 file: `{args.level1.name}`  ")
    lines.append(f"L2 file: `{args.level2.name}`")
    lines.append("")

    # Table header
    lines.append(
        "| Symbol | L1 Trades | L1 Win% | L1 P&L | L1 Candidates | L2 Trades | L2 Win% | L2 P&L | L2 Candidates | L2 Rej breakout❌ | L2 Rej retest❌ | L2 Rej candle-type | ΔTrades | ΔWin% (pp) | ΔP&L |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    tot = {
        "l1_trades": 0,
        "l1_wins": 0,
        "l1_pnl": 0.0,
        "l1_candidates": 0,
        "l2_trades": 0,
        "l2_wins": 0,
        "l2_pnl": 0.0,
        "l2_candidates": 0,
        "rej_breakout": 0,
        "rej_retest": 0,
        "rej_candle": 0,
    }

    def win_rate(trades: int, wins: int) -> float:
        if trades <= 0:
            return 0.0
        return wins / max(trades, 1)

    for sym in symbols:
        r1 = l1_by_sym.get(sym, {})
        r2 = l2_by_sym.get(sym, {})

        l1_trades = int(r1.get("total_trades", 0) or 0)
        l1_wins = int(r1.get("winning_trades", 0) or 0)
        l1_pnl = float(r1.get("total_pnl", 0.0) or 0.0)
        l1_candidates = int(r1.get("candidate_count", 0) or 0)

        l2_trades = int(r2.get("total_trades", 0) or 0)
        l2_wins = int(r2.get("winning_trades", 0) or 0)
        l2_pnl = float(r2.get("total_pnl", 0.0) or 0.0)
        l2_candidates = int(r2.get("candidate_count", 0) or 0)

        rej = r2.get("level2_rejections", {}) or {}
        rej_breakout = int(rej.get("breakout_fail", 0) or 0)
        rej_retest = int(rej.get("retest_fail", 0) or 0)
        rej_candle = int(rej.get("candle_type_fail", 0) or 0)

        l1_wr = win_rate(l1_trades, l1_wins)
        l2_wr = win_rate(l2_trades, l2_wins)

        d_trades = l2_trades - l1_trades
        d_wr_pp = (l2_wr - l1_wr) * 100.0
        d_pnl = l2_pnl - l1_pnl

        tot["l1_trades"] += l1_trades
        tot["l1_wins"] += l1_wins
        tot["l1_pnl"] += l1_pnl
        tot["l1_candidates"] += l1_candidates
        tot["l2_trades"] += l2_trades
        tot["l2_wins"] += l2_wins
        tot["l2_pnl"] += l2_pnl
        tot["l2_candidates"] += l2_candidates
        tot["rej_breakout"] += rej_breakout
        tot["rej_retest"] += rej_retest
        tot["rej_candle"] += rej_candle

        lines.append(
            "| {sym} | {l1t} | {l1wr} | {l1pnl} | {l1cand} | {l2t} | {l2wr} | {l2pnl} | {l2cand} | {rbo} | {rrt} | {rct} | {dt} | {dwr} | {dpnl} |".format(
                sym=sym,
                l1t=l1_trades,
                l1wr=pct(l1_wr),
                l1pnl=fmt_money(l1_pnl),
                l1cand=l1_candidates,
                l2t=l2_trades,
                l2wr=pct(l2_wr),
                l2pnl=fmt_money(l2_pnl),
                l2cand=l2_candidates,
                rbo=rej_breakout,
                rrt=rej_retest,
                rct=rej_candle,
                dt=d_trades,
                dwr=f"{d_wr_pp:+.1f} pp",
                dpnl=fmt_money(d_pnl),
            )
        )

    # Totals
    tot_l1_wr = win_rate(tot["l1_trades"], tot["l1_wins"])
    tot_l2_wr = win_rate(tot["l2_trades"], tot["l2_wins"])
    tot_d_trades = tot["l2_trades"] - tot["l1_trades"]
    tot_d_wr_pp = (tot_l2_wr - tot_l1_wr) * 100.0
    tot_d_pnl = tot["l2_pnl"] - tot["l1_pnl"]

    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    lines.append(
        "| Overall | {l1t} | {l1wr} | {l1pnl} | {l1cand} | {l2t} | {l2wr} | {l2pnl} | {l2cand} | {rbo} | {rrt} | {rct} | {dt} | {dwr} | {dpnl} |".format(
            l1t=tot["l1_trades"],
            l1wr=pct(tot_l1_wr),
            l1pnl=fmt_money(tot["l1_pnl"]),
            l1cand=tot["l1_candidates"],
            l2t=tot["l2_trades"],
            l2wr=pct(tot_l2_wr),
            l2pnl=fmt_money(tot["l2_pnl"]),
            l2cand=tot["l2_candidates"],
            rbo=tot["rej_breakout"],
            rrt=tot["rej_retest"],
            rct=tot["rej_candle"],
            dt=tot_d_trades,
            dwr=f"{tot_d_wr_pp:+.1f} pp",
            dpnl=fmt_money(tot_d_pnl),
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))
    print(f"Wrote comparison to {args.output}")


if __name__ == "__main__":
    main()
