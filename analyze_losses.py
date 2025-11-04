#!/usr/bin/env python3
"""Analyze losing trades to find patterns in breakout characteristics."""

import re
import subprocess
import sys


def run_backtest():
    """Run backtest and capture output."""
    cmd = [
        sys.executable,
        "backtest.py",
        "--level",
        "1",
        "--start",
        "2025-09-01",
        "--end",
        "2025-10-31",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout + result.stderr


def parse_trades(output):
    """Parse trade details from backtest output."""
    trades = []
    lines = output.split("\n")

    current_trade = {}
    in_trade_section = False

    for i, line in enumerate(lines):
        # Detect start of trade section
        if "5m Breakout & Retest" in line:
            in_trade_section = True
            current_trade = {}
            # Extract symbol from the line
            match = re.search(r"^(\w+) 5m Breakout", line)
            if match:
                current_trade["symbol"] = match.group(1)
            continue

        if in_trade_section:
            # Extract breakout info
            if line.startswith("Breakout:"):
                current_trade["breakout"] = line.replace("Breakout:", "").strip()

            # Extract retest info
            elif line.startswith("Retest:"):
                current_trade["retest"] = line.replace("Retest:", "").strip()

            # Extract continuation info
            elif line.startswith("Continuation:"):
                current_trade["continuation"] = line.replace("Continuation:", "").strip()

            # Extract grade
            elif line.startswith("Grade:"):
                current_trade["grade"] = line.replace("Grade:", "").strip()

            # Extract context
            elif line.startswith("Context:"):
                current_trade["context"] = line.replace("Context:", "").strip()

            # Extract continuation post-entry
            elif "Continuation (post-entry):" in line:
                current_trade["continuation_post"] = line.replace(
                    "Continuation (post-entry):", ""
                ).strip()

            # End of trade section
            elif line.startswith("==="):
                in_trade_section = False
                if current_trade:
                    trades.append(current_trade)
                current_trade = {}

    return trades


def parse_trade_outcomes(output):
    """Parse trade outcomes from summary table."""
    outcomes = []
    lines = output.split("\n")

    in_table = False
    for line in lines:
        if "| Date (PDT)" in line:
            in_table = True
            continue
        if in_table:
            if line.startswith("|") and "|" in line[1:]:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) > 11 and parts[1] and parts[1][0].isdigit():
                    outcome = {
                        "date": parts[1],
                        "entry_time": parts[2],
                        "symbol": parts[5],
                        "direction": parts[6],
                        "entry": parts[7],
                        "stop": parts[8],
                        "result": parts[10],
                    }
                    outcomes.append(outcome)
            elif line.startswith("-") or "Total trades" in line:
                break

    return outcomes


def merge_trade_data(trades, outcomes):
    """Merge trade details with outcomes."""
    merged = []

    for outcome in outcomes:
        # Find matching trade by symbol and approximate time
        for trade in trades:
            if trade.get("symbol") == outcome["symbol"]:
                merged_trade = {**trade, **outcome}
                merged.append(merged_trade)
                break

    return merged


