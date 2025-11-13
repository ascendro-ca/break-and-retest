#!/usr/bin/env python3
import argparse
import json
import os
from collections import Counter


def load(path):
    with open(path, "r") as f:
        return json.load(f)


def classify_trades(results_path: str, tol_bps: float = 10.0, pierce_cap_bps: float | None = None):
    data = load(results_path)
    N = sum(len(s.get("signals", [])) for s in data)
    pierce = 0
    touch = 0
    over_cap = 0
    missing = 0
    pierce_depth_bps_hist = Counter()
    for sym in data:
        for t in sym.get("signals", []):
            lvl = t.get("level")
            # Wick-based fields
            rc = t.get("retest_candle") or {}
            low = rc.get("Low")
            high = rc.get("High")
            if lvl is None or low is None or high is None:
                missing += 1
                continue
            tol_price = float(lvl) * float(tol_bps) / 10000.0
            direction = t.get("direction")
            lvl = float(lvl)
            low = float(low)
            high = float(high)
            if direction == "long":
                touch_ = abs(low - lvl) <= tol_price + 1e-9
                depth_bps = max(0.0, (lvl - low) / lvl) * 10000.0
                pierce_ = low < (lvl - tol_price) - 1e-9
            else:  # short
                touch_ = abs(high - lvl) <= tol_price + 1e-9
                depth_bps = max(0.0, (high - lvl) / lvl) * 10000.0
                pierce_ = high > (lvl + tol_price) + 1e-9

            if touch_:
                touch += 1
            elif pierce_:
                pierce_depth_bps_hist[int(round(depth_bps))] += 1
                if pierce_cap_bps is not None and depth_bps > float(pierce_cap_bps) + 1e-9:
                    over_cap += 1
                else:
                    pierce += 1
            else:
                # Neither touch nor pierce under provided tol -> unexpected if
                # selection used 'either'
                missing += 1
    return {
        "total": N,
        "pierce": pierce,
        "touch": touch,
        "missing_or_neither": missing,
        "over_cap": over_cap,
        "pierce_share_pct": (100.0 * pierce / N) if N else 0.0,
        "touch_share_pct": (100.0 * touch / N) if N else 0.0,
        "pierce_depth_bps_hist": dict(sorted(pierce_depth_bps_hist.items())),
    }


def main():
    ap = argparse.ArgumentParser(description="Diagnose wick-contact composition of selected trades")
    ap.add_argument("results_json", help="Path to level1_*_profile_*.json")
    ap.add_argument(
        "--tol-bps", type=float, default=10.0, help="Touch tolerance in bps (default 10)"
    )
    ap.add_argument(
        "--pierce-cap-bps",
        type=float,
        default=20.0,
        help="Pierce cap in bps for classification (default 20)",
    )
    args = ap.parse_args()
    cap = args.pierce_cap_bps
    if cap < 0:
        cap = None
    stats = classify_trades(args.results_json, tol_bps=args.tol_bps, pierce_cap_bps=cap)
    print(f"File: {os.path.basename(args.results_json)}")
    print(f"Total trades: {stats['total']}")
    print(
        f"Touch within {args.tol_bps} bps: {stats['touch']} " f"({stats['touch_share_pct']:.2f}%)"
    )
    cap_label = cap if cap is not None else "None"
    print(
        f"Pierce <= cap {cap_label} bps: {stats['pierce']} " f"({stats['pierce_share_pct']:.2f}%)"
    )
    if stats["over_cap"]:
        print(f"Pierce over cap: {stats['over_cap']}")
    if stats["missing_or_neither"]:
        print(f"Missing/neither (sanity): {stats['missing_or_neither']}")
    # Optional small histogram output
    if stats["pierce_depth_bps_hist"]:
        depths = list(stats["pierce_depth_bps_hist"].items())[:10]
        print("Pierce depth bps (sample up to 10 bins):", depths)


if __name__ == "__main__":
    main()
