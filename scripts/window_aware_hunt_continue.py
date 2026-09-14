#!/usr/bin/env python3
"""Continue window-aware hunt from NEW champion (pool150). Append to results."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research/champions/strategy_pool150.py"
AGENT_DIR = ROOT / "research/agents/window-aware-hunt"
STRAT = AGENT_DIR / "strategy.py"
OUT = ROOT / "results/window_aware_hunt.json"
PY = str(ROOT / ".venv/bin/python")

CHAMP_30 = 2083.3103
CHAMP_60 = 1913.9283
SAMPLE_MIN = 1000.0

BASE = {
    "spread_frac": 0.6676,
    "skew_bps_per_share": 0.35,
    "size_mult": 1.291,
    "max_abs_inv": 100.0,
    "inv_soft_cap": 35.0,
    "inv_pause_ticks": 8,
    "min_daily_reward_pool": 150.0,
    "pull_size_mult": 0.5,
}

# Remaining single-knob mutations (~24) from new parent; skip pool=150 (already champ)
MUTATIONS = [
    ("min_daily_reward_pool", 125.0),
    ("min_daily_reward_pool", 175.0),
    ("min_daily_reward_pool", 200.0),  # regress check toward old
    ("min_daily_reward_pool", 225.0),
    ("spread_frac", 0.62),
    ("spread_frac", 0.64),
    ("spread_frac", 0.65),
    ("spread_frac", 0.69),
    ("spread_frac", 0.70),
    ("spread_frac", 0.72),
    ("size_mult", 1.15),
    ("size_mult", 1.20),
    ("size_mult", 1.25),
    ("size_mult", 1.32),
    ("size_mult", 1.35),
    ("skew_bps_per_share", 0.25),
    ("skew_bps_per_share", 0.28),
    ("skew_bps_per_share", 0.32),
    ("skew_bps_per_share", 0.38),
    ("skew_bps_per_share", 0.40),
    ("inv_pause_ticks", 6),
    ("inv_pause_ticks", 10),
    ("inv_pause_ticks", 12),
    ("pull_size_mult", 0.35),
    ("pull_size_mult", 0.40),
    ("pull_size_mult", 0.60),
]


def _patch_file(path: Path, knob: str, value) -> None:
    text = path.read_text()
    if isinstance(value, float):
        new_default = f"{value}"
        if "." not in new_default:
            new_default = f"{value}.0"
    else:
        new_default = str(int(value))

    if knob == "inv_pause_ticks":
        pat = re.compile(
            r'(self\.inv_pause_ticks\s*=\s*int\(cfg\.get\("inv_pause_ticks",\s*)(\d+)(\))'
        )
        text2, n = pat.subn(rf"\g<1>{int(value)}\3", text, count=1)
    else:
        pat = re.compile(
            rf'(self\.{re.escape(knob)}\s*=\s*float\(cfg\.get\("{re.escape(knob)}",\s*)([^)]+)(\))'
        )
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
    if n != 1:
        raise RuntimeError(f"failed to patch {knob}={value} (n={n})")
    path.write_text(text2)


def run_json(cmd: list[str], timeout: int = 600) -> dict:
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {"error": "nonzero_exit", "code": r.returncode, "stderr": (r.stderr or "")[-2000:], "stdout": (r.stdout or "")[-2000:]}
    out = r.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        i = out.rfind("{")
        if i < 0:
            return {"error": "no_json", "stdout": out[-2000:]}
        return json.loads(out[i:])


def eval_sample() -> dict:
    return run_json([PY, "scripts/eval_sample.py", "--strategy-module", str(STRAT)], timeout=180)


def eval_window(days_file: str) -> dict:
    return run_json(
        [PY, "scripts/eval_window.py", "--days-file", days_file, "--strategy-module", str(STRAT)],
        timeout=900,
    )


def within_2pct(val: float, champ: float) -> bool:
    return val >= champ * 0.98


def gate_keep(n30: float, n60: float) -> tuple[bool, str]:
    if n30 >= CHAMP_30 and n60 >= CHAMP_60:
        return True, "both_ge_champ"
    if n30 > CHAMP_30 and within_2pct(n60, CHAMP_60):
        return True, "30d_better_60d_within_2pct"
    if n60 > CHAMP_60 and within_2pct(n30, CHAMP_30):
        return True, "60d_better_30d_within_2pct"
    return False, "fail_window_gate"


def full_promote(n30: float, n60: float, soft30: bool, soft60: bool) -> bool:
    return n30 > CHAMP_30 and n60 > CHAMP_60 and not soft30 and not soft60

def gate_keep_dyn(n30: float, n60: float, c30: float, c60: float) -> tuple[bool, str]:
    if n30 >= c30 and n60 >= c60:
        return True, "both_ge_champ"
    if n30 > c30 and n60 >= c60 * 0.98:
        return True, "30d_better_60d_within_2pct"
    if n60 > c60 and n30 >= c30 * 0.98:
        return True, "60d_better_30d_within_2pct"
    return False, "fail_window_gate"


def full_promote_dyn(n30, n60, soft30, soft60, c30, c60) -> bool:
    return n30 > c30 and n60 > c60 and not soft30 and not soft60



def main() -> None:
    state = json.loads(OUT.read_text()) if OUT.exists() else {"trials": []}
    trials = state.setdefault("trials", [])
    champ_ref = {"30": CHAMP_30, "60": CHAMP_60}
    parent_ref = {"path": PARENT}
    state["phase2"] = {
        "parent": "strategy_pool150.py",
        "champ_30": champ_ref["30"],
        "champ_60": champ_ref["60"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "n_planned": len(MUTATIONS),
    }
    best = state.get("best")
    promoted = False
    t_start = time.time()
    try_offset = max((t.get("try", 0) for t in trials), default=0)

    for i, (knob, value) in enumerate(MUTATIONS, 1):
        try_n = try_offset + i
        print(f"\n=== TRY {try_n} (phase2 {i}/{len(MUTATIONS)}): {knob}={value} ===", flush=True)
        trial = {
            "try": try_n,
            "phase": 2,
            "knob": knob,
            "value": value,
            "parent_value": BASE.get(knob),
            "parent_label": "pool150",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            shutil.copy2(parent_ref["path"], STRAT)
            # inline patch after copy from live parent
            _patch_file(STRAT, knob, value)
        except Exception as e:
            trial["error"] = f"patch_failed: {e}"
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue

        s = eval_sample()
        if "sample_net_pnl" not in s:
            trial["error"] = s
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue

        sample_net = float(s.get("sample_net_pnl") or 0)
        trial["sample_net_pnl"] = sample_net
        trial["sample_max_dd_pct"] = s.get("max_dd_pct")
        trial["sample_soft_reject"] = s.get("soft_reject")
        trial["sample_n_fills"] = s.get("n_fills")
        trial["sample_elapsed_sec"] = s.get("elapsed_sec")
        print(f"  sample={sample_net:.2f} dd={s.get('max_dd_pct')}", flush=True)

        if sample_net < SAMPLE_MIN or s.get("soft_reject"):
            trial["status"] = "discard_sample"
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue

        trial["status"] = "eval_windows"
        print("  sample>=1000 → eval 30d+60d", flush=True)
        w30 = eval_window("research/window_30d_days.txt")
        w60 = eval_window("research/window_60d_days.txt")
        if "window_net_pnl" not in w30:
            trial["error_30d"] = w30
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue
        if "window_net_pnl" not in w60:
            trial["error_60d"] = w60
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue

        n30 = float(w30["window_net_pnl"])
        n60 = float(w60["window_net_pnl"])
        soft30 = bool(w30.get("soft_reject"))
        soft60 = bool(w60.get("soft_reject"))
        trial["net_30d"] = n30
        trial["net_60d"] = n60
        trial["dd_30d"] = w30.get("max_dd_pct")
        trial["dd_60d"] = w60.get("max_dd_pct")
        trial["soft_30d"] = soft30
        trial["soft_60d"] = soft60
        trial["delta_30d"] = round(n30 - champ_ref['30'], 4)
        trial["delta_60d"] = round(n60 - champ_ref['60'], 4)
        keep, reason = gate_keep_dyn(n30, n60, champ_ref['30'], champ_ref['60'])
        trial["keep"] = keep
        trial["keep_reason"] = reason
        trial["promote_eligible"] = full_promote_dyn(n30, n60, soft30, soft60, champ_ref['30'], champ_ref['60'])
        print(
            f"  30d={n30:.2f} (d{trial['delta_30d']:+.2f})  "
            f"60d={n60:.2f} (d{trial['delta_60d']:+.2f})  "
            f"keep={keep} ({reason}) promote={trial['promote_eligible']}",
            flush=True,
        )
        score = (n30 - champ_ref['30']) + (n60 - champ_ref['60'])
        trial["score_vs_champ"] = round(score, 4)
        if best is None or score > best.get("score_vs_champ", -1e18):
            # Only update best if this is vs current phase champ; keep absolute best windows too
            best = dict(trial)
            shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py")
            state["best_phase2"] = best

        if trial["promote_eligible"]:
            for dest in [
                ROOT / "research/champions/strategy_pool150.py",
                ROOT / "research/champions/strategy_hybrid_spread_size.py",
                ROOT / "research/champions/strategy_current_best.py",
                ROOT / "strategy.py",
            ]:
                shutil.copy2(STRAT, dest)
            shutil.copy2(STRAT, AGENT_DIR / "strategy_promoted.py")
            label = f"{knob}_{value}".replace(".", "p")
            shutil.copy2(STRAT, ROOT / f"research/champions/strategy_pool150_{label}.py")
            state["promoted"] = True
            state["promoted_trial"] = trial
            promoted = True
            trial["status"] = "PROMOTED"
            print("  *** FULL GATE PASS — PROMOTED ***", flush=True)
            # update live champ thresholds for subsequent tries
            champ_ref["30"] = n30
            champ_ref["60"] = n60
            parent_ref["path"] = ROOT / "research/champions/strategy_current_best.py"
            BASE[knob] = value
        elif keep:
            trial["status"] = "keep_near_champ"
        else:
            trial["status"] = "fail_windows"

        trials.append(trial)
        OUT.write_text(json.dumps(state, indent=2, default=str))

    if not promoted:
        shutil.copy2(parent_ref['path'], STRAT)

    state["phase2"]["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["phase2"]["elapsed_sec"] = round(time.time() - t_start, 1)
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["n_tried"] = len(trials)
    state["n_sample_pass"] = sum(
        1 for t in trials if t.get("sample_net_pnl", 0) >= SAMPLE_MIN and not t.get("sample_soft_reject")
    )
    state["n_window_eval"] = sum(1 for t in trials if "net_30d" in t)
    state["n_keep"] = sum(1 for t in trials if t.get("keep"))
    # vs ORIGINAL hybrid
    HYB_30, HYB_60 = 1938.76, 1581.22
    state["anything_beat_hybrid_windows"] = any(
        t.get("net_30d") is not None
        and t.get("net_60d") is not None
        and t["net_30d"] > HYB_30
        and t["net_60d"] > HYB_60
        for t in trials
    )
    state["final_champ_30"] = champ_ref["30"]
    state["final_champ_60"] = champ_ref["60"]
    OUT.write_text(json.dumps(state, indent=2, default=str))
    print("\n=== PHASE2 HUNT DONE ===", flush=True)
    print(json.dumps({
        "n_tried_total": len(trials),
        "phase2_elapsed": state["phase2"]["elapsed_sec"],
        "promoted_again": promoted,
        "anything_beat_hybrid_windows": state["anything_beat_hybrid_windows"],
        "final_champ_30": champ_ref["30"],
        "final_champ_60": champ_ref["60"],
        "best_phase2": state.get("best_phase2"),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
