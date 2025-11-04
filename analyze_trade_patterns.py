#!/usr/bin/env python3
"""
Analyze breakout and retest patterns in losing vs winning trades.
Runs backtest at Level 2 to get grading data, then analyzes patterns.
"""

import re
import sys
from collections import defaultdict


def run_backtest_level2():
    """Run Level 2 backtest to get grading information."""
    # Use Level 1 to get all trades, but we need to add verbose output
    # For now, let's just run a Python script that does the grading inline
    pass


def run_inline_analysis():
    """Run backtest analysis inline to get all trade data with grades."""

    sys.path.insert(0, "/home/whitestryder/Development/python/break-and-retest")

    from datetime import datetime

    from backtest import Backtest

    bt = Backtest(
        symbols=["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"],
        start_date=datetime(2025, 9, 1),
        end_date=datetime(2025, 10, 31),
        initial_capital=7500,
        leverage=2.0,
        pipeline_level=2,  # Get grading info
        display_tz="America/Los_Angeles",
    )

    return bt


def parse_trade_reports(output):
    """Parse Scarface Rules reports from Level 2 output."""
    trades = []
    lines = output.split("\n")

    current_trade = {}
    in_report = False

    for i, line in enumerate(lines):
        # Start of report
        if "5m Breakout & Retest (Scarface Rules)" in line:
            in_report = True
            current_trade = {}
            # Extract symbol
            match = re.search(r"^(\w+) 5m Breakout", line)
            if match:
                current_trade["symbol"] = match.group(1)
            continue

        if in_report:
            # Extract fields
            if line.startswith("Level:"):
                current_trade["level"] = line.split(":", 1)[1].strip()
            elif line.startswith("Breakout:"):
                current_trade["breakout"] = line.split(":", 1)[1].strip()
            elif line.startswith("Retest:"):
                current_trade["retest"] = line.split(":", 1)[1].strip()
            elif line.startswith("Continuation:"):
                if "post-entry" not in line:
                    current_trade["continuation"] = line.split(":", 1)[1].strip()
            elif line.startswith("R/R:"):
                current_trade["rr"] = line.split(":", 1)[1].strip()
            elif line.startswith("Context:"):
                current_trade["context"] = line.split(":", 1)[1].strip()
            elif line.startswith("Grade:"):
                current_trade["grade"] = line.split(":", 1)[1].strip()
            elif "Continuation (post-entry):" in line:
                current_trade["continuation_post"] = line.split(":", 1)[1].strip()
            elif line.startswith("===") and current_trade:
                in_report = False
                trades.append(current_trade)
                current_trade = {}

    return trades


def parse_outcomes(output):
    """Parse trade outcome table."""
    outcomes = []
    lines = output.split("\n")

    in_table = False
    for line in lines:
        if "| Date (PDT)" in line:
            in_table = True
            continue

        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 11 and parts[1] and parts[1][0].isdigit():
                outcomes.append(
                    {
                        "date": parts[1],
                        "entry_time": parts[2],
                        "exit_time": parts[3],
                        "symbol": parts[5],
                        "direction": parts[6],
                        "entry": parts[7],
                        "stop": parts[8],
                        "target": parts[9],
                        "exit": parts[10],
                        "outcome": parts[11],
                        "pnl": parts[12],
                        "shares": parts[13] if len(parts) > 13 else "",
                    }
                )
        elif in_table and ("Total trades" in line or line.startswith("-")):
            break

    return outcomes


def merge_data(reports, outcomes):
    """Merge reports with outcomes by matching symbol and time."""
    merged = []

    # Create lookup for outcomes by symbol
    for outcome in outcomes:
        # Find matching report
        for report in reports:
            if report["symbol"] == outcome["symbol"]:
                merged.append({**report, **outcome})
                break

    return merged


