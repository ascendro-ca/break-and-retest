#!/usr/bin/env python3
"""
Validate backtest result pairs (JSON + _summary.md) for basic consistency.

Flags potential mismatches where:
- JSON is empty ([]) but summary contains a trades table
    (non "No trades to summarize.")
- JSON is non-empty but summary says "No trades to summarize."
    (could be candidate-only runs; flagged as potential)

Usage:
    python validate_backtest_pairs.py [results_dir]

Defaults to ./backtest_results
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NO_TRADES_MARKER = "_No trades to summarize._"


def infer_json_path(md_path: Path) -> Path:
    name = md_path.name
    if not name.endswith("_summary.md"):
        raise ValueError(f"Not a summary markdown filename: {md_path}")
    json_name = name.replace("_summary.md", ".json")
    return md_path.with_name(json_name)


def read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"__ERROR_READING__: {e}"


def load_json_safely(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f"__ERROR_JSON__: {e}"


def summarize_json_payload(payload) -> dict:
    """Best-effort summary of the JSON payload.

    Returns keys:
      - exists: bool
      - is_list: bool
      - is_empty_list: bool
      - length: int | None
      - trade_count: int | None  # sum of len(trades) per symbol when available, or total_trades
    """
    trade_count = None
    if isinstance(payload, list) and payload:
        tc = 0
        tc_known = False
        for item in payload:
            if isinstance(item, dict):
                # Prefer explicit trades arrays
                tr = item.get("trades")
                if isinstance(tr, list):
                    tc += len(tr)
                    tc_known = True
                else:
                    # Fallback to total_trades metric if present
                    tot = item.get("total_trades")
                    if isinstance(tot, int):
                        tc += tot
                        tc_known = True
        if tc_known:
            trade_count = tc

    summary = {
        "exists": payload is not None,
        "is_list": isinstance(payload, list),
        "is_empty_list": isinstance(payload, list) and len(payload) == 0,
        "length": len(payload) if isinstance(payload, list) else None,
        "trade_count": trade_count,
    }
    return summary


def main() -> int:
    root = Path(__file__).resolve().parent
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "backtest_results"
    if not results_dir.exists():
        print(f"Results dir not found: {results_dir}")
        return 2

    md_files = sorted(results_dir.glob("*_summary.md"))
    if not md_files:
        print(f"No summary files found in {results_dir}")
        return 0

    total = 0
    ok = 0
    mismatches = []
    potential = []
    missing_json = []
    read_errors = []

    for md_path in md_files:
        total += 1
        json_path = infer_json_path(md_path)
        md_text = read_text_safely(md_path)
        if md_text.startswith("__ERROR_READING__:"):
            read_errors.append((md_path.name, md_text))
            continue
        md_has_trades = NO_TRADES_MARKER not in md_text

        if not json_path.exists():
            missing_json.append(md_path.name)
            continue

        payload = load_json_safely(json_path)
        if isinstance(payload, str) and payload.startswith("__ERROR_JSON__:"):
            read_errors.append((json_path.name, payload))
            continue

        js = summarize_json_payload(payload)

        hard_mismatch = False
        pot_mismatch = False
        # Prefer trade_count when available
        if js.get("trade_count") is not None:
            if js["trade_count"] == 0 and md_has_trades:
                hard_mismatch = True
            elif js["trade_count"] > 0 and not md_has_trades:
                hard_mismatch = True
        else:
            # Fallback heuristic on list emptiness
            if js["is_empty_list"] and md_has_trades:
                hard_mismatch = True
            elif (js["is_list"] and js["length"] and js["length"] > 0) and not md_has_trades:
                pot_mismatch = True

        if hard_mismatch:
            mismatches.append((json_path.name, md_path.name, "trade_count_vs_md_disagree"))
        elif pot_mismatch:
            potential.append((json_path.name, md_path.name, "json_nonempty_but_md_no_trades"))
        else:
            ok += 1

    print(f"Scanned: {total} pairs")
    print(f"OK: {ok}")
    if missing_json:
        print(f"Missing JSON for {len(missing_json)} summaries:")
        for name in missing_json[:10]:
            print(f"  - {name}")
        if len(missing_json) > 10:
            print(f"  ... {len(missing_json)-10} more")
    if mismatches:
        print(f"MISMATCHES (hard): {len(mismatches)}")
        for j, m, why in mismatches:
            print(f"  - {j} vs {m} -> {why}")
    if potential:
        print(f"Potential mismatches: {len(potential)}")
        for j, m, why in potential[:20]:
            print(f"  - {j} vs {m} -> {why}")
        if len(potential) > 20:
            print(f"  ... {len(potential)-20} more")
    if read_errors:
        print(f"Read/parse errors: {len(read_errors)}")
        for name, err in read_errors[:10]:
            print(f"  - {name}: {err}")
        if len(read_errors) > 10:
            print(f"  ... {len(read_errors)-10} more")

    # exit code: 0 if no hard mismatches, 1 if hard mismatches exist
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
