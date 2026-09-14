#!/usr/bin/env python3
"""Re-score wave3 optimistic winners under --liveish. Promote only if liveish 30d+60d beat pool100."""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
RESULTS = ROOT / "results"
STATUS = RESULTS / "swarm_wave2_status.json"
GATE_MD = RESEARCH / "PROMOTION_GATE.md"
FINDINGS = RESEARCH / "shared_findings.json"
DIGEST = RESULTS / "overnight_digest.md"
PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)

LIVEISH_SAMPLE_GATE = 528.35
LIVEISH_30D_GATE = 432.94
# 60d liveish of official pool100 measured on first run (or from status)
LIVEISH_60D_GATE = None  # filled after pool100 60d

CANDIDATES = [
    # robustness-first; skip two_sided (inv_soft=80)
    ("wave3-cancel_on_mid_move", "cancel_on_mid_move"),
    ("wave3-pull_size_after_adverse_fill", "pull_size_after_adverse_fill"),
    ("wave3-pause_after_fill", "pause_after_fill"),
    ("wave3-free_explore", "free_explore"),
    ("wave3-skew_aggressive", "skew_aggressive"),
    ("wave3-near_mid_size", "near_mid_size"),
    ("wave3-shrink_size", "shrink_size"),
]


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


def read_status() -> dict:
    if STATUS.exists():
        return json.loads(STATUS.read_text())
    return {}


