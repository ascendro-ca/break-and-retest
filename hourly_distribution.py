# ruff: noqa: I001
"""Generate per-hour distribution comparison between two backtest result JSON files.

Reads Level 1 and Level 2 backtest JSON outputs (each a list of per-symbol
objects containing a `signals` array with `datetime` ISO strings). Aggregates
counts by hour (both local timezone from the JSON and converted US/Eastern) and
produces a CSV plus an optional Plotly HTML histogram.

Usage:
    python hourly_distribution.py \
        --level1 backtest_results/level1_ALL_20250101_20251031_points_2025-11-08T105047-0800.json \
        --level2 backtest_results/level2_ALL_20250101_20251031_points_2025-11-08T105736-0800.json \
        --output backtest_results/hourly_distribution_level1_vs_level2_20250101_20251031.csv \
        --html   backtest_results/hourly_distribution_level1_vs_level2_20250101_20251031.html

Columns written:
    hour_local          Hour extracted from original timezone stamps (0-23)
    hour_et             Hour after conversion to US/Eastern
    level1_count        Number of signals in Level 1 during that hour
    level2_count        Number of signals in Level 2 during that hour
    l2_to_l1_ratio      level2_count / level1_count (NaN if level1_count == 0)
    level1_pct          Percentage of total Level 1 signals for that hour
    level2_pct          Percentage of total Level 2 signals for that hour

If Plotly is available a stacked bar chart (Level1 vs Level2 by Eastern hour)
is saved to the provided --html path.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

import pandas as pd

try:  # third-party optional
    import plotly.express as px  # type: ignore
except Exception:  # pragma: no cover - plotly optional
    px = None  # type: ignore


def load_signal_datetimes(path: Path) -> List[str]:
    """Extract all signal datetime strings from a backtest JSON file.

    File format: list of per-symbol objects, each with a `signals` list of dicts
    containing a `datetime` key (ISO8601 with timezone offset).
    """
    with path.open("r") as f:
        data = json.load(f)
    datetimes: List[str] = []
    for symbol_obj in data:
        for sig in symbol_obj.get("signals", []):
            dt = sig.get("datetime")
            if dt:
                datetimes.append(dt)
    return datetimes


def parse_hours(datetimes: List[str]) -> pd.DataFrame:
    """Return DataFrame with columns: datetime_original (str), hour_local, hour_et."""
    rows = []
    eastern = ZoneInfo("US/Eastern")
    for dt_str in datetimes:
        # Robust ISO parsing with timezone offset
        dt = datetime.fromisoformat(dt_str)
        hour_local = dt.hour
        # Convert to Eastern for normalized market hour comparisons
        dt_et = dt.astimezone(eastern)
        hour_et = dt_et.hour
        rows.append((dt_str, hour_local, hour_et))
    return pd.DataFrame(rows, columns=["datetime", "hour_local", "hour_et"])


def aggregate(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Aggregate counts by local and ET hour, returning wide format with counts."""
    by_hour = df.groupby(["hour_local", "hour_et"]).size().reset_index(name=f"{label}_count")
    return by_hour


def build_distribution(level1_path: Path, level2_path: Path) -> pd.DataFrame:
    l1_datetimes = load_signal_datetimes(level1_path)
    l2_datetimes = load_signal_datetimes(level2_path)

    l1_df = parse_hours(l1_datetimes)
    l2_df = parse_hours(l2_datetimes)

    l1_ag = aggregate(l1_df, "level1")
    l2_ag = aggregate(l2_df, "level2")

    merged = pd.merge(l1_ag, l2_ag, on=["hour_local", "hour_et"], how="outer").fillna(0)

    # Add percentage columns
    total_l1 = merged["level1_count"].sum()
    total_l2 = merged["level2_count"].sum()
    merged["level1_pct"] = merged["level1_count"].div(total_l1).mul(100).round(3)
    merged["level2_pct"] = merged["level2_count"].div(total_l2).mul(100).round(3)
    merged["l2_to_l1_ratio"] = merged.apply(
        lambda r: (r["level2_count"] / r["level1_count"])
        if r["level1_count"] > 0
        else float("nan"),
        axis=1,
    ).round(4)

    # Sort by Eastern hour (market-centric) then local hour
    merged = merged.sort_values(["hour_et", "hour_local"]).reset_index(drop=True)
    return merged


def write_csv(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def write_html(df: pd.DataFrame, html_path: Path) -> None:  # pragma: no cover - visualization
    if px is None:
        return
    fig = px.bar(
        df,
        x="hour_et",
        y=["level1_count", "level2_count"],
        barmode="group",
        title="Per-Hour Signal Counts (Level1 vs Level2, Eastern Time)",
        labels={"hour_et": "Hour (ET)", "value": "Count", "variable": "Level"},
    )
    fig.update_layout(legend_title_text="Level")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(html_path))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate per-hour Level1 vs Level2 distribution CSV")
    p.add_argument("--level1", required=True, type=Path, help="Path to Level 1 backtest JSON")
    p.add_argument("--level2", required=True, type=Path, help="Path to Level 2 backtest JSON")
    p.add_argument("--output", required=True, type=Path, help="CSV output path")
    p.add_argument("--html", type=Path, help="Optional HTML histogram output path")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = build_distribution(args.level1, args.level2)
    write_csv(df, args.output)
    if args.html:
        write_html(df, args.html)
    print(f"Wrote hourly distribution CSV: {args.output}")
    if args.html:
        print(f"Wrote histogram HTML: {args.html}")
    # Print quick summary top 5 hours by Level2 density
    top = df.sort_values("level2_pct", ascending=False).head(5)
    print("Top 5 Level2 hours (ET) by percentage:")
    for _, row in top.iterrows():
        print(
            f"HourET={row.hour_et} L2={row.level2_count} ({row.level2_pct}%) "
            f"L1={row.level1_count} ratio={row.l2_to_l1_ratio}"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
