#!/usr/bin/env python3
# isort: skip_file
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd


def load_results(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        return json.load(f)


def build_key(dt: Any, direction: Any) -> Tuple[str, str]:
    return (str(dt), str(direction))


def to_ts(s: Any) -> Optional[pd.Timestamp]:
    try:
        t = pd.to_datetime(s)
        if getattr(t, "tzinfo", None) is None:
            t = t.tz_localize("UTC")
        return t
    except Exception:
        return None


def attach_signal_features(
    trades: List[Dict[str, Any]], signals: List[Dict[str, Any]]
) -> pd.DataFrame:
    sig_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for s in signals or []:
        sig_index[build_key(s.get("datetime"), s.get("direction"))] = s

    rows: List[Dict[str, Any]] = []
    for tr in trades or []:
        key = build_key(tr.get("datetime"), tr.get("direction"))
        s = sig_index.get(key, {})
        pts = (s or {}).get("points", {}) or {}
        # Risk-based vs capped sizing diagnostics
        try:
            entry = float(tr.get("entry")) if tr.get("entry") is not None else None
            stop = float(tr.get("stop")) if tr.get("stop") is not None else None
            shares = int(tr.get("shares", 0) or 0)
            risk_amount = float(tr.get("risk_amount", 0.0) or 0.0)
            rr = float(tr.get("rr_ratio", s.get("rr_ratio", 0.0)) or 0.0)
            rps = (
                abs((entry or 0.0) - (stop or 0.0))
                if entry is not None and stop is not None
                else None
            )
            rbs = (risk_amount / rps) if (rps and rps > 0) else None  # risk-based shares
            cap_bound = rbs is not None and shares < max(0, int(rbs)) - 1
            # expected win P&L if risk-based sizing dominates vs realized sizing
            exp_win_rb = rr * risk_amount if rr and risk_amount else None
            exp_win_real = rr * (rps or 0.0) * shares if rr and (rps is not None) else None
        except Exception:
            rps = None
            rbs = None
            cap_bound = None
            exp_win_rb = None
            exp_win_real = None

        row = {
            # trade fields
            "symbol": s.get("ticker") or None,
            "datetime": tr.get("datetime"),
            "exit_time": tr.get("exit_time"),
            "direction": tr.get("direction"),
            "entry": tr.get("entry"),
            "exit": tr.get("exit"),
            "stop": tr.get("stop"),
            "target": tr.get("target"),
            "shares": tr.get("shares"),
            "pnl": tr.get("pnl"),
            "outcome": tr.get("outcome"),
            "rr_ratio": tr.get("rr_ratio", s.get("rr_ratio")),
            "risk_amount": tr.get("risk_amount"),
            "risk_per_share": rps,
            "risk_based_shares": rbs,
            "cap_bound": cap_bound,
            "exp_win_rb": exp_win_rb,
            "exp_win_real": exp_win_real,
            # signal points
            "bo_pat": pts.get("breakout_pattern_pts"),
            "bo_vol": pts.get("breakout_volume_pts"),
            "bo": pts.get("breakout"),
            "rt": pts.get("retest"),
            "ig": pts.get("ignition"),
            "tr": pts.get("trend"),
            "tot": pts.get("total"),
            # other features
            "bo_body": s.get("breakout_body_pct"),
            "bo_vol_ratio": s.get("breakout_vol_ratio"),
            "rt_vol_ratio": s.get("retest_vol_ratio"),
            "ig_body": s.get("ignition_body_pct"),
            "ig_vol_ratio": s.get("ignition_vol_ratio"),
            "dist_to_target": s.get("distance_to_target"),
            "bo_ctype": pts.get("breakout_ctype", s.get("breakout_ctype")),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # Parse timestamps and compute ET minute-of-day
    if not df.empty:
        ts = df["datetime"].apply(to_ts)
        df["ts"] = ts
        # Convert to ET
        try:
            df["ts_et"] = df["ts"].apply(
                lambda t: t.tz_convert(ZoneInfo("America/New_York")) if t is not None else None
            )
        except Exception:
            df["ts_et"] = df["ts"]

        def tod_minutes(t: Optional[pd.Timestamp]) -> Optional[int]:
            if t is None:
                return None
            return t.hour * 60 + t.minute

        df["et_min"] = df["ts_et"].apply(tod_minutes)
    return df


def summarize(df: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Level 1 Winner Pattern Mining Summary\n")
    if df.empty:
        lines.append("No trades found.")
        return "\n".join(lines)
    total = len(df)
    wins = int((df["outcome"] == "win").sum())
    wr = wins / total if total else 0.0
    pnl = float(df["pnl"].sum())
    lines.append(
        f"Total trades: {total} | Winners: {wins} | Win%: {wr*100:.1f}% | P&L: ${pnl:,.2f}"
    )
    # Feature means by outcome
    for col in [
        "bo_pat",
        "bo_vol",
        "rt",
        "ig",
        "tr",
        "bo_body",
        "bo_vol_ratio",
        "rt_vol_ratio",
        "ig_body",
        "ig_vol_ratio",
        "rr_ratio",
    ]:
        if col in df.columns and df[col].notna().any():
            w = df[df["outcome"] == "win"][col].astype(float)
            losses_series = df[df["outcome"] == "loss"][col].astype(float)
            lines.append(
                (
                    f"- {col}: win mean={w.mean():.2f}, p50={w.median():.2f} | "
                    f"loss mean={losses_series.mean():.2f}, p50={losses_series.median():.2f}"
                )
            )
    # Time-of-day distribution
    if "et_min" in df.columns:

        def pct(x):
            return f"{100*x:.1f}%"

        morning = df[(df["et_min"] >= 9 * 60 + 30) & (df["et_min"] <= 10 * 60 + 45)]
        midday = df[(df["et_min"] > 10 * 60 + 45) & (df["et_min"] <= 12 * 60 + 0)]
        afternoon = df[df["et_min"] > 12 * 60 + 0]
        for name, part in [
            ("09:30-10:45", morning),
            ("10:46-12:00", midday),
            ("12:01-16:00", afternoon),
        ]:
            if not part.empty:
                wrp = (part["outcome"] == "win").mean()
                lines.append(f"- Time {name}: trades={len(part)} win%={pct(wrp)}")
    return "\n".join(lines)


def grid_search(df: pd.DataFrame, target_min=100, target_max=200) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    # Define grid
    pat_opts = [15, 17, 20]
    vol_opts = [5, 10]
    rt_opts = [20, 25, 30]
    ig_opts = [15, 20, 25]
    igvr_opts = [0.0, 0.5, 1.0]
    bo_vr_opts = [0.0, 1.5, 1.8, 2.0]
    rt_vr_opts = [0.0, 0.5, 0.8, 1.0]
    exp_win_min_opts = [0.0, 50.0, 75.0, 100.0]  # filter out tiny-dollar wins
    cap_bound_opts = [None, False]  # prefer non-capped where per-win ~ rr * risk_amount
    # time windows in ET minutes (start,end)
    tw_opts = [(9 * 60 + 35, 10 * 60 + 30), (9 * 60 + 45, 10 * 60 + 45), (9 * 60 + 50, 11 * 60 + 0)]

    results: List[Dict[str, Any]] = []
    base = df.copy()
    for pat in pat_opts:
        for vol in vol_opts:
            filt1 = base[(base["bo_pat"] >= pat) & (base["bo_vol"] >= vol)]
            for rt in rt_opts:
                for ig in ig_opts:
                    f2 = filt1[(filt1["rt"] >= rt) & (filt1["ig"] >= ig)]
                    for igvr in igvr_opts:
                        f3 = f2[(f2["ig_vol_ratio"] >= igvr)]
                        for bo_vr in bo_vr_opts:
                            f4 = f3[(f3["bo_vol_ratio"] >= bo_vr)]
                            for rt_vr in rt_vr_opts:
                                f5 = f4[(f4["rt_vol_ratio"] >= rt_vr)]
                                for exp_min in exp_win_min_opts:
                                    f6 = f5[
                                        (f5["exp_win_real"] >= exp_min)
                                        | (f5["exp_win_rb"] >= exp_min)
                                    ]
                                    for cap_pref in cap_bound_opts:
                                        f7 = f6
                                        if cap_pref is not None and "cap_bound" in f6.columns:
                                            f7 = f6[f6["cap_bound"] == cap_pref]
                                        for start, end in tw_opts:
                                            f = f7[(f7["et_min"] >= start) & (f7["et_min"] <= end)]
                                            n = len(f)
                                            if n == 0:
                                                continue
                                            wins = int((f["outcome"] == "win").sum())
                                            wr = wins / n if n else 0.0
                                            pnl = float(f["pnl"].sum())
                                            # realized avg $ per win (helpful for feasibility)
                                            avg_win = float(
                                                f.loc[f["outcome"] == "win", "pnl"].mean() or 0.0
                                            )
                                            results.append(
                                                {
                                                    "pat": pat,
                                                    "vol": vol,
                                                    "rt": rt,
                                                    "ig": ig,
                                                    "igvr": igvr,
                                                    "bo_vr": bo_vr,
                                                    "rt_vr": rt_vr,
                                                    "exp_min": exp_min,
                                                    "cap_free": (cap_pref is False),
                                                    "tw": f"{start}->{end}",
                                                    "trades": n,
                                                    "wins": wins,
                                                    "wr": wr,
                                                    "pnl": pnl,
                                                    "avg_win": avg_win,
                                                }
                                            )
    res_df = pd.DataFrame(results)
    if res_df.empty:
        return res_df
    # Filter to target band; if none, keep top 50 by pnl
    band = res_df[(res_df["trades"] >= target_min) & (res_df["trades"] <= target_max)]
    if band.empty:
        band = res_df.nlargest(50, "pnl")
    return band.sort_values(["pnl", "wr"], ascending=[False, False]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description="Mine Level1 winners and grid-search simple filters.")
    ap.add_argument("results", type=Path, help="Path to Level1 JSON results file")
    ap.add_argument("--target-min", type=int, default=100)
    ap.add_argument("--target-max", type=int, default=200)
    ap.add_argument("--output", type=Path, help="Optional path to write Markdown report")
    args = ap.parse_args()

    data = load_results(args.results)
    # Flatten across symbols
    all_rows: List[pd.DataFrame] = []
    for sym_rec in data:
        trades = sym_rec.get("trades", []) or []
        signals = sym_rec.get("signals", []) or []
        if trades:
            df = attach_signal_features(trades, signals)
            df["symbol"] = sym_rec.get("symbol")
            all_rows.append(df)
    if not all_rows:
        print("No trades found in results.")
        return
    df_all = pd.concat(all_rows, ignore_index=True)
    # Basic summary
    text = summarize(df_all)
    print(text)

    # Grid search filters
    candidates = grid_search(df_all, target_min=args.target_min, target_max=args.target_max)
    if candidates.empty:
        print("\nNo candidate filter sets found.")
        return
    # Show top 10
    print("\nTop candidate filter sets (by P&L, tie-break win rate):")
    print(candidates.head(10).to_string(index=False))

    if args.output:
        lines: List[str] = []
        lines.append(text)
        lines.append("\n## Top candidate filter sets\n")
        lines.append(candidates.head(25).to_markdown(index=False))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines))
        print(f"Wrote report to {args.output}")


if __name__ == "__main__":
    main()
