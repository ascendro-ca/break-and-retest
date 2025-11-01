# ruff: noqa: I001
"""
Break & Re-Test Live Scanner (CLI)

Thin CLI wrapper that uses the core scanning logic from
`break_and_retest_strategy.scan_ticker` and prints graded results.

Usage examples:
  python break_and_retest_live_scanner.py --tickers AAPL,MSFT --min-grade A
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from break_and_retest_strategy import (
    DEFAULT_RETRY_DELAY,
    DEFAULT_RETRIES,
    LOOKBACK,
    MARKET_OPEN_MINUTES,
    TIMEFRAME,
    TICKERS,
    scan_ticker,
)
from time_utils import get_display_timezone


def _parse_tickers(s: str):
    return [t.strip().upper() for t in s.split(",")] if s else TICKERS


def main():
    p = argparse.ArgumentParser(
        description="5-min Break & Re-Test Live Scanner (multi-timeframe detection)"
    )
    p.add_argument(
        "--tickers",
        default=",".join(TICKERS),
        help="Comma-separated tickers to scan (default: common list)",
    )
    p.add_argument("--timeframe", default=TIMEFRAME)
    p.add_argument("--lookback", default=LOOKBACK)
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    p.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY)
    p.add_argument("--open-minutes", type=int, default=MARKET_OPEN_MINUTES)
    p.add_argument(
        "--min-grade",
        type=str,
        choices=["A", "B", "C"],
        help="Minimum grade filter (A, B, or C). Only show signals with this grade or higher.",
    )
    args = p.parse_args()

    # Resolve display timezone and show it once for clarity
    display_tz, tz_label = get_display_timezone(Path(__file__).parent)

    tickers = _parse_tickers(args.tickers)
    print("\n=== 5-Min Break & Re-Test Live Scanner (CLI) ===\n")
    print(f"Timezone: {tz_label}\n")

    # Define grade hierarchy for filtering
    grade_order = {"A": 3, "B": 2, "C": 1}
    min_grade_value = grade_order.get(args.min_grade, 0) if args.min_grade else 0

    for ticker in tickers:
        try:
            signals, scan_df = scan_ticker(
                ticker,
                timeframe=args.timeframe,
                lookback=args.lookback,
                retries=args.retries,
                retry_delay=args.retry_delay,
                market_open_minutes=args.open_minutes,
            )

            # Apply grade filter if specified
            if args.min_grade and signals:
                filtered_signals = []
                for sig in signals:
                    sig_grade = sig.get("overall_grade", "C")
                    sig_grade_value = grade_order.get(sig_grade, 0)
                    if sig_grade_value >= min_grade_value:
                        filtered_signals.append(sig)

                signals = filtered_signals

                if not signals:
                    print(f"{ticker}: No signals found matching grade {args.min_grade}+ filter.")
                    continue

            # Save outputs similar to the strategy script
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("data", exist_ok=True)
            os.makedirs("logs", exist_ok=True)
            if scan_df is not None and not scan_df.empty:
                scan_path = os.path.join("data", f"{ticker}_scan_{ts}.csv")
                try:
                    scan_df.to_csv(scan_path, index=False)
                    print(f"Saved scan dataframe to {scan_path}")
                except Exception as e:
                    print(f"{ticker}: Failed to save scan dataframe: {e}")
            if signals:
                signals_path = os.path.join("logs", f"{ticker}_signals_{ts}.json")
                try:
                    with open(signals_path, "w") as fh:
                        json.dump(signals, fh, default=str, indent=2)
                    print(f"Saved signals to {signals_path}")
                except Exception as e:
                    print(f"{ticker}: Failed to save signals: {e}")
        except Exception as e:
            print(f"{ticker}: Unexpected error during scan: {e}")


if __name__ == "__main__":
    main()
