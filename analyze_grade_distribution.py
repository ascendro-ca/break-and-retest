#!/usr/bin/env python3
"""Compute distribution of trade point letters from the latest Level 2 backtest.

Usage:
  python analyze_grade_distribution.py backtest_results/level2_ALL_20250101_20251031_profile_2025-11-10T152515-0800.json
If no argument given, uses the hardcoded latest file path.
"""

import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PATH = Path(
    "backtest_results/level2_ALL_20250101_20251031_profile_2025-11-10T152515-0800.json"
)


def load_results(path: Path):
    with path.open("r") as f:
        return json.load(f)


def compute_distribution(results):
    trade_letter_counts = Counter()
    signal_letter_counts = Counter()
    missing_signal_for_trade = 0
    total_trades = 0
    for sym_res in results:
        # Build lookup by datetime for signals -> points letter
        sig_lookup = {}
        for sig in sym_res.get("signals", []):
            dt = sig.get("datetime")
            letter = sig.get("points", {}).get("letter")
            if dt and letter:
                sig_lookup[dt] = letter
                signal_letter_counts[letter] += 1
        for trade in sym_res.get("trades", []):
            total_trades += 1
            dt = trade.get("datetime")
            letter = sig_lookup.get(dt)
            if letter:
                trade_letter_counts[letter] += 1
            else:
                missing_signal_for_trade += 1
    return {
        "total_trades": total_trades,
        "trade_letter_counts": dict(trade_letter_counts),
        "signal_letter_counts": dict(signal_letter_counts),
        "missing_signal_for_trade": missing_signal_for_trade,
    }


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    results = load_results(path)
    stats = compute_distribution(results)
    print("Grade letter distribution (trades):")
    for k, v in sorted(stats["trade_letter_counts"].items()):
        print(f"  {k}: {v}")
    print(f"Total trades: {stats['total_trades']}")
    print()
    print("Grade letter distribution (all gated signals):")
    for k, v in sorted(stats["signal_letter_counts"].items()):
        print(f"  {k}: {v}")
    if stats["missing_signal_for_trade"]:
        print(f"Trades without matching signal letter: {stats['missing_signal_for_trade']}")


if __name__ == "__main__":
    main()
