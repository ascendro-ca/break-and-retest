#!/usr/bin/env python3
"""
Analyze breakout and retest patterns from backtest results JSON.
This script analyzes trades that stopped out to identify common patterns.
"""

import json
import sys
from collections import Counter
from pathlib import Path


def load_results(filepath):
    """Load backtest results from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def analyze_trade_patterns(results):
    """Analyze patterns in winning vs losing trades."""

    all_trades = []
    for result in results:
        symbol = result["symbol"]
        for trade in result.get("trades", []):
            trade["symbol"] = symbol
            all_trades.append(trade)

    losses = [t for t in all_trades if t["outcome"] == "loss"]
    wins = [t for t in all_trades if t["outcome"] == "win"]

    print(f"\n{'='*80}")
    print(f"TRADE PATTERN ANALYSIS")
    print(f"{'='*80}\n")
    print(f"Total Trades: {len(all_trades)}")
    print(f"Winners: {len(wins)} ({len(wins)/len(all_trades)*100:.1f}%)")
    print(f"Losers: {len(losses)} ({len(losses)/len(all_trades)*100:.1f}%)\n")

    if not losses:
        print("No losing trades to analyze!")
        return

    # Analyze breakout grades
    print("=" * 80)
    print("BREAKOUT GRADE ANALYSIS")
    print("=" * 80)

    loss_breakout_grades = Counter([t.get("breakout_grade", "Unknown") for t in losses])
    win_breakout_grades = Counter([t.get("breakout_grade", "Unknown") for t in wins])

    print("\nLOSSES - Breakout Grade Distribution:")
    print("-" * 80)
    for grade, count in loss_breakout_grades.most_common():
        pct = count / len(losses) * 100
        grade_name = {"✅": "A-grade", "⚠️": "B-grade", "❌": "Reject", "Unknown": "Unknown"}.get(
            grade, grade
        )
        print(f"  {grade} {grade_name:15s}: {count:2d} ({pct:5.1f}%)")

    if wins:
        print("\nWINS - Breakout Grade Distribution:")
        print("-" * 80)
        for grade, count in win_breakout_grades.most_common():
            pct = count / len(wins) * 100
            grade_name = {"✅": "A-grade", "⚠️": "B-grade", "❌": "Reject"}.get(grade, grade)
            print(f"  {grade} {grade_name:15s}: {count:2d} ({pct:5.1f}%)")

    # Analyze breakout volume ratios
    print("\n" + "=" * 80)
    print("BREAKOUT VOLUME RATIO ANALYSIS")
    print("=" * 80)

    # Get volume ratios from signals (backtest has this data)
    loss_vol_ratios = []
    win_vol_ratios = []

    for result in results:
        symbol = result["symbol"]
        for i, sig in enumerate(result.get("signals", [])):
            trade = result["trades"][i] if i < len(result["trades"]) else None
            if trade and "breakout_vol_ratio" in sig:
                vol_ratio = sig["breakout_vol_ratio"]
                if trade["outcome"] == "loss":
                    loss_vol_ratios.append((symbol, vol_ratio))
                else:
                    win_vol_ratios.append((symbol, vol_ratio))

    if loss_vol_ratios:
        print("\nLOSSES - Breakout Volume Ratios:")
        print("-" * 80)
        loss_vols = [v for _, v in loss_vol_ratios]
        avg_loss = sum(loss_vols) / len(loss_vols)
        print(f"  Average: {avg_loss:.2f}x")
        print(f"  Minimum: {min(loss_vols):.2f}x")
        print(f"  Maximum: {max(loss_vols):.2f}x")

        # Categorize
        weak = sum(1 for v in loss_vols if v < 1.0)
        adequate = sum(1 for v in loss_vols if 1.0 <= v < 1.5)
        good = sum(1 for v in loss_vols if 1.5 <= v < 2.0)
        strong = sum(1 for v in loss_vols if v >= 2.0)

        print(f"\n  Distribution:")
        print(f"    < 1.0x (Weak):      {weak:2d} ({weak/len(loss_vols)*100:5.1f}%)")
        print(f"    1.0-1.5x (Adequate): {adequate:2d} ({adequate/len(loss_vols)*100:5.1f}%)")
        print(f"    1.5-2.0x (Good):     {good:2d} ({good/len(loss_vols)*100:5.1f}%)")
        print(f"    >= 2.0x (Strong):    {strong:2d} ({strong/len(loss_vols)*100:5.1f}%)")

    if win_vol_ratios:
        print("\nWINS - Breakout Volume Ratios:")
        print("-" * 80)
        win_vols = [v for _, v in win_vol_ratios]
        avg_win = sum(win_vols) / len(win_vols)
        print(f"  Average: {avg_win:.2f}x")
        print(f"  Minimum: {min(win_vols):.2f}x")
        print(f"  Maximum: {max(win_vols):.2f}x")

        weak = sum(1 for v in win_vols if v < 1.0)
        adequate = sum(1 for v in win_vols if 1.0 <= v < 1.5)
        good = sum(1 for v in win_vols if 1.5 <= v < 2.0)
        strong = sum(1 for v in win_vols if v >= 2.0)

        print(f"\n  Distribution:")
        print(f"    < 1.0x (Weak):       {weak:2d} ({weak/len(win_vols)*100:5.1f}%)")
        print(f"    1.0-1.5x (Adequate): {adequate:2d} ({adequate/len(win_vols)*100:5.1f}%)")
        print(f"    1.5-2.0x (Good):     {good:2d} ({good/len(win_vols)*100:5.1f}%)")
        print(f"    >= 2.0x (Strong):    {strong:2d} ({strong/len(win_vols)*100:5.1f}%)")

    # Analyze breakout body percentage
    print("\n" + "=" * 80)
    print("BREAKOUT BODY PERCENTAGE ANALYSIS")
    print("=" * 80)

    loss_body_pcts = []
    win_body_pcts = []

    for result in results:
        symbol = result["symbol"]
        for i, sig in enumerate(result.get("signals", [])):
            trade = result["trades"][i] if i < len(result["trades"]) else None
            if trade and "breakout_body_pct" in sig:
                body_pct = sig["breakout_body_pct"]
                if trade["outcome"] == "loss":
                    loss_body_pcts.append((symbol, body_pct))
                else:
                    win_body_pcts.append((symbol, body_pct))

    if loss_body_pcts:
        print("\nLOSSES - Breakout Body %:")
        print("-" * 80)
        loss_bodies = [b for _, b in loss_body_pcts]
        avg_loss = sum(loss_bodies) / len(loss_bodies)
        print(f"  Average: {avg_loss*100:.1f}%")
        print(f"  Minimum: {min(loss_bodies)*100:.1f}%")
        print(f"  Maximum: {max(loss_bodies)*100:.1f}%")

        # Categorize
        weak = sum(1 for b in loss_bodies if b < 0.40)
        adequate = sum(1 for b in loss_bodies if 0.40 <= b < 0.65)
        good = sum(1 for b in loss_bodies if 0.65 <= b < 0.80)
        strong = sum(1 for b in loss_bodies if b >= 0.80)

        print(f"\n  Distribution:")
        print(f"    < 40% (Weak):       {weak:2d} ({weak/len(loss_bodies)*100:5.1f}%)")
        print(f"    40-65% (Adequate):  {adequate:2d} ({adequate/len(loss_bodies)*100:5.1f}%)")
        print(f"    65-80% (Good):      {good:2d} ({good/len(loss_bodies)*100:5.1f}%)")
        print(f"    >= 80% (Strong):    {strong:2d} ({strong/len(loss_bodies)*100:5.1f}%)")

    if win_body_pcts:
        print("\nWINS - Breakout Body %:")
        print("-" * 80)
        win_bodies = [b for _, b in win_body_pcts]
        avg_win = sum(win_bodies) / len(win_bodies)
        print(f"  Average: {avg_win*100:.1f}%")
        print(f"  Minimum: {min(win_bodies)*100:.1f}%")
        print(f"  Maximum: {max(win_bodies)*100:.1f}%")

        weak = sum(1 for b in win_bodies if b < 0.40)
        adequate = sum(1 for b in win_bodies if 0.40 <= b < 0.65)
        good = sum(1 for b in win_bodies if 0.65 <= b < 0.80)
        strong = sum(1 for b in win_bodies if b >= 0.80)

        print(f"\n  Distribution:")
        print(f"    < 40% (Weak):       {weak:2d} ({weak/len(win_bodies)*100:5.1f}%)")
        print(f"    40-65% (Adequate):  {adequate:2d} ({adequate/len(win_bodies)*100:5.1f}%)")
        print(f"    65-80% (Good):      {good:2d} ({good/len(win_bodies)*100:5.1f}%)")
        print(f"    >= 80% (Strong):    {strong:2d} ({strong/len(win_bodies)*100:5.1f}%)")

    # Analyze retest grades
    print("\n" + "=" * 80)
    print("RETEST GRADE ANALYSIS")
    print("=" * 80)

    loss_retest_grades = Counter([t.get("retest_grade", "Unknown") for t in losses])
    win_retest_grades = Counter([t.get("retest_grade", "Unknown") for t in wins])

    print("\nLOSSES - Retest Grade Distribution:")
    print("-" * 80)
    for grade, count in loss_retest_grades.most_common():
        pct = count / len(losses) * 100
        grade_name = {"✅": "A-grade", "⚠️": "B-grade", "❌": "Reject"}.get(grade, grade)
        print(f"  {grade} {grade_name:15s}: {count:2d} ({pct:5.1f}%)")

    if wins:
        print("\nWINS - Retest Grade Distribution:")
        print("-" * 80)
        for grade, count in win_retest_grades.most_common():
            pct = count / len(wins) * 100
            grade_name = {"✅": "A-grade", "⚠️": "B-grade", "❌": "Reject"}.get(grade, grade)
            print(f"  {grade} {grade_name:15s}: {count:2d} ({pct:5.1f}%)")

    # Print sample trades
    print("\n" + "=" * 80)
    print("SAMPLE LOSING TRADES (First 10)")
    print("=" * 80)

    for i, loss in enumerate(losses[:10], 1):
        # Find corresponding signal for detailed info
        sig = None
        for result in results:
            if result["symbol"] == loss["symbol"]:
                for s in result["signals"]:
                    if s["datetime"] == loss["datetime"]:
                        sig = s
                        break

        print(f"\n{i}. {loss['symbol']} on {loss['datetime']} ({loss['direction']})")
        print(f"   Breakout Grade: {loss.get('breakout_grade', 'N/A')}")
        print(f"   Retest Grade:   {loss.get('retest_grade', 'N/A')}")
        print(f"   Overall Grade:  {loss.get('overall_grade', 'N/A')}")
        if sig:
            print(f"   Breakout Vol:   {sig.get('breakout_vol_ratio', 0):.2f}x")
            print(f"   Breakout Body:  {sig.get('breakout_body_pct', 0)*100:.1f}%")
            print(f"   Retest Vol:     {sig.get('retest_vol_ratio', 0):.2f}x")
        print(f"   Entry/Stop:     ${loss['entry']} / ${loss['stop']}")
        print(f"   P&L:            ${loss['pnl']:.2f}")


def main():
    # Check for Level 1 results with all grades
    level1_file = Path("backtest_results/analysis_sep_oct_all_grades.json")

    if not level1_file.exists():
        print(f"Error: {level1_file} not found!")
        print(
            "Run: python backtest.py --level 1 --start 2025-09-01 --end 2025-10-31 --output analysis_sep_oct_all_grades.json"
        )
        sys.exit(1)

    print(f"Loading results from {level1_file}...")
    results = load_results(level1_file)

    analyze_trade_patterns(results)


if __name__ == "__main__":
    main()
