#!/usr/bin/env python3
"""Collapse a backtest summary markdown table by key.

Groups rows by (Date (PST), Symbol, Entry Time) and retains a single
representative (first occurrence) while reporting duplicate statistics.

Usage:
    python analysis/collapse_summary_by_key.py \
        --input backtest_results/<summary>.md \
        [--output <path>] \
        [--key symbol_timestamp]

Notes:
    - Key 'symbol_timestamp' maps to (Date (PST), Symbol, Entry Time) columns.
    - Representative prefers highest 'Score'; ties fall back to Grade letter
        (A>B>C>D). If still tied, first occurrence is retained.
    - Preserves the original header and column order.
"""

import argparse
import os
from typing import Dict, List, Tuple

# Table header (split for readability, then joined)
HEADER_PREFIX = (
    "| Date (PST) | Entry Time | Exit Time | Time in trade (min) | Symbol | Dir | Entry | Stop | "
    "Target | Exit | Outcome | Risk | R/R | P&L | Shares | Grade | Score | CompPts |"
)
DIVIDER_PREFIX = "|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:"


def parse_row(line: str) -> List[str]:
    # Expect a pipe-delimited row; strip leading/trailing pipes and spaces
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def grade_rank(grade: str) -> int:
    order = {"A": 4, "B": 3, "C": 2, "D": 1}
    return order.get(grade.strip().upper(), 0)


def row_key(parts: List[str]) -> Tuple[str, str, str]:
    # Columns: Date (0), Entry Time (1), ..., Symbol (4)
    # Key: (date, symbol, entry_time)
    try:
        date = parts[0]
        entry_time = parts[1]
        symbol = parts[4]
    except Exception:
        # Fallback to avoid crash; use entire row as key
        return ("", "", "")
    return (date, symbol, entry_time)


def choose_representative(rows: List[List[str]]) -> List[str]:
    """Keep the first occurrence as the representative row.

    Assumes rows are appended in the order they appear in the input summary,
    so rows[0] is the earliest occurrence for the grouped key.
    """
    return rows[0]


def collapse_summary(lines: List[str]) -> Tuple[List[str], Dict[str, int], int, int]:
    """
    Returns:
      new_lines: collapsed markdown lines
      dup_sizes: mapping "date|symbol|entry_time" -> group size (only for >1)
      original_rows: number of data rows parsed
      collapsed_rows: number of rows after collapsing
    """
    out_lines: List[str] = []

    # Pass through header and divider; detect start of table
    header_seen = False
    divider_seen = False
    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            out_lines.append(line)
            continue
        if not header_seen and line.strip().startswith("| Date (PST)"):
            out_lines.append(HEADER_PREFIX)
            header_seen = True
            continue
        if header_seen and not divider_seen and line.strip().startswith("|---"):
            out_lines.append(DIVIDER_PREFIX)
            divider_seen = True
            break
        # Before the table, pass through any non-table lines
        out_lines.append(line)

    # Collect data rows from remaining lines
    data_lines = lines[len(out_lines) :]
    groups: Dict[Tuple[str, str, str], List[List[str]]] = {}
    original_rows = 0
    for line in data_lines:
        s = line.strip()
        if not s.startswith("|"):
            # end of table or empty line
            continue
        if s.startswith("|---"):
            continue
        parts = parse_row(s)
        # Expect at least 18 columns
        if len(parts) < 18:
            continue
        original_rows += 1
        key = row_key(parts)
        groups.setdefault(key, []).append(parts)

    # Build collapsed rows
    dedup_sizes: Dict[str, int] = {}
    collapsed: List[List[str]] = []
    for k, rows in groups.items():
        rep = choose_representative(rows)
        collapsed.append(rep)
        if len(rows) > 1:
            date, symbol, entry_time = k
            dedup_sizes[f"{date}|{symbol}|{entry_time}"] = len(rows)

    # Emit collapsed rows in first-seen order (preserve original summary order)
    for r in collapsed:
        out_lines.append("| " + " | ".join(r) + " |")

    return out_lines, dedup_sizes, original_rows, len(collapsed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to original summary .md")
    ap.add_argument(
        "--output",
        help="Path to write collapsed summary .md; defaults to <input> with _dedup suffix",
    )
    args = ap.parse_args()

    in_path = args.input
    out_path = args.output
    if out_path is None:
        base, ext = os.path.splitext(in_path)
        out_path = base + "_dedup" + ext

    with open(in_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines, dup_sizes, original_rows, collapsed_rows = collapse_summary(lines)

    # Prepend a small stats block
    stats_block = []
    stats_block.append("")
    stats_block.append("### Deduplication stats")
    stats_block.append("")
    stats_block.append(f"- Original rows: {original_rows}")
    stats_block.append(f"- Collapsed rows (unique by date, symbol, entry time): {collapsed_rows}")
    stats_block.append(f"- Duplicates removed: {original_rows - collapsed_rows}")
    if dup_sizes:
        # show top 10 groups by size
        top = sorted(dup_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
        stats_block.append("- Top duplicate keys (date|symbol|entry_time -> count):")
        for k, v in top:
            stats_block.append(f"  - {k} -> {v}")
    stats_block.append("")

    # Insert stats block after the main title '## Trade summary (all entries)'
    # Find the index of the first title line
    insert_at = None
    for i, line in enumerate(new_lines):
        if line.strip().startswith("## Trade summary"):
            insert_at = i + 1
            break
    if insert_at is None:
        insert_at = 0
    new_lines = (
        new_lines[:insert_at]
        + [line + ("\n" if not line.endswith("\n") else "") for line in stats_block]
        + new_lines[insert_at:]
    )

    with open(out_path, "w", encoding="utf-8") as f:
        for line in new_lines:
            if not line.endswith("\n"):
                line += "\n"
            f.write(line)

    print(f"Wrote deduplicated summary to: {out_path}")
    print(f"Original rows: {original_rows}")
    print(f"Collapsed rows: {collapsed_rows}")
    print(f"Duplicates removed: {original_rows - collapsed_rows}")


if __name__ == "__main__":
    main()
