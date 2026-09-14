#!/usr/bin/env python3
"""Rebuild research/window_{30,60,90}d_days.txt (+ full_available alias) from slim_days.

30/60 = calendar windows ending at the latest slim day (skip missing Jun12–17).
90 / full_available = all cached continuous slim days (May14 → latest).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIM = ROOT / "data" / "slim_days"
RESEARCH = ROOT / "research"


def list_slim_days() -> list[str]:
    days = sorted(p.stem for p in SLIM.glob("*.parquet") if p.stat().st_size > 0)
    if not days:
        raise SystemExit(f"no slim days in {SLIM}")
    return days


def calendar_window(days: list[str], n_cal: int) -> list[str]:
    end = datetime.fromisoformat(days[-1])
    start = end - timedelta(days=n_cal - 1)
    return [d for d in days if datetime.fromisoformat(d) >= start]


def write_days(path: Path, days: list[str], header: str | None = None) -> None:
    lines = ([header.rstrip() + "\n"] if header else []) + [d + "\n" for d in days]
    path.write_text("".join(lines))


def rebuild() -> dict:
    days = list_slim_days()
    w30 = calendar_window(days, 30)
    w60 = calendar_window(days, 60)
    w90 = days  # full available continuous

    write_days(RESEARCH / "window_30d_days.txt", w30)
    write_days(RESEARCH / "window_60d_days.txt", w60)
    write_days(RESEARCH / "window_90d_days.txt", w90)
    write_days(
        RESEARCH / "window_full_available_days.txt",
        w90,
        header="# Full available continuous slim window (all cached days; skips archive gap Jun12-17)",
    )

    meta = {
        "n_slim": len(days),
        "first": days[0],
        "last": days[-1],
        "n_30": len(w30),
        "n_60": len(w60),
        "n_90": len(w90),
        "range_30": f"{w30[0]} → {w30[-1]}" if w30 else None,
        "range_60": f"{w60[0]} → {w60[-1]}" if w60 else None,
        "range_90": f"{w90[0]} → {w90[-1]}" if w90 else None,
    }
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    meta = rebuild()
    print("[rebuild_window_days]", meta, flush=True)


if __name__ == "__main__":
    main()
