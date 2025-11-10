#!/usr/bin/env python3
# ruff: noqa: I001
import json
from collections import Counter, defaultdict
from pathlib import Path

# Paths to the JSON result files (adjust if needed)
ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "backtest_results"
L1_FILE = RESULTS_DIR / "level1_ALL_20250101_20251031_points_2025-11-08T083848-0800.json"
L2_FILE = RESULTS_DIR / "level2_ALL_20250101_20251031_points_2025-11-08T084154-0800.json"


def load_json(path: Path):
    with open(path, "r") as f:
        return json.load(f)


def make_sig_key(symbol: str, sig: dict):
    """Canonical key to align Level 1 and 2 signals for the same setup.
    We use (symbol, direction, breakout_time_5m, retest_candle.Datetime)
    which should be stable across Level 1 and 2 for the same candidate.
    """
    direction = sig.get("direction")
    breakout_t = sig.get("breakout_time_5m")
    retest_dt = None
    rc = sig.get("retest_candle") or {}
    if isinstance(rc, dict):
        retest_dt = rc.get("Datetime")
    return (symbol, direction, breakout_t, retest_dt)


def index_signals(results: list):
    """Return a dict: key -> signal for quick lookup."""
    idx = {}
    for sym_obj in results:
        symbol = sym_obj.get("symbol")
        for sig in sym_obj.get("signals", []) or []:
            key = make_sig_key(symbol, sig)
            idx[key] = sig
    return idx


def index_trades(results: list):
    """Return a mapping from (symbol, trade_datetime_str) -> trade dict and also key->trade."""
    by_dt = {}
    # Also map from signal alignment key to trade (via matching signal datetime)
    by_key = {}
    for sym_obj in results:
        symbol = sym_obj.get("symbol")
        # Build a map from signal datetime -> signal for this symbol
        sig_by_dt = {}
        for sig in sym_obj.get("signals", []) or []:
            sdt = sig.get("datetime")
            if sdt is not None:
                sig_by_dt[sdt] = sig
        # Now traverse trades and associate to signals
        for tr in sym_obj.get("trades", []) or []:
            dt = tr.get("datetime")
            if dt is None:
                continue
            by_dt[(symbol, dt)] = tr
            # Find its signal to compute the alignment key
            sig = sig_by_dt.get(dt)
            if sig is not None:
                key = make_sig_key(symbol, sig)
                by_key[key] = tr
    return by_dt, by_key


