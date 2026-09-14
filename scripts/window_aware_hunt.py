#!/usr/bin/env python3
"""Window-aware overnight hunt: mutate ONE knob from hybrid champion; gate on 30d+60d."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research/champions/strategy_hybrid_spread_size.py"
AGENT_DIR = ROOT / "research/agents/window-aware-hunt"
STRAT = AGENT_DIR / "strategy.py"
OUT = ROOT / "results/window_aware_hunt.json"
PY = str(ROOT / ".venv/bin/python")

CHAMP_30 = 1938.76
CHAMP_60 = 1581.22
SAMPLE_MIN = 1000.0  # discard below this before windows

# Champion baseline knobs (for reporting)
BASE = {
    "spread_frac": 0.6676,
    "skew_bps_per_share": 0.35,
    "size_mult": 1.291,
    "max_abs_inv": 100.0,
    "inv_soft_cap": 35.0,
    "inv_pause_ticks": 8,
    "min_daily_reward_pool": 200.0,
    "pull_size_mult": 0.5,
}

# ~25 single-knob mutations in preferred ranges
# Do NOT raise max_abs_inv > 100 or soft cap > 35
MUTATIONS = [
    ("min_daily_reward_pool", 150.0),
    ("min_daily_reward_pool", 175.0),
    ("min_daily_reward_pool", 225.0),
    ("min_daily_reward_pool", 250.0),
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
    ("pull_size_mult", 0.70),
]


def patch_one(knob: str, value) -> None:
    shutil.copy2(PARENT, STRAT)
    text = STRAT.read_text()
    # Match cfg.get("knob", DEFAULT)
    if isinstance(value, float):
        # preserve float formatting
        if value == int(value) and knob in ("max_abs_inv", "inv_soft_cap", "min_daily_reward_pool"):
            new_default = f"{float(value)}"
        else:
            new_default = repr(float(value)) if abs(value) < 1 or value != int(value) else f"{float(value)}"
            # Prefer clean decimals
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
    STRAT.write_text(text2)


def run_json(cmd: list[str], timeout: int = 600) -> dict:
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {"error": "nonzero_exit", "code": r.returncode, "stderr": r.stderr[-2000:], "stdout": r.stdout[-2000:]}
    # last JSON object in stdout
    out = r.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # find last { ... }
        i = out.rfind("{")
        if i < 0:
            return {"error": "no_json", "stdout": out[-2000:], "stderr": r.stderr[-1000:]}
        return json.loads(out[i:])


def eval_sample() -> dict:
    return run_json(
        [PY, "scripts/eval_sample.py", "--strategy-module", str(STRAT)],
        timeout=180,
    )


def eval_window(days_file: str) -> dict:
    return run_json(
        [
            PY,
            "scripts/eval_window.py",
            "--days-file",
            days_file,
            "--strategy-module",
            str(STRAT),
        ],
        timeout=900,
    )


def within_2pct(val: float, champ: float) -> bool:
    return val >= champ * 0.98


def gate_keep(n30: float, n60: float) -> tuple[bool, str]:
    """Keep if BOTH >= champ, OR one strictly better and other within 2%."""
    both_ge = n30 >= CHAMP_30 and n60 >= CHAMP_60
    if both_ge:
        return True, "both_ge_champ"
    one_better_30 = n30 > CHAMP_30 and within_2pct(n60, CHAMP_60)
    one_better_60 = n60 > CHAMP_60 and within_2pct(n30, CHAMP_30)
    if one_better_30:
        return True, "30d_better_60d_within_2pct"
    if one_better_60:
        return True, "60d_better_30d_within_2pct"
    return False, "fail_window_gate"


def full_promote(n30: float, n60: float, soft30: bool, soft60: bool) -> bool:
    return (
        n30 > CHAMP_30
        and n60 > CHAMP_60
        and not soft30
        and not soft60
    )


def main() -> None:
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    trials = []
    best = None
    promoted = False
    t_start = time.time()

    state = {
        "job": "window_aware_hunt",
        "parent": str(PARENT.relative_to(ROOT)),
        "champion": {
            "label": "hybrid_spread_size",
            "sample_ref": 1086.47,
            "net_30d": CHAMP_30,
            "net_60d": CHAMP_60,
            "knobs": BASE,
        },
        "protocol": {
            "sample_discard_below": SAMPLE_MIN,
            "keep_rule": "both windows >= champ OR one strictly better and other within 2%",
            "promote_rule": "both windows STRICTLY > champ, soft_reject false",
            "max_abs_inv_cap": 100,
            "inv_soft_cap_cap": 35,
            "n_planned": len(MUTATIONS),
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "trials": trials,
        "best": None,
        "promoted": False,
    }

    for i, (knob, value) in enumerate(MUTATIONS, 1):
        print(f"\n=== TRY {i}/{len(MUTATIONS)}: {knob}={value} ===", flush=True)
        trial = {
            "try": i,
            "knob": knob,
            "value": value,
            "parent_value": BASE.get(knob),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            patch_one(knob, value)
        except Exception as e:
            trial["error"] = f"patch_failed: {e}"
            trials.append(trial)
            _save(state)
            continue

        s = eval_sample()
        if "error" in s and "sample_net_pnl" not in s:
            trial["error"] = s
            trials.append(trial)
            _save(state)
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
            _save(state)
            continue

        trial["status"] = "eval_windows"
        print("  sample>=1000 → eval 30d+60d", flush=True)
        w30 = eval_window("research/window_30d_days.txt")
        w60 = eval_window("research/window_60d_days.txt")
        if "error" in w30 and "window_net_pnl" not in w30:
            trial["error_30d"] = w30
            trials.append(trial)
            _save(state)
            continue
        if "error" in w60 and "window_net_pnl" not in w60:
            trial["error_60d"] = w60
            trials.append(trial)
            _save(state)
            continue

        n30 = float(w30.get("window_net_pnl") or 0)
        n60 = float(w60.get("window_net_pnl") or 0)
        soft30 = bool(w30.get("soft_reject"))
        soft60 = bool(w60.get("soft_reject"))
        trial["net_30d"] = n30
        trial["net_60d"] = n60
        trial["dd_30d"] = w30.get("max_dd_pct")
        trial["dd_60d"] = w60.get("max_dd_pct")
        trial["soft_30d"] = soft30
        trial["soft_60d"] = soft60
        trial["delta_30d"] = round(n30 - CHAMP_30, 4)
        trial["delta_60d"] = round(n60 - CHAMP_60, 4)
        keep, reason = gate_keep(n30, n60)
        trial["keep"] = keep
        trial["keep_reason"] = reason
        trial["promote_eligible"] = full_promote(n30, n60, soft30, soft60)
        print(
            f"  30d={n30:.2f} (d{trial['delta_30d']:+.2f})  "
            f"60d={n60:.2f} (d{trial['delta_60d']:+.2f})  "
            f"keep={keep} ({reason}) promote={trial['promote_eligible']}",
            flush=True,
        )

        score = (n30 - CHAMP_30) + (n60 - CHAMP_60)
        trial["score_vs_champ"] = round(score, 4)
        if best is None or score > best.get("score_vs_champ", -1e18):
            best = dict(trial)
            # snapshot strategy of best
            shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py")
            state["best"] = best

        if trial["promote_eligible"]:
            # promote
            champ_path = ROOT / "research/champions/strategy_hybrid_spread_size.py"
            shutil.copy2(STRAT, champ_path)
            shutil.copy2(STRAT, ROOT / "research/champions/strategy_current_best.py")
            shutil.copy2(STRAT, ROOT / "strategy.py")
            shutil.copy2(STRAT, AGENT_DIR / "strategy_promoted.py")
            state["promoted"] = True
            state["promoted_trial"] = trial
            promoted = True
            trial["status"] = "PROMOTED"
            print("  *** FULL GATE PASS — PROMOTED ***", flush=True)
        elif keep:
            trial["status"] = "keep_near_champ"
        else:
            trial["status"] = "fail_windows"

        trials.append(trial)
        _save(state)

        if promoted:
            break

    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["elapsed_sec"] = round(time.time() - t_start, 1)
    state["n_tried"] = len(trials)
    state["n_sample_pass"] = sum(1 for t in trials if t.get("sample_net_pnl", 0) >= SAMPLE_MIN and not t.get("sample_soft_reject"))
    state["n_window_eval"] = sum(1 for t in trials if "net_30d" in t)
    state["n_keep"] = sum(1 for t in trials if t.get("keep"))
    state["anything_beat_hybrid_windows"] = bool(
        any(
            t.get("promote_eligible")
            or (
                t.get("net_30d") is not None
                and t.get("net_60d") is not None
                and t["net_30d"] > CHAMP_30
                and t["net_60d"] > CHAMP_60
            )
            for t in trials
        )
    )
    # restore working strategy.py to parent if not promoted
    if not promoted:
        shutil.copy2(PARENT, STRAT)
    _save(state)
    print("\n=== HUNT DONE ===", flush=True)
    print(json.dumps({k: state[k] for k in ("n_tried", "n_sample_pass", "n_window_eval", "n_keep", "promoted", "anything_beat_hybrid_windows", "best", "elapsed_sec")}, indent=2), flush=True)


def _save(state: dict) -> None:
    OUT.write_text(json.dumps(state, indent=2, default=str))


if __name__ == "__main__":
    main()
