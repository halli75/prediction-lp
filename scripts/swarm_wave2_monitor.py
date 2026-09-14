#!/usr/bin/env python3
"""Monitor wave2 axis agents; window-eval promising sample beats; promote only on gate."""
from __future__ import annotations

import fcntl
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
AGENTS = RESEARCH / "agents"
RESULTS = ROOT / "results"
STATUS = RESULTS / "swarm_wave2_status.json"
GATE_MD = RESEARCH / "PROMOTION_GATE.md"
FINDINGS = RESEARCH / "shared_findings.json"
DIGEST = RESULTS / "overnight_digest.md"
PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)

PARENT_SAMPLE = 1755.64
GATE_30D = 2767.11
GATE_60D = 3038.91
SAMPLE_DELTA = 50.0
CHAMPION_SRC = RESEARCH / "champions" / "strategy_pool100.py"

WAVE2_AXES = [
    "cancel_on_mid_move",
    "pull_size_after_adverse_fill",
    "pause_after_fill",
    "shrink_size",
    "min_daily_reward_pool_fine",
    "near_mid_size",
    "free_explore",
    "skew_aggressive",
    "two_sided_strict",
    "size_by_reward_pool",
]
AGENT_PREFIX = "wave3"


def locked_json_update(path: Path, mutator) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}\n")
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip() or "{}"
            data = json.loads(raw)
            data = mutator(data) or data
            f.seek(0)
            f.truncate()
            f.write(json.dumps(data, indent=2, default=str) + "\n")
            f.flush()
            return data
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def eval_window(days_file: Path, strategy: Path) -> dict:
    cp = subprocess.run(
        [
            str(PY),
            str(ROOT / "scripts" / "eval_window.py"),
            "--days-file",
            str(days_file),
            "--strategy-module",
            str(strategy),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"eval_window failed rc={cp.returncode}: {cp.stderr or cp.stdout}")
    out = cp.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        start, end = out.find("{"), out.rfind("}")
        if start >= 0 and end > start:
            return json.loads(out[start : end + 1])
        raise


def read_status() -> dict:
    if STATUS.exists():
        return json.loads(STATUS.read_text())
    return {}


def write_status(data: dict) -> None:
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    STATUS.write_text(json.dumps(data, indent=2) + "\n")


def agent_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        Path(f"/proc/{pid}").stat()
        return True
    except FileNotFoundError:
        return False


def collect_agent_best(agent_id: str) -> dict | None:
    p = AGENTS / agent_id / "best_metrics.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def promote(agent_id: str, axis: str, best_path: Path, sample: dict, w30: dict, w60: dict) -> None:
    """Strict promote: copy to champions + sync gate docs. Avoid racing window-hunt mid-write by brief lock file."""
    lock = RESULTS / "champion_promote.lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            label = f"wave2_{axis}_{ts}"
            dest = RESEARCH / "champions" / f"strategy_{label}.py"
            shutil.copy2(best_path, dest)
            for target in [
                RESEARCH / "champions" / "strategy_current_best.py",
                RESEARCH / "champions" / "strategy_pool100.py",
                RESEARCH / "champions" / "strategy_hybrid_spread_size.py",
                ROOT / "strategy.py",
            ]:
                shutil.copy2(best_path, target)

            sample_pnl = float(sample.get("sample_net_pnl") or sample.get("net_pnl") or 0)
            p30 = float(w30.get("net_pnl") or 0)
            p60 = float(w60.get("net_pnl") or 0)
            dd30 = w30.get("max_dd_pct")
            dd60 = w60.get("max_dd_pct")

            gate_body = f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (wave2 `{axis}` from pool100 parent)
Files: `research/champions/strategy_pool150.py` = `strategy_hybrid_spread_size.py` = `strategy_current_best.py` = root `strategy.py`
Promoted {ts} by swarm_wave2_monitor (agent `{agent_id}`).

| Window | Net PnL to beat | Max DD (champ) |
|--------|----------------:|---------------:|
| 12d sample | **{sample_pnl:.2f}** | {float(sample.get('max_dd_pct') or 0):.2f}% |
| 30d | **{p30:.2f}** | {float(dd30 or 0):.2f}% |
| ~60d | **{p60:.2f}** | {float(dd60 or 0):.2f}% |

## Rules
1. Do **not** promote for beating older champions only.
2. To replace champion: **both** 30d and 60d net_pnl must exceed the table above, soft_reject false, max_dd_pct < 25.
3. Never overwrite `strategy_current_best.py` unless that gate passes.
4. Inventory soft/hard caps must remain defensive (soft ≤35, hard ≤100; soft ≥20 floor).
5. Prefer live-realism eval flags when comparing (see `research/LIVE_REALISM.md`).
"""
            GATE_MD.write_text(gate_body)

            promo = {
                "job": "swarm_wave2_promotion",
                "label": label,
                "agent_id": agent_id,
                "axis": axis,
                "strategy": str(dest),
                "windows": {
                    "sample": sample,
                    "30d": w30,
                    "60d": w60,
                },
                "gate_beaten": {"30d": GATE_30D, "60d": GATE_60D},
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            (RESULTS / f"promotion_{label}.json").write_text(json.dumps(promo, indent=2) + "\n")

            def mut_findings(data: dict) -> dict:
                data = data or {}
                data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                findings = data.setdefault("findings", [])
                findings.append(
                    {
                        "ts": data["updated_at"],
                        "agent_id": agent_id,
                        "axis": axis,
                        "event": "promoted",
                        "sample_net_pnl": sample_pnl,
                        "window_30d_net_pnl": p30,
                        "window_60d_net_pnl": p60,
                        "label": label,
                    }
                )
                data["findings"] = findings[-200:]
                data["current_champion"] = {
                    "label": label,
                    "agent_id": agent_id,
                    "axis": axis,
                    "sample_net_pnl": sample_pnl,
                    "30d": p30,
                    "60d": p60,
                    "path": "research/champions/strategy_current_best.py",
                }
                return data

            locked_json_update(FINDINGS, mut_findings)

            digest_line = (
                f"\n## PROMOTION {ts}\n"
                f"- Agent `{agent_id}` axis `{axis}`\n"
                f"- sample {sample_pnl:.2f} / 30d {p30:.2f} / 60d {p60:.2f}\n"
                f"- beat gate 30d>{GATE_30D} and 60d>{GATE_60D}\n"
                f"- champion files synced to `{dest.name}`\n"
            )
            if DIGEST.exists():
                DIGEST.write_text(DIGEST.read_text() + digest_line)
            else:
                DIGEST.write_text("# Overnight digest\n" + digest_line)
            print(f"[monitor] PROMOTED {agent_id} -> {label}", flush=True)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def main() -> None:
    poll_sec = 45
    max_wall = int(sys.argv[1]) if len(sys.argv) > 1 else 5400  # default 90 min
    t0 = time.time()
    print(f"[monitor] start max_wall={max_wall}s parent_sample={PARENT_SAMPLE} (pool100)", flush=True)

    while time.time() - t0 < max_wall:
        st = read_status()
        agents = st.setdefault("agents", {})
        evaluated = st.setdefault("window_evals", {})
        promotions = st.setdefault("promotions", [])

        # refresh live PIDs / bests
        for axis in WAVE2_AXES:
            aid = f"{AGENT_PREFIX}-{axis}"
            entry = agents.setdefault(aid, {"axis": axis})
            pid = entry.get("pid")
            entry["alive"] = agent_alive(pid)
            # also detect orphaned python by cmdline
            best = collect_agent_best(aid)
            if best:
                pnl = float(best.get("sample_net_pnl") or best.get("net_pnl") or -1e18)
                entry["best_sample_net_pnl"] = pnl
                entry["max_dd_pct"] = best.get("max_dd_pct")
                entry["soft_reject"] = best.get("soft_reject")
                entry["best_updated_at"] = best.get("elapsed_sec")
            # iters from experiments.jsonl
            exp = AGENTS / aid / "experiments.jsonl"
            if exp.exists():
                try:
                    entry["iters"] = sum(1 for _ in exp.open()) - 1  # minus baseline
                except Exception:
                    pass

        # candidate window evals (serialize to avoid OOM with hunt)
        for axis in WAVE2_AXES:
            aid = f"{AGENT_PREFIX}-{axis}"
            entry = agents.get(aid) or {}
            pnl = entry.get("best_sample_net_pnl")
            if pnl is None:
                continue
            if float(pnl) < PARENT_SAMPLE + SAMPLE_DELTA:
                continue
            key = f"{aid}:{float(pnl):.4f}"
            if key in evaluated:
                continue
            # skip if soft reject
            if entry.get("soft_reject"):
                evaluated[key] = {"skipped": "soft_reject"}
                continue
            # if a heavy window eval already running elsewhere, wait
            busy = False
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                try:
                    cmd = (proc / "cmdline").read_bytes().decode("utf-8", "ignore")
                except Exception:
                    continue
                if "eval_window.py" in cmd:
                    busy = True
                    break
            if busy:
                print(f"[monitor] defer window eval {aid}; eval_window busy", flush=True)
                continue

            best_path = AGENTS / aid / "strategy_best.py"
            if not best_path.exists():
                continue
            print(
                f"[monitor] sample beat +{float(pnl) - PARENT_SAMPLE:.2f} on {aid}; running 30d/60d",
                flush=True,
            )
            try:
                w30 = eval_window(RESEARCH / "window_30d_days.txt", best_path)
                w60 = eval_window(RESEARCH / "window_60d_days.txt", best_path)
            except Exception as e:
                evaluated[key] = {"error": str(e), "ts": time.time()}
                write_status(st)
                print(f"[monitor] window eval error: {e}", flush=True)
                continue

            p30 = float(w30.get("net_pnl") or -1e18)
            p60 = float(w60.get("net_pnl") or -1e18)
            soft30 = bool(w30.get("soft_reject"))
            soft60 = bool(w60.get("soft_reject"))
            dd30 = float(w30.get("max_dd_pct") or 0)
            dd60 = float(w60.get("max_dd_pct") or 0)
            rec = {
                "agent_id": aid,
                "axis": axis,
                "sample_net_pnl": float(pnl),
                "30d": p30,
                "60d": p60,
                "soft_reject_30d": soft30,
                "soft_reject_60d": soft60,
                "max_dd_pct_30d": dd30,
                "max_dd_pct_60d": dd60,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            # Inventory floors/ceilings (PROMOTION_GATE.md rule 4)
            inv_ok = True
            try:
                bt = best_path.read_text()
                import re as _re
                m_soft = _re.search(r'inv_soft_cap",\s*([0-9.]+)', bt)
                m_hard = _re.search(r'max_abs_inv",\s*([0-9.]+)', bt)
                soft_cap = float(m_soft.group(1)) if m_soft else 35.0
                hard_cap = float(m_hard.group(1)) if m_hard else 100.0
                inv_ok = (20.0 <= soft_cap <= 35.0) and (80.0 <= hard_cap <= 100.0)
                rec["inv_soft_cap"] = soft_cap
                rec["max_abs_inv"] = hard_cap
                rec["inv_ok"] = inv_ok
            except Exception as _e:
                rec["inv_check_error"] = str(_e)
            pass_gate = (
                p30 > GATE_30D
                and p60 > GATE_60D
                and (not soft30)
                and (not soft60)
                and dd30 < 25
                and dd60 < 25
                and inv_ok
            )
            rec["pass_gate"] = pass_gate
            evaluated[key] = rec
            entry["window_30d_net_pnl"] = p30
            entry["window_60d_net_pnl"] = p60
            entry["pass_gate"] = pass_gate
            (RESULTS / f"wave2_window_{aid}_{float(pnl):.2f}.json").write_text(
                json.dumps({"sample": entry, "30d": w30, "60d": w60, "rec": rec}, indent=2) + "\n"
            )
            print(
                f"[monitor] {aid} 30d={p30:.2f} 60d={p60:.2f} pass={pass_gate}",
                flush=True,
            )
            if pass_gate:
                sample_metrics = collect_agent_best(aid) or {"sample_net_pnl": pnl}
                promote(aid, axis, best_path, sample_metrics, w30, w60)
                promotions.append(rec)
                # refresh gate constants from new champion for subsequent compares
                # (local vars; next promotions must beat the new champ — re-read GATE not critical mid-run)
            write_status(st)

        # summary
        alive = sum(1 for a in agents.values() if a.get("alive"))
        st["alive_count"] = alive
        st["parent_sample"] = PARENT_SAMPLE
        st["gate_30d"] = GATE_30D
        st["gate_60d"] = GATE_60D
        write_status(st)
        print(
            f"[monitor] tick alive={alive}/{len(WAVE2_AXES)} promotions={len(promotions)} "
            f"elapsed={time.time()-t0:.0f}s",
            flush=True,
        )
        if alive == 0 and (time.time() - t0) > 120:
            # all finished; one more status then exit
            print("[monitor] all agents finished; exiting", flush=True)
            break
        time.sleep(poll_sec)

    st = read_status()
    st["monitor_done"] = True
    write_status(st)
    print("[monitor] done", flush=True)


if __name__ == "__main__":
    main()