def write_status(st: dict) -> None:
    st["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    STATUS.write_text(json.dumps(st, indent=2) + "\n")


def parse_json_out(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def eval_sample_liveish(strategy: Path) -> dict:
    cp = subprocess.run(
        [str(PY), str(ROOT / "scripts" / "eval_sample.py"),
         "--strategy-module", str(strategy), "--liveish"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"eval_sample --liveish rc={cp.returncode}: {cp.stderr or cp.stdout}")
    return parse_json_out(cp.stdout)


def eval_window_busy() -> bool:
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes().decode("utf-8", "ignore")
        except Exception:
            continue
        if "eval_window.py" in cmd:
            return True
    return False


def eval_window_liveish(days_file: Path, strategy: Path) -> dict:
    # wait if other window evals running (OOM)
    while eval_window_busy():
        print(f"[liveish] wait for eval_window slot before {days_file.name} {strategy}", flush=True)
        time.sleep(30)
    cp = subprocess.run(
        [str(PY), str(ROOT / "scripts" / "eval_window.py"),
         "--days-file", str(days_file),
         "--strategy-module", str(strategy),
         "--liveish"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"eval_window --liveish rc={cp.returncode}: {cp.stderr or cp.stdout}")
    return parse_json_out(cp.stdout)


def inv_ok(strategy: Path) -> tuple[bool, float, float]:
    bt = strategy.read_text()
    m_soft = re.search(r'inv_soft_cap",\s*([0-9.]+)', bt)
    m_hard = re.search(r'max_abs_inv",\s*([0-9.]+)', bt)
    soft = float(m_soft.group(1)) if m_soft else 35.0
    hard = float(m_hard.group(1)) if m_hard else 100.0
    ok = (20.0 <= soft <= 35.0) and (80.0 <= hard <= 100.0)
    return ok, soft, hard


def promote(aid: str, axis: str, best_path: Path, sample: dict, w30: dict, w60: dict) -> None:
    lock = RESULTS / "champion_promote.lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            label = f"liveish_{axis}_{ts}"
            dest = RESEARCH / "champions" / f"strategy_{label}.py"
            shutil.copy2(best_path, dest)
            for target in [
                RESEARCH / "champions" / "strategy_current_best.py",
                RESEARCH / "champions" / "strategy_pool100.py",
                ROOT / "strategy.py",
            ]:
                shutil.copy2(best_path, target)
            sp = float(sample.get("sample_net_pnl") or sample.get("net_pnl") or 0)
            p30 = float(w30.get("net_pnl") or 0)
            p60 = float(w60.get("net_pnl") or 0)
            GATE_MD.write_text(
                f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish-gated, axis `{axis}`, parent pool100)
Files: `research/champions/strategy_pool100.py` = `strategy_current_best.py` = root `strategy.py`
Snapshot: `{dest.name}`
Promoted {ts} after **liveish** 30d+60d beat pool100 liveish.

| Window | Optimistic (legacy) | Liveish to beat |
|--------|--------------------:|----------------:|
| 12d sample | (see candidate) | **{sp:.2f}** |
| 30d | (see candidate) | **{p30:.2f}** |
| ~60d | (see candidate) | **{p60:.2f}** |

## Rules
1. Do **not** promote for beating older champions only.
2. Optimistic 30d/60d wins are **not sufficient**.
3. To replace champion: **both liveish-30d and liveish-60d** must exceed the liveish column, soft_reject false, max_dd_pct < 25.
4. Never overwrite `strategy_current_best.py` unless that liveish gate passes.
5. Inventory soft/hard caps must remain defensive (soft ≤35, hard ≤100; soft ≥20 floor).
6. See `research/LIVE_REALISM.md`.
"""
            )
            promo = {
                "job": "swarm_liveish_promotion",
                "label": label,
                "agent_id": aid,
                "axis": axis,
                "liveish": True,
                "windows": {"sample": sample, "30d": w30, "60d": w60},
                "gate_beaten_liveish": {"30d": LIVEISH_30D_GATE, "60d": LIVEISH_60D_GATE},
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            (RESULTS / f"promotion_{label}.json").write_text(json.dumps(promo, indent=2) + "\n")

            def mut(data: dict) -> dict:
                data = data or {}
                data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                findings = data.setdefault("findings", [])
                findings.append({
                    "ts": data["updated_at"], "agent_id": aid, "axis": axis,
                    "event": "promoted_liveish", "sample_net_pnl": sp,
                    "liveish_30d": p30, "liveish_60d": p60, "label": label,
                })
                data["findings"] = findings[-200:]
                data["current_champion"] = {
                    "label": label, "liveish": True, "sample_net_pnl": sp,
                    "30d": p30, "60d": p60,
                    "path": "research/champions/strategy_current_best.py",
                }
                return data

            locked_json_update(FINDINGS, mut)
            line = (
                f"\n## LIVEISH PROMOTION {ts}\n"
                f"- Agent `{aid}` axis `{axis}`\n"
                f"- liveish sample {sp:.2f} / 30d {p30:.2f} / 60d {p60:.2f}\n"
                f"- beat pool100 liveish 30d>{LIVEISH_30D_GATE} 60d>{LIVEISH_60D_GATE}\n"
            )
            if DIGEST.exists():
                DIGEST.write_text(DIGEST.read_text() + line)
            else:
                DIGEST.write_text("# Overnight digest\n" + line)
            print(f"[liveish] PROMOTED {aid} -> {label}", flush=True)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def main() -> None:
    global LIVEISH_60D_GATE
    print("[liveish] rescore start", flush=True)
    st = read_status()
    st["liveish_mode"] = True
    st["liveish_sample_gate"] = LIVEISH_SAMPLE_GATE
    st["liveish_30d_gate"] = LIVEISH_30D_GATE
    st["parent"] = "pool100"
    st["note"] = (
        "Optimistic cancel_mid promo VOID. Champion restored to pool100. "
        "Promotions require liveish 30d+60d vs pool100 (sample 528.35 / 30d 432.94). "
        "Attach: tail -f results/swarm_liveish_rescore.log ; "
        "axes: tail -f research/agents/wave3-<axis>/run.log"
    )
    live = st.setdefault("liveish_scores", {})

    # 1) measure official pool100 liveish 60d (for gate) when slot free
    gate60_path = RESULTS / "liveish_pool100_60d.json"
    if gate60_path.exists():
        g = json.loads(gate60_path.read_text())
        LIVEISH_60D_GATE = float(g.get("net_pnl") or 0)
        print(f"[liveish] loaded pool100 60d liveish={LIVEISH_60D_GATE:.2f}", flush=True)
    else:
        print("[liveish] measuring official pool100 liveish 60d...", flush=True)
        try:
            w60c = eval_window_liveish(
                RESEARCH / "window_60d_days.txt",
                RESEARCH / "champions" / "strategy_pool100.py",
            )
            gate60_path.write_text(json.dumps(w60c, indent=2) + "\n")
            LIVEISH_60D_GATE = float(w60c.get("net_pnl") or 0)
            print(f"[liveish] pool100 60d liveish={LIVEISH_60D_GATE:.4f}", flush=True)
        except Exception as e:
            print(f"[liveish] pool100 60d error: {e}", flush=True)
            LIVEISH_60D_GATE = None
    st["liveish_60d_gate"] = LIVEISH_60D_GATE
    write_status(st)

    # 2) liveish sample all candidates
    for aid, axis in CANDIDATES:
        best = RESEARCH / "agents" / aid / "strategy_best.py"
        if not best.exists():
            continue
        ok, soft, hard = inv_ok(best)
        rec = live.setdefault(aid, {"axis": axis})
        rec["inv_ok"] = ok
        rec["inv_soft_cap"] = soft
        rec["max_abs_inv"] = hard
        if not ok:
            rec["skipped"] = f"inv caps soft={soft} hard={hard}"
            print(f"[liveish] SKIP {aid} inv soft={soft} hard={hard}", flush=True)
            write_status(st)
            continue
        # adopt precomputed sample file if present
        pre = RESULTS / f"liveish_sample_{aid}.json"
        if rec.get("sample_liveish") is None and pre.exists() and pre.stat().st_size > 10:
            try:
                m = json.loads(pre.read_text())
                if m.get("liveish") and m.get("sample_net_pnl") is not None:
                    rec["sample_liveish"] = float(m.get("sample_net_pnl") or m.get("net_pnl") or 0)
                    rec["sample_max_dd_pct"] = m.get("max_dd_pct")
                    rec["sample_soft_reject"] = m.get("soft_reject")
                    rec["sample_metrics"] = m
                    print(f"[liveish] loaded precomputed sample {aid}={rec['sample_liveish']:.2f}", flush=True)
                    write_status(st)
            except Exception as e:
                print(f"[liveish] bad precompute {aid}: {e}", flush=True)
        if rec.get("sample_liveish") is not None:
            print(f"[liveish] sample already scored {aid}={rec['sample_liveish']}", flush=True)
            continue
        print(f"[liveish] sample {aid}...", flush=True)
        try:
            m = eval_sample_liveish(best)
        except Exception as e:
            rec["sample_error"] = str(e)
            write_status(st)
            print(f"[liveish] sample error {aid}: {e}", flush=True)
            continue
        rec["sample_liveish"] = float(m.get("sample_net_pnl") or m.get("net_pnl") or 0)
        rec["sample_max_dd_pct"] = m.get("max_dd_pct")
        rec["sample_soft_reject"] = m.get("soft_reject")
        rec["sample_metrics"] = m
        (RESULTS / f"liveish_sample_{aid}.json").write_text(json.dumps(m, indent=2) + "\n")
        print(
            f"[liveish] {aid} sample_liveish={rec['sample_liveish']:.2f} "
            f"(gate {LIVEISH_SAMPLE_GATE}) dd={m.get('max_dd_pct')}",
            flush=True,
        )
        write_status(st)

    # 3) window eval those that beat liveish sample
    for aid, axis in CANDIDATES:
        rec = live.get(aid) or {}
        if rec.get("skipped") or rec.get("sample_liveish") is None:
            continue
        if rec.get("sample_soft_reject"):
            continue
        if float(rec["sample_liveish"]) <= LIVEISH_SAMPLE_GATE:
            rec["window_skipped"] = "liveish sample did not beat pool100"
            write_status(st)
            continue
        best = RESEARCH / "agents" / aid / "strategy_best.py"
        if rec.get("liveish_30d") is None:
            print(f"[liveish] 30d {aid} (sample {rec['sample_liveish']:.2f})...", flush=True)
            try:
                w30 = eval_window_liveish(RESEARCH / "window_30d_days.txt", best)
                rec["liveish_30d"] = float(w30.get("net_pnl") or 0)
                rec["liveish_30d_dd"] = w30.get("max_dd_pct")
                rec["liveish_30d_soft"] = w30.get("soft_reject")
                rec["liveish_30d_metrics"] = w30
                print(f"[liveish] {aid} 30d={rec['liveish_30d']:.2f} gate={LIVEISH_30D_GATE}", flush=True)
            except Exception as e:
                rec["liveish_30d_error"] = str(e)
                write_status(st)
                print(f"[liveish] 30d error {aid}: {e}", flush=True)
                continue
            write_status(st)
        if rec.get("liveish_30d") is None:
            continue
        if rec.get("liveish_30d_soft") or float(rec["liveish_30d"]) <= LIVEISH_30D_GATE:
            rec["pass_liveish_gate"] = False
            rec["fail_reason"] = "30d liveish did not beat pool100"
            write_status(st)
            continue
        if rec.get("liveish_60d") is None:
            print(f"[liveish] 60d {aid}...", flush=True)
            try:
                w60 = eval_window_liveish(RESEARCH / "window_60d_days.txt", best)
                rec["liveish_60d"] = float(w60.get("net_pnl") or 0)
                rec["liveish_60d_dd"] = w60.get("max_dd_pct")
                rec["liveish_60d_soft"] = w60.get("soft_reject")
                rec["liveish_60d_metrics"] = w60
                print(f"[liveish] {aid} 60d={rec['liveish_60d']:.2f} gate={LIVEISH_60D_GATE}", flush=True)
            except Exception as e:
                rec["liveish_60d_error"] = str(e)
                write_status(st)
                print(f"[liveish] 60d error {aid}: {e}", flush=True)
                continue
            write_status(st)
        g60 = LIVEISH_60D_GATE if LIVEISH_60D_GATE is not None else -1e18
        pass_gate = (
            float(rec["liveish_30d"]) > LIVEISH_30D_GATE
            and float(rec.get("liveish_60d") or -1e18) > g60
            and not rec.get("liveish_30d_soft")
            and not rec.get("liveish_60d_soft")
            and float(rec.get("liveish_30d_dd") or 0) < 25
            and float(rec.get("liveish_60d_dd") or 0) < 25
            and rec.get("inv_ok")
        )
        rec["pass_liveish_gate"] = pass_gate
        write_status(st)
        if pass_gate:
            promote(
                aid, axis, best,
                rec.get("sample_metrics") or {"sample_net_pnl": rec["sample_liveish"]},
                rec.get("liveish_30d_metrics") or {"net_pnl": rec["liveish_30d"]},
                rec.get("liveish_60d_metrics") or {"net_pnl": rec["liveish_60d"]},
            )
            st.setdefault("promotions", []).append({"agent_id": aid, "liveish": True})
            write_status(st)

    st["liveish_rescore_done"] = True
    write_status(st)
    print("[liveish] rescore done", flush=True)


if __name__ == "__main__":
    main()
