import re
from collections import defaultdict
from pathlib import Path

L1_PATH = Path(
    "backtest_results/level1_ALL_20250101_20251031_points_2025-11-09T095322-0800_summary.md"
)
L2_PATH = Path(
    "backtest_results/level2_ALL_20250101_20251031_points_2025-11-09T101308-0800_summary.md"
)

ROW_RE = re.compile(r"^\|\s*20\d{2}-\d{2}-\d{2}.*")
# Columns expected (Markdown table):
# Date | Entry | Exit | minutes | Symbol | Dir | Entry | Stop | Target | Exit |
# Outcome | Risk | R/R | P&L | Shares
# We'll split on '|' and strip each part.


def parse_file(path):
    trades = []
    with path.open() as f:
        for line in f:
            if not line.startswith("| 20"):  # quicker filter
                continue
            parts = [p.strip() for p in line.strip().split("|")[1:-1]]  # drop leading/trailing pipe
            if len(parts) < 15:
                continue
            (
                date,
                entry_time,
                exit_time,
                minutes,
                symbol,
                direction,
                entry_px,
                stop_px,
                target_px,
                exit_px,
                outcome,
                risk,
                rr,
                pnl,
                shares,
            ) = parts[:15]
            try:
                pnl_f = float(pnl.replace("$", ""))
            except ValueError:
                # some losses show like -37.45, wins positive
                try:
                    pnl_f = float(pnl)
                except ValueError:
                    continue
            try:
                risk_f = float(risk)
            except ValueError:
                risk_f = None
            trades.append(
                {
                    "date": date,
                    "entry_time": entry_time,
                    "symbol": symbol,
                    "direction": direction,
                    "outcome": outcome,
                    "pnl": pnl_f,
                    "risk": risk_f,
                }
            )
    return trades


l1_trades = parse_file(L1_PATH)
l2_trades = parse_file(L2_PATH)


def aggregate(trades):
    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = total - wins
    total_pnl = sum(t["pnl"] for t in trades)
    win_pnls = [t["pnl"] for t in trades if t["outcome"] == "win"]
    loss_pnls = [t["pnl"] for t in trades if t["outcome"] == "loss"]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    win_rate = wins / total if total else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss if total else 0.0
    per_symbol = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for t in trades:
        ps = per_symbol[t["symbol"]]
        ps["trades"] += 1
        if t["outcome"] == "win":
            ps["wins"] += 1
        ps["pnl"] += t["pnl"]
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "per_symbol": per_symbol,
    }


l1_stats = aggregate(l1_trades)
l2_stats = aggregate(l2_trades)

# Build comparison markdown snippet
md = []
md.append("## Updated Aggregate Funnel (Nov 9 run)")
md.append("| Metric | Level 1 | Level 2 | Delta |")
md.append("|---|---:|---:|---:|")
md.append(
    "| Trades | {} | {} | {} |".format(
        l1_stats["total"], l2_stats["total"], l2_stats["total"] - l1_stats["total"]
    )
)
md.append(
    "| Winners | {} | {} | {} |".format(
        l1_stats["wins"], l2_stats["wins"], l2_stats["wins"] - l1_stats["wins"]
    )
)
md.append(
    "| Win Rate | {:.2f}% | {:.2f}% | {:.2f} pp |".format(
        l1_stats["win_rate"] * 100,
        l2_stats["win_rate"] * 100,
        (l2_stats["win_rate"] - l1_stats["win_rate"]) * 100,
    )
)
md.append(
    "| Total P&L | ${:.2f} | ${:.2f} | ${:.2f} |".format(
        l1_stats["total_pnl"],
        l2_stats["total_pnl"],
        l2_stats["total_pnl"] - l1_stats["total_pnl"],
    )
)
md.append(
    "| Avg Win | ${:.2f} | ${:.2f} | ${:.2f} |".format(
        l1_stats["avg_win"],
        l2_stats["avg_win"],
        l2_stats["avg_win"] - l1_stats["avg_win"],
    )
)
md.append(
    "| Avg Loss | ${:.2f} | ${:.2f} | ${:.2f} |".format(
        l1_stats["avg_loss"],
        l2_stats["avg_loss"],
        l2_stats["avg_loss"] - l1_stats["avg_loss"],
    )
)
md.append(
    "| Expectancy | ${:.2f} | ${:.2f} | ${:.2f} |".format(
        l1_stats["expectancy"],
        l2_stats["expectancy"],
        l2_stats["expectancy"] - l1_stats["expectancy"],
    )
)

# Per-symbol efficiency (retention and EV per trade)
md.append("\n## Per-Symbol Efficiency")
md.append(
    "| Symbol | L1 Trades | L2 Trades | Retention % | L1 Win Rate % | L2 Win Rate % | "
    "L1 EV | L2 EV | L2-L1 EV Δ |"
)
md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for symbol in sorted(l1_stats["per_symbol"]):
    l1s = l1_stats["per_symbol"][symbol]
    l2s = l2_stats["per_symbol"].get(symbol, {"trades": 0, "wins": 0, "pnl": 0.0})
    l1_wr = (l1s["wins"] / l1s["trades"] * 100) if l1s["trades"] else 0.0
    l2_wr = (l2s["wins"] / l2s["trades"] * 100) if l2s["trades"] else 0.0
    l1_ev = l1s["pnl"] / l1s["trades"] if l1s["trades"] else 0.0
    l2_ev = l2s["pnl"] / l2s["trades"] if l2s["trades"] else 0.0
    retention = (l2s["trades"] / l1s["trades"] * 100) if l1s["trades"] else 0.0
    md.append(
        "| {} | {} | {} | {:.1f}% | {:.1f}% | {:.2f} | {:.2f} | {:.2f} | {:.2f} |".format(
            symbol,
            l1s["trades"],
            l2s["trades"],
            retention,
            l1_wr,
            l2_wr,
            l1_ev,
            l2_ev,
            l2_ev - l1_ev,
        )
    )


# Early window compliance check (entries must be <= 08:00:00 PST)
def is_within_first_90(entry_time: str) -> bool:
    # Format HH:MM:SS
    try:
        hh, mm, ss = map(int, entry_time.split(":"))
    except Exception:
        return True
    # First 90 minutes from 06:30 to 08:00 inclusive. Entries are 06:xx or 07:xx or exactly 08:00:00
    if hh < 6 or hh > 8:
        return False
    if hh == 8:
        return mm == 0 and ss == 0
    return True


l2_non_compliant = [t for t in l2_trades if not is_within_first_90(t["entry_time"])]
md.append("\n## Early Window Compliance")
if not l2_non_compliant:
    md.append("All Level 2 entries are within the first 90 minutes (<= 08:00:00 PST).")
else:
    md.append(f"{len(l2_non_compliant)} Level 2 entries appear after 08:00:00 PST (first 3 shown):")
    for t in l2_non_compliant[:3]:
        md.append(f"- {t['date']} {t['entry_time']} {t['symbol']}")

OUT_PATH = Path("backtest_results/updated_funnel_metrics.md")
OUT_PATH.write_text("\n".join(md))
print("Wrote", OUT_PATH, "with updated metrics.")
