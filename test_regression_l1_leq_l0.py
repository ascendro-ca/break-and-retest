import json
from pathlib import Path
import re

import pytest
# ruff: noqa: I001


BACKTEST_DIR = Path(__file__).parent / "backtest_results"


def _parse_filename_meta(path: Path):
    """
    Parse backtest result filenames created by backtest.py into components.

    Expected pattern:
      level{n}_{symbols}_{start}_{end}_{grading}_{timestamp}.json

    Returns a dict with keys: level, symbols, start, end, grading, timestamp.
    If parsing fails, returns None.
    """
    # Use robust split around underscores, but keep timestamp intact (it contains '-')
    # Examples:
    #   level0_ALL_20250101_20251031_points_2025-11-06T110823-0800.json
    #   level1_ALL_20250106_20250110_points_2025-11-06T110554-0800.json
    name = path.stem  # drop .json
    parts = name.split("_")
    if len(parts) < 6:
        return None

    level_part = parts[0]
    if not level_part.startswith("level"):
        return None
    try:
        level = int(level_part.replace("level", ""))
    except ValueError:
        return None

    symbols = parts[1]
    start = parts[2]
    end = parts[3]
    grading = parts[4]
    # Timestamp might itself contain underscores in some legacy outputs; join the rest
    timestamp = "_".join(parts[5:])

    # Basic validations
    if not re.fullmatch(r"\d{8}", start):
        return None
    if not re.fullmatch(r"\d{8}", end):
        return None

    return {
        "level": level,
        "symbols": symbols,
        "start": start,
        "end": end,
        "grading": grading,
        "timestamp": timestamp,
    }


def _load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def _aggregate_counts(results_json):
    """Sum total_trades and candidate_count across all symbols in results list."""
    total_trades = 0
    total_candidates = 0
    # Results JSON is a list of per-symbol dicts
    for res in results_json:
        total_trades += int(res.get("total_trades", 0) or 0)
        total_candidates += int(res.get("candidate_count", 0) or 0)
    return total_trades, total_candidates


def _find_latest_pair_by_range():
    """
    Find the latest Level 0 and Level 1 JSON pair for the same
    symbols/start/end/grading. Returns (path_l0, path_l1) or (None, None).
    """
    if not BACKTEST_DIR.exists():
        return None, None

    # Index files by key=(symbols,start,end,grading) with latest timestamp
    l0_index = {}
    l1_index = {}

    for path in BACKTEST_DIR.glob("level*_*.json"):
        meta = _parse_filename_meta(path)
        if not meta:
            continue
        key = (meta["symbols"], meta["start"], meta["end"], meta["grading"])
        # Normalize timestamp string to compare (lexicographic works for ISO-like format)
        ts = meta["timestamp"]
        if meta["level"] == 0:
            prev = l0_index.get(key)
            if not prev or ts > prev[0]:
                l0_index[key] = (ts, path)
        elif meta["level"] == 1:
            prev = l1_index.get(key)
            if not prev or ts > prev[0]:
                l1_index[key] = (ts, path)

    # Intersect keys and pick the latest common pair by timestamp intersection
    common = set(l0_index.keys()) & set(l1_index.keys())
    if not common:
        return None, None

    # Choose the pair with the maximum min(ts_l0, ts_l1) to ensure both are fresh
    best = None
    best_score = None
    for key in common:
        ts0, p0 = l0_index[key]
        ts1, p1 = l1_index[key]
        score = min(ts0, ts1)
        if best is None or score > best_score:
            best = (p0, p1)
            best_score = score

    return best if best else (None, None)


def test_level1_trades_do_not_exceed_level0_candidates():
    """
    Regression: For the same date range and symbols, total Level 1 trades must be
    less than or equal to total Level 0 candidates.

    If matching artifacts are not present under backtest_results/, the test is skipped.
    """
    l0_path, l1_path = _find_latest_pair_by_range()
    if not l0_path or not l1_path:
        pytest.skip(
            "No matching Level 0/1 backtest artifacts found. Run backtests to generate them."
        )

    l0_json = _load_json(l0_path)
    l1_json = _load_json(l1_path)

    # Aggregate counts across symbols
    _, l0_candidates = _aggregate_counts(l0_json)
    l1_trades, _ = _aggregate_counts(l1_json)

    assert l1_trades <= l0_candidates, (
        f"Invariant broken: Level 1 trades ({l1_trades}) > Level 0 candidates ({l0_candidates}).\n"
        f"Level 0 file: {l0_path.name}\nLevel 1 file: {l1_path.name}"
    )