def main():
    l1 = load_json(L1_FILE)
    l2 = load_json(L2_FILE)

    # Build indexes
    l2_sigs = index_signals(l2)  # Note: these are only Level 2-accepted signals

    l1_trades_by_dt, l1_trades_by_key = index_trades(l1)
    l2_trades_by_dt, l2_trades_by_key = index_trades(l2)

    # Identify Level 1 winners
    l1_winner_keys = []
    l1_total_winners = 0
    for sym_obj in l1:
        symbol = sym_obj.get("symbol")
        for tr in sym_obj.get("trades", []) or []:
            if tr.get("outcome") == "win":
                l1_total_winners += 1
                # Find the corresponding signal key
                dt = tr.get("datetime")
                sig = None
                for s in sym_obj.get("signals", []) or []:
                    if s.get("datetime") == dt:
                        sig = s
                        break
                if sig is None:
                    # Fallback: skip if we can't locate the signal; shouldn't happen
                    continue
                key = make_sig_key(symbol, sig)
                l1_winner_keys.append((key, symbol, tr, sig))

    # Classification counters
    classes = Counter()
    examples = defaultdict(list)

    for key, symbol, tr, sig in l1_winner_keys:
        # If Level 2 accepted this setup, it will appear in l2_sigs
        l2_sig = l2_sigs.get(key)
        if l2_sig is not None:
            # Check if L2 actually traded it
            l2_tr = l2_trades_by_key.get(key)
            if l2_tr is None:
                classes["accepted_no_trade"] += 1
                if len(examples["accepted_no_trade"]) < 5:
                    examples["accepted_no_trade"].append(
                        {
                            "symbol": symbol,
                            "direction": sig.get("direction"),
                            "breakout_time_5m": sig.get("breakout_time_5m"),
                            "retest_time": sig.get("retest_candle", {}).get("Datetime"),
                            "l1_entry": tr.get("entry"),
                            "l1_dt": tr.get("datetime"),
                        }
                    )
            else:
                if l2_tr.get("outcome") == "win":
                    classes["captured_win"] += 1
                else:
                    classes["captured_loss"] += 1
                    if len(examples["captured_loss"]) < 5:
                        examples["captured_loss"].append(
                            {
                                "symbol": symbol,
                                "direction": sig.get("direction"),
                                "breakout_time_5m": sig.get("breakout_time_5m"),
                                "retest_time": sig.get("retest_candle", {}).get("Datetime"),
                                "l1_entry": tr.get("entry"),
                                "l2_entry": l2_tr.get("entry"),
                                "l1_dt": tr.get("datetime"),
                                "l2_dt": l2_tr.get("datetime"),
                            }
                        )
        else:
            # Absent from L2 signals: rejected. Attribute to gate vs ignition.
            # Use L1 grades as proxy for L2 gate outcome.
            grades = sig.get("component_grades", {})
            breakout_ok = grades.get("breakout") != "❌"
            rr_ok = grades.get("rr") != "❌"
            if breakout_ok and rr_ok:
                classes["missing_ignition"] += 1
                if len(examples["missing_ignition"]) < 5:
                    examples["missing_ignition"].append(
                        {
                            "symbol": symbol,
                            "direction": sig.get("direction"),
                            "breakout_time_5m": sig.get("breakout_time_5m"),
                            "retest_time": sig.get("retest_candle", {}).get("Datetime"),
                            "l1_entry": tr.get("entry"),
                            "l1_dt": tr.get("datetime"),
                            "grades": grades,
                        }
                    )
            else:
                classes["rejected_by_gate"] += 1
                if len(examples["rejected_by_gate"]) < 5:
                    examples["rejected_by_gate"].append(
                        {
                            "symbol": symbol,
                            "direction": sig.get("direction"),
                            "breakout_time_5m": sig.get("breakout_time_5m"),
                            "retest_time": sig.get("retest_candle", {}).get("Datetime"),
                            "grades": grades,
                        }
                    )

    total = l1_total_winners

    def pct(x):
        return (100.0 * x / total) if total else 0.0

    print("Level 1 winners (3R) total:", total)
    print("Breakdown (as % of L1 winners):")
    print(
        f"  - Captured by Level 2 and won: {classes['captured_win']}"
        f" ({pct(classes['captured_win']):.1f}%)"
    )
    print(
        f"  - Captured by Level 2 but lost: {classes['captured_loss']}"
        f" ({pct(classes['captured_loss']):.1f}%)"
    )
    print(
        f"  - Accepted by Level 2 but no trade: {classes['accepted_no_trade']}"
        f" ({pct(classes['accepted_no_trade']):.1f}%)"
    )
    missed = classes["rejected_by_gate"] + classes["missing_ignition"]
    print(f"  - Missed by Level 2 total: {missed} ({pct(missed):.1f}%)")
    print(
        f"      • Rejected by breakout/RR gate: {classes['rejected_by_gate']}"
        f" ({pct(classes['rejected_by_gate']):.1f}%)"
    )
    print(
        f"      • No ignition detected (Level 2 rules): {classes['missing_ignition']}"
        f" ({pct(classes['missing_ignition']):.1f}%)"
    )

    # Show a few examples for each category
    for cat in ["captured_loss", "missing_ignition", "rejected_by_gate", "accepted_no_trade"]:
        if examples[cat]:
            print(f"\nExamples: {cat}")
            for ex in examples[cat]:
                print(json.dumps(ex, indent=2))


if __name__ == "__main__":
    main()
