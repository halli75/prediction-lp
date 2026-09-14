#!/usr/bin/env python3
"""Re-score pool100 (strategy.py) liveish on Aug10-ending 30/60/90 windows.

One window at a time; new subprocess per window so memory is released.
Does not overwrite strategy_current_best.
"""
from __future__ import annotations

import gc
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "bin" / "python"
EVAL = ROOT / "scripts" / "eval_window.py"
STRAT = ROOT / "strategy.py"
OUT = ROOT / "results" / "liveish_pool100_aug10_30_60_90.json"
MIN_AVAIL_MB = 2800

WINDOWS = [
    ("30d", ROOT / "research" / "window_30d_days.txt"),
    ("60d", ROOT / "research" / "window_60d_days.txt"),
    ("90d", ROOT / "research" / "window_90d_days.txt"),
]


def mem_avail_mb() -> float:
    info = {}
    for ln in Path("/proc/meminfo").read_text().splitlines():
        k, v = ln.split(":", 1)
        parts = v.split()
        info[k] = float(parts[0])  # kB
    return info.get("MemAvailable", info.get("MemFree", 0.0)) / 1024.0


def wait_for_memory(need_mb: float, timeout_s: float = 240.0) -> bool:
    t0 = time.time()
    while True:
        avail = mem_avail_mb()
        print(f"[mem] available={avail:.0f}MB need={need_mb:.0f}MB", flush=True)
        if avail >= need_mb:
            return True
        if time.time() - t0 > timeout_s:
            return False
        time.sleep(15)


def run_window(name: str, days_file: Path) -> dict:
    need = {"30d": 3200, "60d": 4000, "90d": 5200}[name]
    if not wait_for_memory(need, timeout_s=300.0):
        return {
            "error": "insufficient_memory",
            "mem_avail_mb": mem_avail_mb(),
            "need_mb": need,
            "skipped": True,
        }
    cmd = [
        str(PY),
        str(EVAL),
        "--liveish",
        "--days-file",
        str(days_file),
        "--strategy-module",
        str(STRAT),
        "--capital",
        "10000",
    ]
    print(f"[run] {name} {' '.join(cmd)}", flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    elapsed = time.time() - t0
    raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
    part_path = ROOT / "results" / f"liveish_pool100_aug10_{name}.json"
    if proc.returncode != 0:
        err = {
            "error": "eval_failed",
            "returncode": proc.returncode,
            "elapsed_sec": round(elapsed, 3),
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-2000:],
            "oom": "MemoryError" in raw or "Killed" in raw or proc.returncode in (9, 137, -9),
        }
        part_path.write_text(json.dumps(err, indent=2) + "\n")
        print(json.dumps(err, indent=2), flush=True)
        return err
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        err = {"error": "no_json", "stdout_tail": raw[-2000:], "elapsed_sec": round(elapsed, 3)}
        part_path.write_text(json.dumps(err, indent=2) + "\n")
        return err
    metrics = json.loads(raw[start : end + 1])
    metrics["window"] = name
    metrics["days_file"] = str(days_file.relative_to(ROOT))
    metrics["days_range"] = [metrics["days"][0], metrics["days"][-1]] if metrics.get("days") else None
    metrics["wall_elapsed_sec"] = round(elapsed, 3)
    part_path.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    print(
        f"[done] {name} net={metrics.get('net_pnl')} dd={metrics.get('max_dd_pct')} "
        f"fills={metrics.get('n_fills')} days={metrics.get('n_days')} "
        f"rows={metrics.get('n_price_rows')} elapsed={elapsed:.1f}s",
        flush=True,
    )
    gc.collect()
    return metrics


def main() -> None:
    t0 = time.time()
    out = {
        "job": "liveish_pool100_aug10_30_60_90",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": "strategy.py",
        "champion": "pool100",
        "min_daily_reward_pool": 100.0,
        "liveish": True,
        "windows_end": "2026-08-10",
        "optimistic_ref": {
            "source": "results/pool100_expand_summary.json",
            "30d": 3192.4223,
            "60d": 3634.586,
            "90d": 3171.5655,
        },
        "prior_liveish_old_windows": {
            "note": "old day lists (not ending 2026-08-10)",
            "sample": 528.35,
            "30d": 432.94,
            "60d": 423.35,
        },
        "windows": {},
        "notes": [
            "One window at a time via scripts/eval_window.py --liveish",
            "Did not overwrite strategy_current_best",
            "Did not write giant prices.parquet",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")

    for name, days_file in WINDOWS:
        print(f"\n===== {name} =====", flush=True)
        m = run_window(name, days_file)
        out["windows"][name] = m
        out["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out["elapsed_sec"] = round(time.time() - t0, 3)
        OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
        gc.collect()
        if m.get("skipped") or m.get("oom") or m.get("error"):
            print(f"[stop] {name} failed/skipped; not continuing larger windows", flush=True)
            if name != "90d":
                break

    # compact summary
    summary = {}
    for name, m in out["windows"].items():
        if "net_pnl" in m:
            summary[name] = {
                "net_pnl": m.get("net_pnl"),
                "reward_pnl": m.get("reward_pnl"),
                "trading_pnl": m.get("trading_pnl"),
                "max_dd_pct": m.get("max_dd_pct"),
                "n_fills": m.get("n_fills"),
                "n_days": m.get("n_days"),
                "n_price_rows": m.get("n_price_rows"),
                "soft_reject": m.get("soft_reject"),
                "days_range": m.get("days_range"),
            }
        else:
            summary[name] = {k: m.get(k) for k in ("error", "oom", "skipped", "mem_avail_mb")}
    out["summary"] = summary
    out["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["elapsed_sec"] = round(time.time() - t0, 3)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("\n===== SUMMARY =====", flush=True)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
