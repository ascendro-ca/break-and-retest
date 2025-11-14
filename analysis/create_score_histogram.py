#!/usr/bin/env python3
"""
Build score histograms from a backtest results JSON file.

- Input: backtest_results/*.json produced by backtest.py
- Output: interactive HTML with one bar per exact score
    and hover showing the date range of trades with that score

Usage:
        python analysis/create_score_histogram.py \
            --input backtest_results/<file>.json \
            --mode winners|losers|both \
            --out backtest_results/out.html
If --input is omitted, the script will pick the most recent JSON in backtest_results/.
When --mode both is used, a stacked histogram is produced (red=losers, green=winners).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import plotly.graph_objects as go


def find_latest_results_file(results_dir: Path) -> Path | None:
    candidates = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_trades_scores(path: Path, outcome: str | None = "win") -> List[Dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    rows: List[Dict[str, Any]] = []
    if not isinstance(data, list):
        return rows
    for res in data:
        symbol = res.get("symbol")
        for t in res.get("trades") or []:
            if outcome is not None and t.get("outcome") != outcome:
                continue
            # Prefer the convenience field, fall back to points.total
            score = t.get("score_total")
            if score is None:
                pts = t.get("points") or {}
                score = pts.get("total") if isinstance(pts, dict) else None
            if score is None:
                continue
            try:
                score_f = float(score)
            except Exception:
                continue
            rows.append(
                {
                    "symbol": t.get("symbol", symbol),
                    "datetime": t.get("datetime"),
                    "score": score_f,
                    "outcome": t.get("outcome"),
                }
            )
    return rows


def group_by_score(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group by exact integer score and compute date ranges for hover."""
    if not rows:
        return []
    buckets: Dict[int, List[str]] = {}
    for w in rows:
        try:
            score_i = int(round(float(w.get("score", 0))))
        except Exception:
            continue
        buckets.setdefault(score_i, []).append(w.get("datetime"))

    def parse_dt(s: str) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None

    grouped: List[Dict[str, Any]] = []
    for score in sorted(buckets.keys()):
        ts_list = [parse_dt(s) for s in buckets[score]]
        ts_list = [t for t in ts_list if t is not None]
        if ts_list:
            dmin = min(ts_list).date().isoformat()
            dmax = max(ts_list).date().isoformat()
            hover = f"Date range: {dmin} — {dmax}"
        else:
            hover = "Date range: n/a"
        grouped.append({"score": score, "count": len(buckets[score]), "hover_text": hover})
    return grouped


def group_by_score_both(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group by score with separate loser and winner counts and date ranges."""
    if not rows:
        return []
    losers: Dict[int, List[str]] = {}
    winners: Dict[int, List[str]] = {}
    for r in rows:
        try:
            s = int(round(float(r.get("score", 0))))
        except Exception:
            continue
        dt = r.get("datetime")
        if r.get("outcome") == "loss":
            losers.setdefault(s, []).append(dt)
        elif r.get("outcome") == "win":
            winners.setdefault(s, []).append(dt)

    def daterange(vals: List[str]) -> str:
        def p(x: str) -> datetime | None:
            try:
                return datetime.fromisoformat(x)
            except Exception:
                return None

        ts = [p(v) for v in vals if v]
        ts = [t for t in ts if t is not None]
        if not ts:
            return "n/a"
        return f"{min(ts).date().isoformat()} — {max(ts).date().isoformat()}"

    all_scores = sorted(set(losers.keys()) | set(winners.keys()))
    out: List[Dict[str, Any]] = []
    for s in all_scores:
        lc = len(losers.get(s, []))
        wc = len(winners.get(s, []))
        out.append(
            {
                "score": s,
                "loss_count": lc,
                "win_count": wc,
                "loss_range": daterange(losers.get(s, [])),
                "win_range": daterange(winners.get(s, [])),
            }
        )
    return out


def make_figure(grouped: List[Dict[str, Any]], title: str) -> go.Figure:
    x = [g["score"] for g in grouped]
    y = [g["count"] for g in grouped]
    custom = [g["hover_text"] for g in grouped]
    fig = go.Figure(
        data=[
            go.Bar(
                x=x,
                y=y,
                customdata=custom,
                hovertemplate=("Score %{x}<br>count=%{y}<br>%{customdata}<extra></extra>"),
                marker_color="#3b82f6",
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title="Scores",
        yaxis_title="Count",
        bargap=0.05,
        template="plotly_white",
    )
    return fig


def make_figure_both(grouped: List[Dict[str, Any]], title: str) -> go.Figure:
    x = [g["score"] for g in grouped]
    y_loss = [g["loss_count"] for g in grouped]
    y_win = [g["win_count"] for g in grouped]
    hover_loss = [f"Losses: {g['loss_count']}<br>Date range: {g['loss_range']}" for g in grouped]
    hover_win = [f"Wins: {g['win_count']}<br>Date range: {g['win_range']}" for g in grouped]

    fig = go.Figure(
        data=[
            go.Bar(
                name="Losses",
                x=x,
                y=y_loss,
                customdata=hover_loss,
                hovertemplate=("Score %{x}<br>%{customdata}<extra></extra>"),
                marker_color="#ef4444",
            ),
            go.Bar(
                name="Wins",
                x=x,
                y=y_win,
                customdata=hover_win,
                hovertemplate=("Score %{x}<br>%{customdata}<extra></extra>"),
                marker_color="#22c55e",
            ),
        ]
    )
    fig.update_layout(
        barmode="stack",
        title=title,
        xaxis_title="Scores",
        yaxis_title="Count",
        bargap=0.05,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def main():
    parser = argparse.ArgumentParser(description="Score histogram(s) from backtest results")
    parser.add_argument("--input", type=str, default=None, help="Path to backtest results JSON")
    parser.add_argument("--out", type=str, default=None, help="Output HTML path")
    parser.add_argument(
        "--mode",
        choices=["winners", "losers", "both"],
        default="winners",
        help="Which histogram to generate (default: winners)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    results_dir = root / "backtest_results"

    in_path: Path | None
    if args.input:
        in_path = Path(args.input)
    else:
        in_path = find_latest_results_file(results_dir)
    if not in_path or not in_path.exists():
        raise SystemExit("No input results JSON found.")

    if args.mode == "winners":
        rows = load_trades_scores(in_path, outcome="win")
        if not rows:
            raise SystemExit("No winners found in the provided results file.")
        grouped = group_by_score(rows)
    elif args.mode == "losers":
        rows = load_trades_scores(in_path, outcome="loss")
        if not rows:
            raise SystemExit("No losers found in the provided results file.")
        grouped = group_by_score(rows)
    else:
        rows = load_trades_scores(in_path, outcome=None)
        if not rows:
            raise SystemExit("No trades found in the provided results file.")
        grouped_both = group_by_score_both(rows)

    # Default output path based on input name
    if args.out:
        out_path = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = {"winners": "winner", "losers": "loser", "both": "combined"}[args.mode]
        out_path = results_dir / f"{suffix}_score_histogram_{ts}.html"

    if args.mode == "both":
        title = f"Score Histogram (Stacked) — {in_path.name}"
        fig = make_figure_both(grouped_both, title=title)
    else:
        title = f"{args.mode.capitalize()} Score Histogram — {in_path.name}"
        fig = make_figure(grouped, title=title)
    fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True)

    print(f"Histogram saved to {out_path}")


if __name__ == "__main__":
    main()
