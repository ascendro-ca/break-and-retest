#!/usr/bin/env python3
"""
Summarize a deduplicated markdown trade summary.

Computes:
  - Total trades
  - Wins, Losses, Forced counts
  - Win rate (wins / (wins + losses)) and overall win rate (wins / total)
  - Total P&L sum

Usage:
  python analysis/summarize_dedup_summary.py --input <dedup_summary.md>
"""

from __future__ import annotations

import argparse


def parse_row(line: str):
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    total = 0
    wins = 0
    losses = 0
    forced = 0
    pnl_sum = 0.0

    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s.startswith("|"):
                continue
            if s.startswith("|---"):
                continue
            # Header line starts with '| Date (PST)'
            if s.startswith("| Date (PST)"):
                continue
            parts = parse_row(s)
            if len(parts) < 18:
                continue
            total += 1
            outcome = parts[10].lower()
            if outcome == "win":
                wins += 1
            elif outcome == "loss":
                losses += 1
            elif outcome == "forced":
                forced += 1
            # P&L column index 13
            try:
                pnl = float(parts[13])
            except Exception:
                pnl = 0.0
            pnl_sum += pnl

    denom_wl = max(1, wins + losses)  # avoid div-by-zero
    win_rate_ex_forced = wins / denom_wl
    win_rate_overall = wins / max(1, total)

    print("Summary metrics (deduped):")
    print(f"- Total trades: {total}")
    print(f"  - Wins: {wins}")
    print(f"  - Losses: {losses}")
    print(f"  - Forced: {forced}")
    win_rate_pct_str = f"{win_rate_ex_forced*100:.1f}%"
    print(f"- Win rate (wins / (wins + losses)): {win_rate_ex_forced:.4f} ({win_rate_pct_str})")
    print(f"- Win rate (wins / total): {win_rate_overall:.4f} ({win_rate_overall*100:.1f}%)")
    print(f"- Total P&L: {pnl_sum:.2f}")


if __name__ == "__main__":
    main()