def analyze_patterns(trades):
    """Analyze patterns in losing vs winning trades."""

    losses = [t for t in trades if t["outcome"] == "loss"]
    wins = [t for t in trades if t["outcome"] == "win"]

    print(f"\n{'='*80}")
    print(f"TRADE PATTERN ANALYSIS: Sep-Oct 2025")
    print(f"{'='*80}\n")
    print(f"Total Trades: {len(trades)}")
    print(f"Winners: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"Losers: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)\n")

    # Analyze breakout patterns
    print("=" * 80)
    print("BREAKOUT PATTERN ANALYSIS")
    print("=" * 80)

    def extract_breakout_pattern(breakout_str):
        """Extract key characteristics from breakout string."""
        patterns = []
        if "Strong candle" in breakout_str or "Solid candle" in breakout_str:
            patterns.append("Strong/Solid")
        if "Adequate" in breakout_str:
            patterns.append("Adequate")
        if "weak" in breakout_str.lower():
            patterns.append("Weak")
        if "✅" in breakout_str:
            patterns.append("✅ A-grade")
        if "⚠️" in breakout_str:
            patterns.append("⚠️ B-grade")
        if "❌" in breakout_str:
            patterns.append("❌ Reject")

        # Extract volume info
        if "high vol" in breakout_str:
            patterns.append("high vol")
        elif "good vol" in breakout_str:
            patterns.append("good vol")
        elif "vol" in breakout_str:
            patterns.append("adequate vol")

        return " | ".join(patterns) if patterns else breakout_str[:40]

    print("\nLOSSES - Breakout Characteristics:")
    print("-" * 80)
    loss_breakouts = defaultdict(int)
    for loss in losses:
        pattern = extract_breakout_pattern(loss.get("breakout", "Unknown"))
        loss_breakouts[pattern] += 1

    for pattern, count in sorted(loss_breakouts.items(), key=lambda x: -x[1]):
        pct = count / len(losses) * 100 if losses else 0
        print(f"  {count:2d} ({pct:5.1f}%)  {pattern}")

    print("\nWINS - Breakout Characteristics:")
    print("-" * 80)
    win_breakouts = defaultdict(int)
    for win in wins:
        pattern = extract_breakout_pattern(win.get("breakout", "Unknown"))
        win_breakouts[pattern] += 1

    for pattern, count in sorted(win_breakouts.items(), key=lambda x: -x[1]):
        pct = count / len(wins) * 100 if wins else 0
        print(f"  {count:2d} ({pct:5.1f}%)  {pattern}")

    # Analyze retest patterns
    print("\n" + "=" * 80)
    print("RETEST PATTERN ANALYSIS")
    print("=" * 80)

    def extract_retest_pattern(retest_str):
        """Extract key characteristics from retest string."""
        patterns = []
        if "A-grade" in retest_str or "clean rejection" in retest_str:
            patterns.append("✅ A-grade clean rejection")
        if "B-grade" in retest_str or "deeper pierce" in retest_str:
            patterns.append("⚠️ B-grade deeper pierce")
        if "C-grade" in retest_str:
            patterns.append("C-grade")
        if "❌" in retest_str:
            patterns.append("❌ Reject")

        # Extract pierce info
        if "pierce 0.0%" in retest_str:
            patterns.append("no pierce")
        elif "pierce" in retest_str:
            match = re.search(r"pierce (\d+\.\d+)%", retest_str)
            if match:
                patterns.append(f"pierce {match.group(1)}%")

        # Volume info
        if "light vol" in retest_str:
            patterns.append("light vol")
        elif "higher vol" in retest_str:
            patterns.append("higher vol")

        return " | ".join(patterns) if patterns else retest_str[:40]

    print("\nLOSSES - Retest Characteristics:")
    print("-" * 80)
    loss_retests = defaultdict(int)
    for loss in losses:
        pattern = extract_retest_pattern(loss.get("retest", "Unknown"))
        loss_retests[pattern] += 1

    for pattern, count in sorted(loss_retests.items(), key=lambda x: -x[1]):
        pct = count / len(losses) * 100 if losses else 0
        print(f"  {count:2d} ({pct:5.1f}%)  {pattern}")

    print("\nWINS - Retest Characteristics:")
    print("-" * 80)
    win_retests = defaultdict(int)
    for win in wins:
        pattern = extract_retest_pattern(win.get("retest", "Unknown"))
        win_retests[pattern] += 1

    for pattern, count in sorted(win_retests.items(), key=lambda x: -x[1]):
        pct = count / len(wins) * 100 if wins else 0
        print(f"  {count:2d} ({pct:5.1f}%)  {pattern}")

    # Sample losing trades
    print("\n" + "=" * 80)
    print("SAMPLE LOSING TRADES (First 10)")
    print("=" * 80)

    for i, loss in enumerate(losses[:10], 1):
        print(
            f"\n{i}. {loss['symbol']} on {loss['date']} {loss['entry_time']} ({loss['direction']})"
        )
        print(f"   Breakout:  {loss.get('breakout', 'N/A')}")
        print(f"   Retest:    {loss.get('retest', 'N/A')}")
        print(f"   Grade:     {loss.get('grade', 'N/A')}")
        print(f"   Context:   {loss.get('context', 'N/A')}")
        print(f"   Entry/Stop: ${loss['entry']} / ${loss['stop']}")


if __name__ == "__main__":
    print("Running Level 2 backtest to get grading data...")
    print("This will take a moment...\n")

    output = run_backtest_level2()

    print("Parsing trade reports...")
    reports = parse_trade_reports(output)
    outcomes = parse_outcomes(output)

    print(f"Found {len(reports)} trade reports and {len(outcomes)} outcomes\n")

    merged = merge_data(reports, outcomes)
    print(f"Merged {len(merged)} complete trades")

    if merged:
        analyze_patterns(merged)
    else:
        print("\nNo trades found with complete data.")
        print("\nShowing raw reports found:")
        for r in reports[:5]:
            print(f"\n{r.get('symbol', 'Unknown')}:")
            print(f"  Breakout: {r.get('breakout', 'N/A')}")
            print(f"  Retest: {r.get('retest', 'N/A')}")
