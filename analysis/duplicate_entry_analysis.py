"""Quick duplicate entry analysis for backtest console output tables.

Parses saved console output files (ungated vs gated) and counts how many
trades share identical (date, entry time, symbol) keys, treating those as
duplicate emissions. This is a heuristic: the console table may wrap rows,
so we only consider the first line fragments that begin with a pipe and a
date string (YYYY-MM-DD) and assume columns are pipe-delimited.

Usage (from repo root):
  python analysis/duplicate_entry_analysis.py \
      --ungated analysis/ungated_jan01_15.txt \
      --gated   analysis/gated_jan01_15.txt

Outputs summary stats for each file and comparative suppression metrics.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Dict

ROW_PATTERN = re.compile(r"^\|\s*20\d{2}-\d{2}-\d{2}\s*\|")


def extract_keys(path: Path) -> Counter:
    """Extract (date, entry_time, symbol) keys from a console output file.

    We look for lines that start with a pipe + date. For each such line we
    split on pipes, drop empty fragments, then take indices:
        0 -> date, 1 -> entry time, 4 -> symbol
    If the expected indices are missing, the line is skipped.
    """
    counts: Counter = Counter()
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not ROW_PATTERN.match(line):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            # Need at least 5 columns to safely access symbol.
            if len(parts) < 5:
                continue
            date, entry_time, _exit_time, _mins, symbol = parts[:5]
            key = (date, entry_time, symbol)
            counts[key] += 1
    return counts


def summarize(counts: Counter) -> Dict[str, float]:
    total = sum(counts.values())
    unique = len(counts)
    duplicates = total - unique
    duplicate_ratio = duplicates / total if total else 0.0
    avg_dupes_per_affected = (duplicates / unique) if unique else 0.0
    return {
        "total_rows": total,
        "unique_keys": unique,
        "duplicates": duplicates,
        "duplicate_ratio": duplicate_ratio,
        "avg_dupes_per_affected_key": avg_dupes_per_affected,
    }


def format_summary(label: str, stats: Dict[str, float]) -> str:
    return (
        f"{label} Summary:\n"
        f"  Total rows parsed: {stats['total_rows']}\n"
        f"  Unique (date, entry, symbol) keys: {stats['unique_keys']}\n"
        f"  Duplicate rows: {stats['duplicates']}\n"
        f"  Duplicate ratio: {stats['duplicate_ratio']*100:.1f}%\n"
        f"  Avg duplicates per affected key: {stats['avg_dupes_per_affected_key']:.2f}\n"
    )


def compare(ungated: Dict[str, float], gated: Dict[str, float]) -> str:
    suppression = (
        (ungated["duplicates"] - gated["duplicates"]) / ungated["duplicates"] * 100
        if ungated["duplicates"]
        else 0.0
    )
    trade_reduction = (
        (ungated["total_rows"] - gated["total_rows"]) / ungated["total_rows"] * 100
        if ungated["total_rows"]
        else 0.0
    )
    return (
        "Comparative Impact:\n"
        f"  Duplicate suppression: {suppression:.1f}%\n"
        f"  Total trade count reduction: {trade_reduction:.1f}%\n"
        f"  Remaining duplicate ratio (gated): {gated['duplicate_ratio']*100:.1f}%\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ungated", required=True, type=Path)
    parser.add_argument("--gated", required=True, type=Path)
    args = parser.parse_args()

    ungated_counts = extract_keys(args.ungated)
    gated_counts = extract_keys(args.gated)

    ungated_stats = summarize(ungated_counts)
    gated_stats = summarize(gated_counts)

    print(format_summary("Ungated", ungated_stats))
    print(format_summary("Gated", gated_stats))
    print(compare(ungated_stats, gated_stats))

    # Show a few worst duplicate keys for diagnostic insight.
    dup_keys = [(k, c) for k, c in ungated_counts.items() if c > 1]
    dup_keys.sort(key=lambda x: x[1], reverse=True)
    if dup_keys:
        print("Top duplicate keys (ungated):")
        for (date, entry, symbol), c in dup_keys[:10]:
            print(f"  {date} {entry} {symbol}: {c} trades")
    else:
        print("No duplicates detected in ungated output (unexpected).")


if __name__ == "__main__":
    main()
