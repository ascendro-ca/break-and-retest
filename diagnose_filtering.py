#!/usr/bin/env python3
"""
Diagnostic script to analyze where candidates are filtered out in the pipeline.

Shows the filtering funnel from Level 0 → Level 1 → Level 2:
- Level 0: All break & retest candidates
- Level 1: Candidates with entry/stop/target (no ignition required)
- Level 2: Only setups with ignition and C+ grades

Usage:
    python diagnose_filtering.py --start 2025-05-01 --end 2025-10-31
    python diagnose_filtering.py --symbols AAPL MSFT --start 2025-05-01 --end 2025-05-31
"""

import argparse
import json
from pathlib import Path

from backtest import BacktestEngine, DataCache
from config_utils import load_config
from time_utils import get_display_timezone


def run_diagnostic(symbols, start_date, end_date, cache_dir="cache"):
    """Run diagnostic backtest across all three levels"""

    display_tz, tz_label = get_display_timezone(Path(__file__).parent)

    print(f"\n{'='*80}")
    print(f"DIAGNOSTIC FILTERING ANALYSIS")
    print(f"{'='*80}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Timezone: {tz_label}")
    print(f"{'='*80}\n")

    cache = DataCache(cache_dir)

    results_by_level = {}

    # Run at each level
    for level in [0, 1, 2]:
        print(f"\n{'='*80}")
        print(f"RUNNING LEVEL {level} BACKTEST")
        print(f"{'='*80}\n")

        engine = BacktestEngine(
            initial_capital=7500,
            leverage=2.0,
            display_tzinfo=display_tz,
            tz_label=tz_label,
            pipeline_level=level,
            no_trades=(level == 0),  # Level 0 is candidates only
            grading_system="points",
        )

        level_results = []

        for symbol in symbols:
            print(f"\nProcessing {symbol}...")

            # Load 5m data
            df_5m = cache.download_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval="5m",
            )

            if df_5m.empty:
                print(f"  No 5m data for {symbol}")
                continue

            # Run backtest
            result = engine.run_backtest(symbol, df_5m, cache_dir=cache_dir)
            level_results.append(result)

        results_by_level[level] = level_results

    # Analyze filtering funnel
    print(f"\n\n{'='*80}")
    print(f"FILTERING FUNNEL ANALYSIS")
    print(f"{'='*80}\n")

    for symbol in symbols:
        print(f"\n{symbol}:")
        print(f"{'-'*60}")

        # Get results for this symbol at each level
        l0_result = next((r for r in results_by_level[0] if r["symbol"] == symbol), None)
        l1_result = next((r for r in results_by_level[1] if r["symbol"] == symbol), None)
        l2_result = next((r for r in results_by_level[2] if r["symbol"] == symbol), None)

        if not l0_result:
            print("  No data available")
            continue

        # Level 0: Candidates
        l0_candidates = l0_result.get("candidate_count", 0)
        print(f"  Level 0 (Candidates):     {l0_candidates:3d} break & retest setups detected")

        # Level 1: Base trades (no ignition, no grading)
        if l1_result:
            l1_signals = len(l1_result.get("signals", []))
            l1_trades = l1_result.get("total_trades", 0)
            l1_filtered = l0_candidates - l1_signals
            print(f"  Level 1 (Base Trades):    {l1_signals:3d} candidates → {l1_trades} trades")
            if l1_filtered > 0:
                print(f"    ↳ Filtered out: {l1_filtered} (entry timing/other constraints)")

        # Level 2: Enhanced with ignition and grading
        if l2_result:
            l2_signals = len(l2_result.get("signals", []))
            l2_trades = l2_result.get("total_trades", 0)

            # Show rejections if available
            rejections = l2_result.get("level2_rejections", {})
            breakout_fail = rejections.get("breakout_fail", 0)
            retest_fail = rejections.get("retest_fail", 0)
            ignition_fail = rejections.get(
                "ignition_fail", 0
            )  # Note: this tracks continuation grade fails

            print(f"  Level 2 (Quality Filter): {l2_signals:3d} candidates → {l2_trades} trades")

            # Calculate how many were lost between L1 and L2
            if l1_result:
                l1_to_l2_loss = l1_signals - (
                    l2_signals + breakout_fail + retest_fail + ignition_fail
                )
                if l1_to_l2_loss > 0:
                    print(f"    ↳ No ignition found: {l1_to_l2_loss}")

            if breakout_fail + retest_fail + ignition_fail > 0:
                print(f"    ↳ Grading failures:")
                if breakout_fail > 0:
                    print(f"        • Breakout grade ❌: {breakout_fail}")
                if retest_fail > 0:
                    print(f"        • Retest grade ❌: {retest_fail}")
                if ignition_fail > 0:
                    print(f"        • Ignition grade ❌: {ignition_fail}")

    # Overall summary
    print(f"\n\n{'='*80}")
    print(f"OVERALL SUMMARY")
    print(f"{'='*80}\n")

    l0_total = sum(r.get("candidate_count", 0) for r in results_by_level[0])
    l1_total_signals = sum(len(r.get("signals", [])) for r in results_by_level[1])
    l1_total_trades = sum(r.get("total_trades", 0) for r in results_by_level[1])
    l2_total_signals = sum(len(r.get("signals", [])) for r in results_by_level[2])
    l2_total_trades = sum(r.get("total_trades", 0) for r in results_by_level[2])

    print(f"Level 0 Candidates:     {l0_total:4d}")
    print(
        f"Level 1 Signals:        {l1_total_signals:4d} "
        f"({l1_total_signals/l0_total*100:.1f}% of L0)"
    )
    print(f"Level 1 Trades:         {l1_total_trades:4d}")
    print(
        f"Level 2 Signals:        {l2_total_signals:4d} "
        f"({l2_total_signals/l0_total*100:.1f}% of L0)"
    )
    print(
        f"Level 2 Trades:         {l2_total_trades:4d} ({l2_total_trades/l0_total*100:.1f}% of L0)"
    )

    print(f"\nFiltering Impact:")
    l0_l1_filtered = l0_total - l1_total_signals
    l0_l1_pct = (l0_total - l1_total_signals) / l0_total * 100
    print(f"  L0 → L1: {l0_l1_filtered:4d} filtered ({l0_l1_pct:.1f}%)")

    l1_l2_filtered = l1_total_signals - l2_total_signals
    l1_l2_pct = (l1_total_signals - l2_total_signals) / l1_total_signals * 100
    print(f"  L1 → L2: {l1_l2_filtered:4d} filtered ({l1_l2_pct:.1f}%)")

    l0_l2_filtered = l0_total - l2_total_signals
    l0_l2_pct = (l0_total - l2_total_signals) / l0_total * 100
    print(f"  L0 → L2: {l0_l2_filtered:4d} filtered ({l0_l2_pct:.1f}%)")

    # Calculate L2 rejection breakdown
    total_breakout_fail = sum(
        r.get("level2_rejections", {}).get("breakout_fail", 0) for r in results_by_level[2]
    )
    total_retest_fail = sum(
        r.get("level2_rejections", {}).get("retest_fail", 0) for r in results_by_level[2]
    )
    total_ignition_fail = sum(
        r.get("level2_rejections", {}).get("ignition_fail", 0) for r in results_by_level[2]
    )

    if total_breakout_fail + total_retest_fail + total_ignition_fail > 0:
        print(f"\nLevel 2 Grade Failures:")
        if total_breakout_fail > 0:
            print(f"  Breakout ❌:  {total_breakout_fail:4d}")
        if total_retest_fail > 0:
            print(f"  Retest ❌:    {total_retest_fail:4d}")
        if total_ignition_fail > 0:
            print(f"  Ignition ❌:  {total_ignition_fail:4d}")

    print(f"\n{'='*80}\n")

    return results_by_level


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose where candidates are filtered in the pipeline"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Stock symbols to analyze (default: all from config.json)",
    )
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory")
    parser.add_argument(
        "--output",
        help="Optional: Save detailed results to JSON file",
    )

    args = parser.parse_args()

    CONFIG = load_config()
    symbols = args.symbols if args.symbols else CONFIG["tickers"]

    results = run_diagnostic(
        symbols=symbols,
        start_date=args.start,
        end_date=args.end,
        cache_dir=args.cache_dir,
    )

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Detailed results saved to {output_path}")


if __name__ == "__main__":
    main()
