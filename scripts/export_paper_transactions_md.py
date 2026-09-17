#!/usr/bin/env python3
"""Rebuild results/paper/TRANSACTIONS.md from the live paper fills ledger.

Source of truth is results/paper/fills.csv (appended by the paper trader).
This script only regenerates the human-readable Markdown view.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FILLS = ROOT / "results" / "paper" / "fills.csv"
PNL = ROOT / "results" / "paper" / "daily_pnl.csv"
OUT = ROOT / "results" / "paper" / "TRANSACTIONS.md"
ET = ZoneInfo("America/New_York")


def main() -> int:
    if not FILLS.exists():
        OUT.write_text(
            "# Paper trade transactions\n\n"
            "_No `fills.csv` yet — paper trader has not logged fills._\n",
            encoding="utf-8",
        )
        print(f"wrote empty stub → {OUT}")
        return 0

    rows: list[dict[str, str]] = []
    with FILLS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_day: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        iso = r.get("iso_time") or ""
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            day = dt.astimezone(ET).date().isoformat()
        except Exception:
            day = (iso[:10] if iso else "unknown")
        by_day[day].append(r)

    pnl_rows: list[dict[str, str]] = []
    if PNL.exists():
        with PNL.open(newline="", encoding="utf-8") as f:
            pnl_rows = list(csv.DictReader(f))

    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")
    lines: list[str] = [
        "# Paper trade transactions",
        "",
        f"_Auto-generated from `results/paper/fills.csv`. Last rebuilt: **{now_et}**._",
        "",
        "## Snapshot",
        "",
        f"- Total fills: **{len(rows)}**",
        f"- Days with fills: **{len(by_day)}**",
        "",
    ]

    if pnl_rows:
        lines += ["## Daily PnL (ET)", "", "| Day (ET) | Day PnL | Cum PnL | Fills | End equity |", "|---|---:|---:|---:|---:|"]
        for p in pnl_rows:
            lines.append(
                f"| {p.get('day_et','')} | {p.get('day_pnl','')} | {p.get('cum_pnl','')} | "
                f"{p.get('fills','')} | {p.get('end_equity','')} |"
            )
        lines.append("")

    lines += ["## Fills by day (ET)", ""]
    for day in sorted(by_day.keys(), reverse=True):
        day_rows = by_day[day]
        notional = 0.0
        for r in day_rows:
            try:
                notional += abs(float(r.get("notional") or 0))
            except ValueError:
                pass
        lines.append(f"### {day} — {len(day_rows)} fills · ~${notional:,.2f} notional")
        lines.append("")
        lines.append(
            "| Time (ET) | Side | Action | Size | Price | Notional | Market | Cash after |"
        )
        lines.append("|---|---|---|---:|---:|---:|---|---:|")
        for r in day_rows:
            iso = r.get("iso_time") or ""
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
                t = dt.strftime("%H:%M:%S")
            except Exception:
                t = iso
            q = (r.get("question") or r.get("market_id") or "")[:48]
            lines.append(
                f"| {t} | {r.get('side','')} | {r.get('action','')} | "
                f"{_num(r.get('size'))} | {_num(r.get('price'))} | {_num(r.get('notional'))} | "
                f"`{q}` | {_num(r.get('cash_after'))} |"
            )
        lines.append("")

    lines += [
        "## Notes",
        "",
        "- Paper / simulate-only. Not live exchange orders.",
        "- Source ledger: `results/paper/fills.csv` (append-only while the paper trader runs).",
        "- Rebuilt on the 10:00 and 22:00 America/New_York commit routine.",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} fills → {OUT} ({OUT.stat().st_size} bytes)")
    return 0


def _num(v: str | None) -> str:
    if v is None or v == "":
        return ""
    try:
        x = float(v)
        if abs(x) >= 100:
            return f"{x:.2f}"
        return f"{x:.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return str(v)


if __name__ == "__main__":
    raise SystemExit(main())
