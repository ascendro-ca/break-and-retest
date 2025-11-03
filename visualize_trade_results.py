#!/usr/bin/env python3
"""
Utility: Plot specific trades from backtest results using cached OHLCV.

Examples:
  python visualize_trade_results.py \
    --results backtest_results/backtest_results/level1_all_2025-09-01_to_2025-10-31.json \
    --symbol TSLA --date 2025-09-11 --out logs/tsla_20250911_trades.html

  python visualize_trade_results.py \
    --results backtest_results/backtest_results/level1_all_2025-09-01_to_2025-10-31.json \
    --symbol AMZN --date 2025-10-03 --out logs/amzn_20251003_trades.html

Notes:
- Expects cache files under cache/<SYMBOL>/<YYYY-MM-DD>_5m.csv (UTC timestamps)
- Falls back to 1m cache if 5m not available
- Overlays entry/stop/target lines for filtered trades on that date
"""

from __future__ import annotations

import argparse
import json
import os
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from cache_utils import DEFAULT_CACHE_DIR, load_cached_day
from visualize_test_results import create_chart


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot specific trades from a backtest results JSON")
    p.add_argument("--results", required=True, help="Path to backtest results JSON")
    p.add_argument("--symbol", required=True, help="Symbol to plot (e.g., TSLA)")
    p.add_argument("--date", required=True, help="Trade date (YYYY-MM-DD, UTC date)")
    p.add_argument(
        "--times",
        nargs="*",
        default=None,
        help=(
            "Optional trade datetimes to include (UTC, 'YYYY-MM-DD HH:MM:SS+00:00'). "
            "If omitted, plots all trades for the symbol on the date."
        ),
    )
    p.add_argument("--interval", default="5m", choices=["1m", "5m"], help="Cache interval to use")
    p.add_argument(
        "--out", default=None, help="Output HTML file (defaults to logs/<sym>_<date>_trades.html)"
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open browser tabs (for CI/headless runs)",
    )
    return p.parse_args()


def _load_results(path: Path) -> List[Dict]:
    with open(path, "r") as f:
        data = json.load(f)
    # Expected shape: list of per-symbol summaries with 'symbol', 'trades' keys
    return data if isinstance(data, list) else []


def _filter_trades(
    results: List[Dict], symbol: str, date_str: str, times: Optional[List[str]]
) -> List[Dict]:
    out: List[Dict] = []
    for sym_block in results:
        if sym_block.get("symbol") != symbol:
            continue
        for trade in sym_block.get("trades", []):
            dt = trade.get("datetime")
            if not dt:
                continue
            try:
                ts = pd.to_datetime(dt)
            except Exception:
                continue
            if ts.strftime("%Y-%m-%d") != date_str:
                continue
            if times and dt not in times:
                continue
            out.append(trade)
    # Sort by datetime for consistent overlays
    out.sort(key=lambda t: t.get("datetime", ""))
    return out


def _load_day_df(symbol: str, date_str: str, interval: str) -> Optional[pd.DataFrame]:
    # Try requested interval first
    df = load_cached_day(DEFAULT_CACHE_DIR, symbol, date_str, interval)
    if df is not None and not df.empty:
        return df
    # Fallback: try the other interval
    alt = "1m" if interval == "5m" else "5m"
    df = load_cached_day(DEFAULT_CACHE_DIR, symbol, date_str, alt)
    return df


def main():
    args = _parse_args()
    results_path = Path(args.results)
    symbol = args.symbol.upper()
    date_str = args.date
    times = args.times

    if not results_path.exists():
        raise SystemExit(f"Results file not found: {results_path}")

    results = _load_results(results_path)
    trades = _filter_trades(results, symbol, date_str, times)
    if not trades:
        raise SystemExit(
            f"No trades found for {symbol} on {date_str}"
            + (" matching provided times" if times else "")
        )

    df = _load_day_df(symbol, date_str, args.interval)
    if df is None or df.empty:
        raise SystemExit(f"No cached OHLCV found for {symbol} {date_str} at {args.interval}/1m")

    # Build signal overlays
    signals = []
    for t in trades:
        signals.append(
            {
                "direction": t.get("direction"),
                "entry": t.get("entry"),
                "stop": t.get("stop"),
                "target": t.get("target"),
                "datetime": t.get("datetime"),  # UTC string; create_chart handles tz display
            }
        )

    title = f"{symbol} trades on {date_str}"
    # Default output path
    if args.out:
        out_path = args.out
    else:
        os.makedirs("logs", exist_ok=True)
        out_path = os.path.join("logs", f"{symbol.lower()}_{date_str.replace('-', '')}_trades.html")

    fig = create_chart(df, signals, output_file=out_path, title=title)
    # create_chart already writes HTML when output_file is provided; ensure file exists
    if not os.path.exists(out_path):
        fig.write_html(out_path)
    print(f"Saved chart to {out_path}")

    # Open in default browser unless suppressed
    if not args.no_open:
        try:
            webbrowser.open(f"file://{os.path.abspath(out_path)}")
            print(f"Opened {out_path} in the default browser.")
        except Exception:
            print("Could not open the file in a browser automatically.")


if __name__ == "__main__":
    main()
