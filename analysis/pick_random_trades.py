#!/usr/bin/env python3
import json
import random
from pathlib import Path

import pandas as pd

RESULTS_PATH = Path(
    "backtest_results/level1_ALL_20250101_20250531_profile_2025-11-12T182642-0800.json"
)


def load_trades(results_path: Path):
    data = json.loads(results_path.read_text())
    trades = []
    for sym_block in data:
        symbol = sym_block.get("symbol")
        for t in sym_block.get("trades", []) or []:
            # normalize datetime to string and get date (keeping original tz)
            dt_str = str(t.get("datetime"))
            try:
                ts = pd.to_datetime(dt_str)
            except Exception:
                continue
            date_str = ts.strftime("%Y-%m-%d")
            trades.append(
                {
                    "symbol": symbol,
                    "date": date_str,
                    "datetime": dt_str,
                    "direction": t.get("direction"),
                    "pnl": t.get("pnl"),
                    "outcome": t.get("outcome"),
                }
            )
    return trades


def pick_examples(trades, outcome: str, n: int):
    pool = [t for t in trades if (t.get("outcome") == outcome)]
    random.shuffle(pool)
    return pool[:n]


def main():
    trades = load_trades(RESULTS_PATH)
    wins = pick_examples(trades, "win", 2)
    losses = pick_examples(trades, "loss", 2)
    print(json.dumps({"wins": wins, "losses": losses}, indent=2))


if __name__ == "__main__":
    main()
