#!/usr/bin/env python3
"""Monitor prepare.py expand; when done (or PID dies), rebuild 30/60/90 and eval pool100."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")
LOG = ROOT / "results" / "prepare_90d_expand.log"
STATUS = ROOT / "results" / "prepare_90d_expand_watch.json"
OUT_DIR = ROOT / "results" / "pool100_expand_evals"
STRAT = ROOT / "research" / "champions" / "strategy_pool100.py"
PREPARE_PID = int(os.environ.get("PREPARE_PID", "147408"))


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def slim_count() -> int:
    d = ROOT / "data" / "slim_days"
    return sum(1 for p in d.glob("*.parquet") if p.stat().st_size > 0)


def log_tail(n: int = 8) -> list[str]:
    if not LOG.exists():
        return []
    lines = LOG.read_text(errors="replace").splitlines()
    return lines[-n:]


def write_status(**kw) -> None:
    payload = {"updated_at": utc(), **kw}
    if STATUS.exists():
        try:
            prev = json.loads(STATUS.read_text())
            prev.update(payload)
            payload = prev
        except Exception:
            pass
    STATUS.write_text(json.dumps(payload, indent=2) + "\n")


def rebuild() -> dict:
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "rebuild_window_days.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    print(proc.stdout, flush=True)
    if proc.returncode != 0:
        print(proc.stderr, flush=True)
        raise SystemExit(f"rebuild failed rc={proc.returncode}")
    # parse meta from stdout if present
    return {"stdout": proc.stdout.strip()}


def eval_window(label: str, days_file: Path, out: Path) -> dict:
    print(f"[eval] pool100 {label} days={days_file} ...", flush=True)
    t0 = time.time()
    proc = subprocess.run(
        [
            PY,
            str(ROOT / "scripts" / "eval_window.py"),
            "--days-file",
            str(days_file),
            "--strategy-module",
            str(STRAT),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:], proc.stderr[-2000:], flush=True)
        raise SystemExit(f"eval {label} failed rc={proc.returncode}")
    raw = proc.stdout.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise SystemExit(f"no JSON from eval_window {label}: {raw[:400]}")
    metrics = json.loads(raw[start : end + 1])
    metrics["label"] = f"pool100_{label}"
    metrics["window"] = label
    metrics["days_file"] = str(days_file.relative_to(ROOT))
    metrics["strategy"] = str(STRAT.relative_to(ROOT))
    metrics["elapsed_wall_sec"] = round(time.time() - t0, 2)
    metrics["evaluated_at"] = utc()
    out.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    print(
        f"[eval] {label} net={metrics.get('net_pnl')} dd={metrics.get('max_dd_pct')} "
        f"n_days={metrics.get('n_days')} -> {out}",
        flush=True,
    )
    return metrics


def run_evals() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, days_name in [
        ("30d", "window_30d_days.txt"),
        ("60d", "window_60d_days.txt"),
        ("90d", "window_90d_days.txt"),
    ]:
        days_file = ROOT / "research" / days_name
        out = OUT_DIR / f"pool100_{label}.json"
        results[label] = eval_window(label, days_file, out)
    summary = {
        "job": "pool100_expand_window_evals",
        "updated_at": utc(),
        "strategy": str(STRAT.relative_to(ROOT)),
        "windows": {
            k: {
                "net_pnl": v.get("net_pnl"),
                "reward_pnl": v.get("reward_pnl"),
                "trading_pnl": v.get("trading_pnl"),
                "max_dd_pct": v.get("max_dd_pct"),
                "n_days": v.get("n_days"),
                "n_fills": v.get("n_fills"),
                "soft_reject": v.get("soft_reject"),
                "artifact": str((OUT_DIR / f"pool100_{k}.json").relative_to(ROOT)),
            }
            for k, v in results.items()
        },
    }
    summary_path = ROOT / "results" / "pool100_expand_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    # Also refresh full-available alias artifact for pool100
    full_out = ROOT / "results" / "eval_full_available_pool100.json"
    m90 = dict(results["90d"])
    m90["label"] = "pool100"
    m90["window"] = "full_available"
    m90["days_file"] = "research/window_90d_days.txt"
    m90["note"] = (
        "Longest honest local continuous window: all slim_days "
        f"(May14→{results['90d'].get('days', ['?'])[-1] if results['90d'].get('days') else '?'}, "
        "skip Jun12–17). Post-Jul21 expand."
    )
    full_out.write_text(json.dumps(m90, indent=2, default=str) + "\n")
    print(f"[summary] wrote {summary_path}", flush=True)
    return summary


def prepare_looks_done(pid: int) -> bool:
    if not alive(pid):
        return True
    # also treat log "done" / final assemble as complete
    tail = "\n".join(log_tail(30)).lower()
    markers = (
        "all days done",
        "prepare complete",
        "finished continuous",
        "mode=continuous_l2 target=",
    )
    # if progress X/X appears
    for line in log_tail(50):
        if "progress" in line and "/" in line:
            # e.g. progress 83/83
            try:
                part = line.split("progress", 1)[1].strip().split()[0]
                a, b = part.split("/")
                if int(a) >= int(b):
                    # wait until process exits though
                    return False
            except Exception:
                pass
    return False


def main() -> None:
    pid = PREPARE_PID
    write_status(
        phase="watching",
        prepare_pid=pid,
        prepare_alive=alive(pid),
        slim_n=slim_count(),
        log_tail=log_tail(5),
    )
    print(f"[watch] prepare_pid={pid} alive={alive(pid)} slim={slim_count()}", flush=True)

    last_slim = slim_count()
    last_rebuild_n = 0
    poll = 20
    while alive(pid):
        n = slim_count()
        write_status(
            phase="watching",
            prepare_pid=pid,
            prepare_alive=True,
            slim_n=n,
            log_tail=log_tail(6),
        )
        # incremental rebuild of day lists as days accumulate (every +5)
        if n >= last_rebuild_n + 5 or (n > last_rebuild_n and n % 5 == 0):
            print(f"[watch] interim rebuild at slim={n}", flush=True)
            rebuild()
            last_rebuild_n = n
            write_status(phase="interim_rebuilt", slim_n=n, last_rebuild_n=n)
        if n != last_slim:
            print(f"[watch] slim {last_slim} -> {n}", flush=True)
            last_slim = n
        time.sleep(poll)

    print(f"[watch] prepare pid={pid} exited; slim={slim_count()}", flush=True)
    write_status(phase="prepare_exited", prepare_alive=False, slim_n=slim_count())

    # Final rebuild + evals
    print("[watch] final rebuild + pool100 30/60/90 evals", flush=True)
    rebuild()
    write_status(phase="evaluating", slim_n=slim_count())
    summary = run_evals()
    write_status(phase="done", slim_n=slim_count(), summary=summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
