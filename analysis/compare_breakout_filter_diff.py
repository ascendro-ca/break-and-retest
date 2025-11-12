#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root on path for direct execution
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from grading.breakout_grader import score_breakout_details  # noqa: E402


def load_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        return json.load(f)


def key_from_trade(tr: Dict[str, Any]) -> Tuple[str, str]:
    return (str(tr.get("datetime")), str(tr.get("direction")))


def index_signals_by_key(res: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for s in res.get("signals", []) or []:
        k = (str(s.get("datetime")), str(s.get("direction")))
        out[k] = s
    return out


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Compare Test1 (breakout filters disabled -> max breakout points) vs "
            "Test2 (filters enabled) and recalculate realistic breakout pattern/volume "
            "points for filtered trades to attribute gating reasons."
        )
    )
    ap.add_argument("test1", type=Path, help="Path to Test1 JSON (filters disabled)")
    ap.add_argument("test2", type=Path, help="Path to Test2 JSON (filters enabled)")
    ap.add_argument("--symbol", default=None, help="Symbol to filter (default: first in file)")
    ap.add_argument(
        "--output", type=Path, default=None, help="Optional path to write Markdown diff"
    )
    ap.add_argument(
        "--grade-threshold",
        type=float,
        default=86.0,
        help="Total points threshold for grade gating (default 86 for A)",
    )
    args = ap.parse_args()

    r1 = load_results(args.test1)
    r2 = load_results(args.test2)

    # Pick symbol
    sym = args.symbol or (r1[0]["symbol"] if r1 else None)
    if sym is None:
        raise SystemExit("No symbol found in Test1 file")

    r1_sym = next((r for r in r1 if r.get("symbol") == sym), None)
    r2_sym = next((r for r in r2 if r.get("symbol") == sym), None)
    if r1_sym is None or r2_sym is None:
        raise SystemExit(f"Symbol {sym} not found in both files")

    t1 = r1_sym.get("trades", []) or []
    t2 = r2_sym.get("trades", []) or []

    t1_keys = {key_from_trade(tr) for tr in t1}
    t2_keys = {key_from_trade(tr) for tr in t2}

    filtered_keys = sorted(list(t1_keys - t2_keys))

    s_index = index_signals_by_key(r1_sym)

    rows: List[Dict[str, Any]] = []
    for k in filtered_keys:
        sig = s_index.get(k, {})
        breakout_candle = sig.get("breakout_candle", {}) or {}
        vol_ratio = float(sig.get("breakout_vol_ratio", 0.0) or 0.0)
        direction = sig.get("direction")
        # Recalculate realistic breakout scoring with filters enabled (current module state)
        details = score_breakout_details(breakout_candle, vol_ratio, {}, direction=direction)
        new_pattern = int(details.get("pattern_pts", 0))
        new_volume = int(details.get("volume_pts", 0))
        # Retain other component points from original (they are unaffected by breakout filters)
        pts = sig.get("points", {}) or {}
        retest_pts = int(pts.get("retest", 0))
        ignition_pts = int(pts.get("ignition", 0))
        trend_pts = int(pts.get("trend", 0))
        new_total = new_pattern + new_volume + retest_pts + ignition_pts + trend_pts
        reason_parts = []
        if new_pattern < 20:
            reason_parts.append("pattern")
        if new_volume < 10:
            reason_parts.append("volume")
        if new_total < args.grade_threshold:
            reason_parts.append("total<threshold")
        rows.append(
            {
                "datetime": k[0],
                "direction": k[1],
                "breakout_time_5m": sig.get("breakout_time_5m"),
                "body_pct": sig.get("breakout_body_pct"),
                "vol_ratio": vol_ratio,
                "ctype": details.get("ctype"),
                "pattern_pts": new_pattern,
                "volume_pts": new_volume,
                "retest_pts": retest_pts,
                "ignition_pts": ignition_pts,
                "trend_pts": trend_pts,
                "new_total": new_total,
                "threshold": args.grade_threshold,
                "gating_reasons": ",".join(reason_parts) if reason_parts else "unknown",
            }
        )

    # Aggregate reason counts
    reason_counts: Dict[str, int] = {}
    for r in rows:
        for part in r["gating_reasons"].split(","):
            reason_counts[part] = reason_counts.get(part, 0) + 1

    # Print compact preview
    print(f"Symbol: {sym}")
    print(
        (
            f"Test1 trades: {len(t1)} | Test2 trades: {len(t2)} | "
            f"Filtered by breakout gating: {len(rows)}"
        )
    )
    print("Top gating reasons (count):")
    for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {reason}: {cnt}")
    preview = rows[:20]
    for r in preview:
        print(
            (
                f"- {r['datetime']} {r['direction']} | "
                f"body={r['body_pct']:.2f} volx={r['vol_ratio']:.2f} "
                f"ctype={r['ctype']} "
            )
            + (
                "pts b/v/r/i/t="
                f"{r['pattern_pts']}/{r['volume_pts']}/{r['retest_pts']}/"
                f"{r['ignition_pts']}/{r['trend_pts']} "
                f"total={r['new_total']} reasons={r['gating_reasons']}"
            )
        )

    if args.output:
        lines: List[str] = []
        lines.append(f"# Breakout filter diff for {sym}")
        lines.append("")
        lines.append(f"Test1 (filters disabled): {args.test1.name}")
        lines.append(f"Test2 (filters enabled): {args.test2.name}")
        lines.append("")
        lines.append(f"Filtered trades: {len(rows)} out of {len(t1)} (retained {len(t2)})")
        lines.append("")
        lines.append("## Gating reason counts")
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {reason}: {cnt}")
        lines.append("")
        lines.append(
            "| datetime | dir | breakout_time_5m | body_pct | vol_ratio | ctype | "
            "pattern_pts | volume_pts | retest_pts | ignition_pts | trend_pts | "
            "new_total | threshold | gating_reasons |"
        )
        lines.append("|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in rows:

            def fmt(x):
                try:
                    return f"{float(x):.2f}"
                except Exception:
                    return str(x)

            lines.append(
                "| "
                + " | ".join(
                    [
                        str(r.get("datetime")),
                        str(r.get("direction")),
                        str(r.get("breakout_time_5m")),
                        fmt(r.get("body_pct")),
                        fmt(r.get("vol_ratio")),
                        str(r.get("ctype")),
                        str(r.get("pattern_pts")),
                        str(r.get("volume_pts")),
                        str(r.get("retest_pts")),
                        str(r.get("ignition_pts")),
                        str(r.get("trend_pts")),
                        str(r.get("new_total")),
                        str(r.get("threshold")),
                        str(r.get("gating_reasons")),
                    ]
                )
                + " |"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines))
        print(f"Wrote detailed diff to {args.output}")


if __name__ == "__main__":
    main()