def analyze_patterns(trades):
    """Analyze patterns in losing trades."""
    losses = [t for t in trades if t["result"] == "loss"]
    wins = [t for t in trades if t["result"] == "win"]

    print(f"\n{'='*80}")
    print(f"ANALYSIS: {len(losses)} LOSSES vs {len(wins)} WINS")
    print(f"{'='*80}\n")

    # Analyze breakout patterns
    print("BREAKOUT PATTERNS IN LOSSES:")
    print("-" * 80)

    breakout_patterns = {}
    for loss in losses:
        breakout = loss.get("breakout", "Unknown")

        # Extract key indicators
        if "Adequate" in breakout or "⚠️" in breakout:
            pattern = "Adequate/Warning ⚠️"
        elif "A-grade" in breakout or "✅" in breakout:
            pattern = "A-grade ✅"
        elif "weak" in breakout.lower() or "❌" in breakout:
            pattern = "Weak/Reject ❌"
        else:
            pattern = breakout[:50]

        breakout_patterns[pattern] = breakout_patterns.get(pattern, 0) + 1

    for pattern, count in sorted(breakout_patterns.items(), key=lambda x: -x[1]):
        pct = count / len(losses) * 100
        print(f"  {count:2d} ({pct:5.1f}%) - {pattern}")

    print("\nBREAKOUT PATTERNS IN WINS:")
    print("-" * 80)

    breakout_patterns_wins = {}
    for win in wins:
        breakout = win.get("breakout", "Unknown")

        if "Adequate" in breakout or "⚠️" in breakout:
            pattern = "Adequate/Warning ⚠️"
        elif "A-grade" in breakout or "✅" in breakout:
            pattern = "A-grade ✅"
        elif "weak" in breakout.lower() or "❌" in breakout:
            pattern = "Weak/Reject ❌"
        else:
            pattern = breakout[:50]

        breakout_patterns_wins[pattern] = breakout_patterns_wins.get(pattern, 0) + 1

    for pattern, count in sorted(breakout_patterns_wins.items(), key=lambda x: -x[1]):
        pct = count / len(wins) * 100
        print(f"  {count:2d} ({pct:5.1f}%) - {pattern}")

    # Analyze retest patterns
    print("\n\nRETEST PATTERNS IN LOSSES:")
    print("-" * 80)

    retest_patterns = {}
    for loss in losses:
        retest = loss.get("retest", "Unknown")

        if "A-grade" in retest or "clean rejection" in retest:
            pattern = "A-grade: clean rejection ✅"
        elif "B-grade" in retest or "deeper pierce" in retest:
            pattern = "B-grade: deeper pierce ⚠️"
        elif "C-grade" in retest or "weak" in retest.lower():
            pattern = "C-grade: weak structure"
        elif "❌" in retest or "reject" in retest.lower():
            pattern = "Reject ❌"
        else:
            pattern = retest[:50]

        retest_patterns[pattern] = retest_patterns.get(pattern, 0) + 1

    for pattern, count in sorted(retest_patterns.items(), key=lambda x: -x[1]):
        pct = count / len(losses) * 100
        print(f"  {count:2d} ({pct:5.1f}%) - {pattern}")

    print("\nRETEST PATTERNS IN WINS:")
    print("-" * 80)

    retest_patterns_wins = {}
    for win in wins:
        retest = win.get("retest", "Unknown")

        if "A-grade" in retest or "clean rejection" in retest:
            pattern = "A-grade: clean rejection ✅"
        elif "B-grade" in retest or "deeper pierce" in retest:
            pattern = "B-grade: deeper pierce ⚠️"
        elif "C-grade" in retest or "weak" in retest.lower():
            pattern = "C-grade: weak structure"
        elif "❌" in retest or "reject" in retest.lower():
            pattern = "Reject ❌"
        else:
            pattern = retest[:50]

        retest_patterns_wins[pattern] = retest_patterns_wins.get(pattern, 0) + 1

    for pattern, count in sorted(retest_patterns_wins.items(), key=lambda x: -x[1]):
        pct = count / len(wins) * 100
        print(f"  {count:2d} ({pct:5.1f}%) - {pattern}")

    # Sample losses with details
    print("\n\nSAMPLE LOSING TRADES (first 10):")
    print("=" * 80)
    for i, loss in enumerate(losses[:10], 1):
        print(f"\n{i}. {loss['symbol']} on {loss['date']} at {loss['entry_time']}")
        print(f"   Breakout: {loss.get('breakout', 'N/A')}")
        print(f"   Retest:   {loss.get('retest', 'N/A')}")
        print(f"   Grade:    {loss.get('grade', 'N/A')}")
        print(f"   Context:  {loss.get('context', 'N/A')}")


if __name__ == "__main__":
    print("Running backtest...")
    output = run_backtest()

    print("Parsing trades...")
    trades = parse_trades(output)
    outcomes = parse_trade_outcomes(output)

    print(f"Found {len(trades)} trade details and {len(outcomes)} outcomes")

    merged = merge_trade_data(trades, outcomes)
    print(f"Merged {len(merged)} trades")

    analyze_patterns(merged)
