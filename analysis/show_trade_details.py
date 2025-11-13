#!/usr/bin/env python3
import json
import sys
from pathlib import Path

RESULTS = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path("backtest_results/level1_ALL_20250101_20250531_profile_2025-11-12T182642-0800.json")
)
TIMES = set(sys.argv[2:])

data = json.loads(RESULTS.read_text())
out = []
for sym_block in data:
    sym = sym_block.get("symbol")
    for t in sym_block.get("trades", []) or []:
        dt = str(t.get("datetime"))
        if dt in TIMES:
            out.append(
                {
                    "symbol": sym,
                    "datetime": dt,
                    "direction": t.get("direction"),
                    "entry": t.get("entry"),
                    "stop": t.get("stop"),
                    "target": t.get("target"),
                    "exit": t.get("exit"),
                    "pnl": t.get("pnl"),
                    "outcome": t.get("outcome"),
                }
            )
print(json.dumps(out, indent=2))
