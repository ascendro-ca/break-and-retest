#!/usr/bin/env python3
"""
Scan backtest_results/histograms for histogram HTML files and build an index page.

Output: backtest_results/histograms/index.html

Groups related files by common prefix (before the trailing _winners/_losers/_both).
Sorted by file modification time (most recent groups first).
"""

from __future__ import annotations

import argparse
import html
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Entry:
    prefix: str
    winners: Optional[Path]
    losers: Optional[Path]
    both: Optional[Path]
    mtime: float


def build_index(hist_dir: Path) -> List[Entry]:
    files = list(hist_dir.glob("*.html"))
    groups: Dict[str, Dict[str, Path]] = {}
    mtimes: Dict[str, float] = {}
    for f in files:
        name = f.name
        if name.endswith("_winners.html"):
            key = name[: -len("_winners.html")]
            groups.setdefault(key, {})["winners"] = f
        elif name.endswith("_losers.html"):
            key = name[: -len("_losers.html")]
            groups.setdefault(key, {})["losers"] = f
        elif name.endswith("_both.html"):
            key = name[: -len("_both.html")]
            groups.setdefault(key, {})["both"] = f
        else:
            # ignore non-matching html files
            continue
        # Track most recent mtime across modes for the group
        m = f.stat().st_mtime
        if key not in mtimes or m > mtimes[key]:
            mtimes[key] = m

    entries: List[Entry] = []
    for key, d in groups.items():
        entries.append(
            Entry(
                prefix=key,
                winners=d.get("winners"),
                losers=d.get("losers"),
                both=d.get("both"),
                mtime=mtimes.get(key, 0.0),
            )
        )
    # Sort newest first
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries


def render_html(entries: List[Entry], title: str = "Score Histograms Index") -> str:
    rows: List[str] = []
    rows.append("<table>")
    rows.append(
        "<thead><tr>"
        "<th>Result prefix</th>"
        "<th>Winners</th>"
        "<th>Losers</th>"
        "<th>Combined</th>"
        "<th>Updated</th>"
        "</tr></thead>"
    )
    rows.append("<tbody>")
    for e in entries:

        def link_or_dash(p: Optional[Path]) -> str:
            return f'<a href="{html.escape(p.name)}" target="_blank">open</a>' if p else "—"

        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.mtime)) if e.mtime else "—"
        rows.append(
            "<tr>"
            f"<td class=prefix>{html.escape(e.prefix)}</td>"
            f"<td>{link_or_dash(e.winners)}</td>"
            f"<td>{link_or_dash(e.losers)}</td>"
            f"<td>{link_or_dash(e.both)}</td>"
            f"<td class=mtime>{updated}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")

    css = """
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px}
    h1{font-size:20px;margin:0 0 16px 0}
    table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #e5e7eb;padding:8px 10px;text-align:left;font-size:14px}
    thead th{background:#f9fafb}
    tr:nth-child(even){background:#fafafa}
    .prefix{font-family:monospace}
    .mtime{white-space:nowrap}
    footer{margin-top:16px;color:#6b7280;font-size:12px}
    """

    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{css}</style>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>"
        + "\n".join(rows)
        + "<footer>Generated automatically from backtest_results/histograms</footer>"
        "</body></html>"
    )
    return html_doc


def main():
    ap = argparse.ArgumentParser(description="Generate index for histogram HTML files")
    ap.add_argument(
        "--dir",
        default="backtest_results/histograms",
        help="Directory containing histogram HTML files",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Output index.html path (default: <dir>/index.html)",
    )
    args = ap.parse_args()

    hist_dir = Path(args.dir)
    hist_dir.mkdir(parents=True, exist_ok=True)
    entries = build_index(hist_dir)
    html_doc = render_html(entries)
    out_path = Path(args.out) if args.out else hist_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Index written: {out_path}")


if __name__ == "__main__":
    main()
