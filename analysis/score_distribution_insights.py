#!/usr/bin/env python3
"""
Analyze score distribution patterns from backtest results JSON.

Usage:
  python analysis/score_distribution_insights.py --input backtest_results/<file>.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Tuple


@dataclass
class TradeRow:
    score: float
    outcome: str
    symbol: str | None
    dt: str | None


def load_trades(path: Path) -> List[TradeRow]:
    with open(path, "r") as f:
        data = json.load(f)
    rows: List[TradeRow] = []
    for res in data:
        sym = res.get("symbol")
        for t in res.get("trades") or []:
            pts = t.get("points") or {}
            s = t.get("score_total", pts.get("total"))
            if s is None:
                continue
            try:
                s_f = float(s)
            except Exception:
                continue
            rows.append(
                TradeRow(score=s_f, outcome=str(t.get("outcome")), symbol=sym, dt=t.get("datetime"))
            )
    return rows


def summarize(rows: List[TradeRow]) -> Dict[str, Any]:
    if not rows:
        return {}
    scores = [r.score for r in rows]
    wins = [r for r in rows if r.outcome == "win"]
    losses = [r for r in rows if r.outcome == "loss"]
    forced = [r for r in rows if r.outcome == "forced"]

    # Counts by exact integer score
    def i(x: float) -> int:
        try:
            return int(round(x))
        except Exception:
            return 0

    by_score: Dict[int, List[TradeRow]] = defaultdict(list)
    for r in rows:
        by_score[i(r.score)].append(r)

    # Win rate by score with sample size
    winrate_by_score: Dict[int, Tuple[float, int]] = {}
    for sc, items in sorted(by_score.items()):
        n = len(items)
        wins_n = sum(1 for r in items if r.outcome == "win")
        winrate_by_score[sc] = (wins_n / n if n else 0.0, n)

    # Threshold sweep (>=T)
    def sweep(thresholds: List[int]) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        for T in thresholds:
            filt = [r for r in rows if i(r.score) >= T]
            n = len(filt)
            w = sum(1 for r in filt if r.outcome == "win")
            out[T] = {
                "n": n,
                "win_rate": (w / n if n else 0.0),
            }
        return out

    thresholds = list(range(56, 101))
    sweep_stats = sweep(thresholds)

    # Concentration near threshold band [56, 62]
    band_low, band_high = 56, 62
    in_band = [r for r in rows if band_low <= i(r.score) <= band_high]

    # Identify crossover score where wins exceed losses by score
    crossover: List[Tuple[int, int, int]] = []
    for sc, items in sorted(by_score.items()):
        wins_n = sum(1 for r in items if r.outcome == "win")
        losses_n = sum(1 for r in items if r.outcome == "loss")
        crossover.append((sc, wins_n, losses_n))

    # Top scores by win rate with minimum sample size
    min_n = 10
    top = sorted(
        [(sc, wr, n) for sc, (wr, n) in winrate_by_score.items() if n >= min_n],
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    # Compose summary
    summary: Dict[str, Any] = {
        "n_trades": len(rows),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_forced": len(forced),
        "win_rate_overall": (len(wins) / len(rows) if rows else 0.0),
        "score_mean": mean(scores),
        "score_median": median(scores),
        "score_mean_wins": mean([r.score for r in wins]) if wins else None,
        "score_mean_losses": mean([r.score for r in losses]) if losses else None,
        "concentration_band": {
            "band": [band_low, band_high],
            "count": len(in_band),
            "share": (len(in_band) / len(rows) if rows else 0.0),
        },
        "winrate_by_score": winrate_by_score,
        "sweep_ge_threshold": sweep_stats,
        "crossover_counts": crossover,
        "top_scores_by_winrate": top,
    }
    return summary


def format_report(summary: Dict[str, Any]) -> str:
    if not summary:
        return "No data"
    lines: List[str] = []

    def pct(x: float) -> str:
        return f"{100*x:.1f}%"

    lines.append("\n=== OVERALL ===")
    lines.append(
        " ".join(
            [
                f"Trades: {summary['n_trades']}",
                f"Wins: {summary['n_wins']}",
                f"Losses: {summary['n_losses']}",
                f"Forced: {summary['n_forced']}",
            ]
        )
    )
    lines.append(f"Win rate: {pct(summary['win_rate_overall'])}")
    lines.append(
        f"Scores — mean: {summary['score_mean']:.1f}, median: {summary['score_median']:.1f}, "
        f"wins mean: {summary['score_mean_wins']:.1f} "
        f"losses mean: {summary['score_mean_losses']:.1f}"
    )

    band = summary["concentration_band"]
    lines.append(
        "Concentration near threshold "
        f"[{band['band'][0]}-{band['band'][1]}]: "
        f"{band['count']} trades ({pct(band['share'])})"
    )

    # Crossover (first score with wins > losses)
    first_win_dom = next(
        (
            (sc, wins_n, losses_n)
            for sc, wins_n, losses_n in summary["crossover_counts"]
            if wins_n > losses_n
        ),
        None,
    )
    if first_win_dom:
        lines.append(
            "First score where wins > losses: "
            f"{first_win_dom[0]} (wins={first_win_dom[1]}, "
            f"losses={first_win_dom[2]})"
        )

    # Thresholds where win rate crosses targets
    for target in (0.5, 0.6, 0.7):
        hit = next(
            (
                T
                for T in range(56, 101)
                if summary["sweep_ge_threshold"][T]["win_rate"] >= target
                and summary["sweep_ge_threshold"][T]["n"] >= 20
            ),
            None,
        )
        if hit is not None:
            lines.append(
                f"Win rate >= {int(target*100)}% for scores >= {hit} "
                f"(n={summary['sweep_ge_threshold'][hit]['n']})"
            )

    # Top win-rate scores (min sample size)
    lines.append("\nTop scores by win rate (min n=10):")
    for sc, wr, n in summary["top_scores_by_winrate"]:
        lines.append(f"  Score {sc}: win rate {pct(wr)} (n={n})")

    # Win-rate by score (compact): show a few representative points
    lines.append("\nWin rate by score (selected):")
    for sc in (56, 60, 65, 70, 75, 80, 85, 90, 95):
        wr, n = summary["winrate_by_score"].get(sc, (None, None))
        if wr is not None:
            lines.append(f"  {sc}: {pct(wr)} (n={n})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Score distribution insights")
    parser.add_argument("--input", required=True, help="Path to backtest results JSON")
    args = parser.parse_args()

    path = Path(args.input)
    rows = load_trades(path)
    summary = summarize(rows)
    print(format_report(summary))


if __name__ == "__main__":
    main()
