#!/usr/bin/env python3
"""Window-aware hunt FROM restored pool150 parent only. Never promotes unless both windows beat gate."""

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

# Authoritative restored champion gate
CHAMP_SAMPLE = 1197.56
CHAMP_30 = 2083.31
CHAMP_60 = 1913.93
SAMPLE_DISCARD = 1000.0  # skip windows below this

BASE = {
    "spread_frac": 0.6676,
    "skew_bps_per_share": 0.35,
    "size_mult": 1.291,
    "max_abs_inv": 100.0,
    "inv_soft_cap": 35.0,
    "inv_pause_ticks": 8,
    "min_daily_reward_pool": 150.0,
    "pull_size_mult": 0.5,
    "mid_move_cancel_cents": 2.0,
    "mid_move_hard_cancel_cents": 4.0,
    "mid_move_widen_mult": 1.6,
    "min_edge_vs_bbo": 0.0,
    "vol_filter": 0.0,
}

# ~25 single-knob mutations; live-realism first, then prior winners / preferred ranges
# Do NOT raise max_abs_inv > 100 or soft > 35 (tightening OK)
MUTATIONS = [
    # live-realism: tighter cancel / pause / pull
    ("mid_move_cancel_cents", 1.0),
    ("mid_move_cancel_cents", 1.5),
    ("mid_move_hard_cancel_cents", 2.5),
    ("mid_move_hard_cancel_cents", 3.0),
    ("mid_move_widen_mult", 1.8),
    ("mid_move_widen_mult", 2.0),
    ("inv_pause_ticks", 10),
    ("inv_pause_ticks", 12),
    ("inv_pause_ticks", 16),
    ("pull_size_mult", 0.35),
    ("pull_size_mult", 0.40),
    ("min_edge_vs_bbo", 0.01),
    ("min_edge_vs_bbo", 0.02),
    ("vol_filter", 0.03),
    ("vol_filter", 0.05),
    # tighter inventory (live portfolio discipline)
    ("inv_soft_cap", 25.0),
    ("inv_soft_cap", 30.0),
    ("max_abs_inv", 80.0),
    # pool / spread / size (incl. prior pool125 candidate — re-verify from clean parent)
    ("min_daily_reward_pool", 125.0),
    ("min_daily_reward_pool", 175.0),
    ("spread_frac", 0.62),
    ("spread_frac", 0.70),
    ("spread_frac", 0.72),
    ("size_mult", 1.15),
    ("size_mult", 1.20),
    ("size_mult", 1.35),
    ("skew_bps_per_share", 0.28),
    ("skew_bps_per_share", 0.40),
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
    elif knob == "mid_move_hard_cancel_cents":
        # multiline default
        pat = re.compile(
            r'(self\.mid_move_hard_cancel_cents\s*=\s*float\(\s*\n\s*cfg\.get\("mid_move_hard_cancel_cents",\s*)([^)]+)(\)\s*\n\s*\))',
            re.M,
        )
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
        if n != 1:
            pat2 = re.compile(
                r'(cfg\.get\("mid_move_hard_cancel_cents",\s*)([^)]+)(\))'
            )
            text2, n = pat2.subn(rf"\g<1>{new_default}\3", text, count=1)
    else:
        pat = re.compile(
            rf'(self\.{re.escape(knob)}\s*=\s*float\(cfg\.get\("{re.escape(knob)}",\s*)([^)]+)(\))'
        )
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
    if n != 1:
        raise RuntimeError(f"failed to patch {knob}={value} (n={n})")
    path.write_text(text2)


def run_json(cmd: list[str], timeout: int = 900) -> dict:
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {
            "error": "nonzero_exit",
            "code": r.returncode,
            "stderr": (r.stderr or "")[-2000:],
            "stdout": (r.stdout or "")[-2000:],
        }
    out = (r.stdout or "").strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        i = out.rfind("{")
        if i < 0:
            return {"error": "no_json", "stdout": out[-2000:]}
        return json.loads(out[i:])


def eval_sample() -> dict:
    return run_json([PY, "scripts/eval_sample.py", "--strategy-module", str(STRAT)], 180)


def eval_window(days_file: str) -> dict:
    return run_json(
        [PY, "scripts/eval_window.py", "--days-file", days_file, "--strategy-module", str(STRAT)],
        900,
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


def promote_eligible(sample: float, n30: float, n60: float, soft30: bool, soft60: bool, soft_s: bool) -> bool:
    return (
        sample >= CHAMP_SAMPLE
        and n30 > CHAMP_30
        and n60 > CHAMP_60
        and not soft30
        and not soft60
        and not soft_s
    )


def write_promotion(trial: dict, label: str) -> Path:
    path = ROOT / f"results/promotion_{label}.json"
    promo = {
        "job": f"COMMANDER_promotion_{label}",
        "label": label,
        "parent": "pool150",
        "strategy": f"research/champions/strategy_{label}.py",
        "knob": trial["knob"],
        "value": trial["value"],
        "parent_value": trial.get("parent_value"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gate_beaten": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "windows": {
            "sample": {
                "net_pnl": trial["sample_net_pnl"],
                "max_dd_pct": trial.get("sample_max_dd_pct"),
                "soft_reject": trial.get("sample_soft_reject"),
                "n_fills": trial.get("sample_n_fills"),
            },
            "30d": {
                "net_pnl": trial["net_30d"],
                "max_dd_pct": trial.get("dd_30d"),
                "soft_reject": trial.get("soft_30d"),
                "delta_vs_pool150": trial.get("delta_30d"),
            },
            "60d": {
                "net_pnl": trial["net_60d"],
                "max_dd_pct": trial.get("dd_60d"),
                "soft_reject": trial.get("soft_60d"),
                "delta_vs_pool150": trial.get("delta_60d"),
            },
        },
        "inv_caps": {"inv_soft_cap": "≤35", "max_abs_inv": "≤100"},
        "source_try": trial.get("try"),
    }
    path.write_text(json.dumps(promo, indent=2, default=str))
    return path


def update_promotion_gate(trial: dict, label: str) -> None:
    gate = ROOT / "research/PROMOTION_GATE.md"
    text = f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (from pool150; knob `{trial['knob']}={trial['value']}`)  
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = `strategy_hybrid_spread_size.py` = root `strategy.py`  
Prior pool150 archived as `research/champions/strategy_pool150.py` (unchanged historical snapshot if still matching prior knobs — see note).

| Window | Net PnL to beat | Max DD (champ) |
|--------|----------------:|---------------:|
| 12d sample | **{trial['sample_net_pnl']:.2f}** | {trial.get('sample_max_dd_pct')}% |
| 30d | **{trial['net_30d']:.2f}** | {trial.get('dd_30d')}% |
| ~60d | **{trial['net_60d']:.2f}** | {trial.get('dd_60d')}% |

Prior pool150 (beaten): sample 1197.56 / 30d 2083.31 / 60d 1913.93

## Rules
1. Do **not** promote for beating older champions only.
2. To replace champion: **both** 30d and 60d net_pnl must exceed the table above, soft_reject false, max_dd_pct < 25.
3. Never overwrite `strategy_current_best.py` unless that gate passes.
4. Inventory soft/hard caps must remain defensive (soft ≤35, hard ≤100; soft ≥20 floor).
5. Prefer live-realism mutations (tighter mid-move cancel, longer inv pause, lower pull_size).
"""
    gate.write_text(text)


def broadcast_finding(trial: dict, label: str) -> None:
    path = ROOT / "research/shared_findings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["current_champion"] = {
        "label": label,
        "knob": trial["knob"],
        "value": trial["value"],
        "sample_net_pnl": trial["sample_net_pnl"],
        "net_30d": trial["net_30d"],
        "net_60d": trial["net_60d"],
        "delta_30d_vs_pool150": trial.get("delta_30d"),
        "delta_60d_vs_pool150": trial.get("delta_60d"),
        "beat_pool150": True,
    }
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append(
            {
                "ts": data["updated_at"],
                "agent": "window-aware-hunt",
                "event": "promoted",
                "label": label,
                "knob": trial["knob"],
                "value": trial["value"],
                "sample": trial["sample_net_pnl"],
                "net_30d": trial["net_30d"],
                "net_60d": trial["net_60d"],
                "note": "beat restored pool150 on BOTH windows; soft_reject false; inv caps held",
            }
        )
    # also top-level hunt note
    data["window_aware_hunt"] = {
        "parent": "pool150",
        "gate_30": CHAMP_30,
        "gate_60": CHAMP_60,
        "last_promote": label,
        "updated_at": data["updated_at"],
    }
    path.write_text(json.dumps(data, indent=2, default=str))


def promote(trial: dict) -> str:
    label = f"pool150_{trial['knob']}_{str(trial['value']).replace('.', 'p')}"
    # keep pool150.py as historical snapshot of the beaten champ — only overwrite if it's still the live name
    # Write new named champion; sync current_best / hybrid / root
    named = ROOT / f"research/champions/strategy_{label}.py"
    shutil.copy2(STRAT, named)
    for dest in [
        ROOT / "research/champions/strategy_current_best.py",
        ROOT / "research/champions/strategy_hybrid_spread_size.py",
        ROOT / "strategy.py",
    ]:
        shutil.copy2(STRAT, dest)
    # Also update strategy_pool150.py ONLY if label is the new live champ naming convention?
    # Commander said: copy into champions ONLY if gate passes. Keep strategy_pool150.py as the
    # beaten baseline snapshot (do not overwrite pool150 file with new champ so history remains).
    shutil.copy2(STRAT, AGENT_DIR / "strategy_promoted.py")
    write_promotion(trial, label)
    update_promotion_gate(trial, label)
    broadcast_finding(trial, label)
    return label


def load_state() -> dict:
    if OUT.exists():
        return json.loads(OUT.read_text())
    return {"trials": []}


def main() -> None:
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    # ensure parent is pool150
    if not PARENT.exists():
        raise SystemExit(f"missing parent {PARENT}")
    shutil.copy2(PARENT, STRAT)
    shutil.copy2(PARENT, AGENT_DIR / "strategy_parent.py")

    state = load_state()
    trials = state.setdefault("trials", [])
    phase = {
        "name": "restored_pool150",
        "parent": "research/champions/strategy_pool150.py",
        "gate": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "n_planned": len(MUTATIONS),
        "note": "Commander restore: hunt only from pool150; do not trust drifted chain",
    }
    state["phase_restored_pool150"] = phase
    state["champion_ref"] = {
        "label": "pool150",
        "sample": CHAMP_SAMPLE,
        "net_30d": CHAMP_30,
        "net_60d": CHAMP_60,
    }

    best = None  # best by score vs pool150 among window-evals
    best_promote = None
    live = {"sample": CHAMP_SAMPLE, "30": CHAMP_30, "60": CHAMP_60, "label": "pool150"}
    try_offset = 1000  # namespace restored-phase tries
    t0 = time.time()

    for i, (knob, value) in enumerate(MUTATIONS, 1):
        # safety: never raise inv caps
        if knob == "max_abs_inv" and float(value) > 100:
            continue
        if knob == "inv_soft_cap" and float(value) > 35:
            continue

        try_n = try_offset + i
        print(f"\n=== TRY {try_n} (restored {i}/{len(MUTATIONS)}): {knob}={value} ===", flush=True)
        trial = {
            "try": try_n,
            "phase": "restored_pool150",
            "knob": knob,
            "value": value,
            "parent_value": BASE.get(knob),
            "parent_label": "pool150",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            shutil.copy2(PARENT, STRAT)  # ALWAYS from pool150
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

        sample_net = float(s["sample_net_pnl"])
        trial["sample_net_pnl"] = sample_net
        trial["sample_max_dd_pct"] = s.get("max_dd_pct")
        trial["sample_soft_reject"] = s.get("soft_reject")
        trial["sample_n_fills"] = s.get("n_fills")
        trial["sample_elapsed_sec"] = s.get("elapsed_sec")
        print(f"  sample={sample_net:.2f} dd={s.get('max_dd_pct')}", flush=True)

        if sample_net < SAMPLE_DISCARD or s.get("soft_reject"):
            trial["status"] = "discard_sample"
            trials.append(trial)
            OUT.write_text(json.dumps(state, indent=2, default=str))
            continue

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
        trial["delta_30d"] = round(n30 - CHAMP_30, 4)
        trial["delta_60d"] = round(n60 - CHAMP_60, 4)
        keep, reason = gate_keep(n30, n60)
        trial["keep"] = keep
        trial["keep_reason"] = reason
        beats_pool150 = promote_eligible(
            sample_net, n30, n60, soft30, soft60, bool(s.get("soft_reject"))
        )
        # Only overwrite live champ if also strictly beating current live gate
        beats_live = (
            sample_net >= live["sample"]
            and n30 > live["30"]
            and n60 > live["60"]
            and not soft30 and not soft60 and not s.get("soft_reject")
        )
        trial["promote_eligible"] = beats_pool150 and beats_live
        trial["beats_pool150"] = beats_pool150
        trial["score_vs_pool150"] = round((n30 - CHAMP_30) + (n60 - CHAMP_60), 4)
        print(
            f"  30d={n30:.2f} (d{trial['delta_30d']:+.2f})  "
            f"60d={n60:.2f} (d{trial['delta_60d']:+.2f})  "
            f"keep={keep} ({reason}) beats_pool150={beats_pool150} promote={trial['promote_eligible']}",
            flush=True,
        )

        if best is None or trial["score_vs_pool150"] > best.get("score_vs_pool150", -1e18):
            best = dict(trial)
            shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py")
            state["best_vs_pool150"] = best

        if trial["promote_eligible"]:
            label = promote(trial)
            trial["status"] = "PROMOTED"
            trial["promoted_label"] = label
            best_promote = dict(trial)
            state["promoted_from_pool150"] = True
            state["promoted_trial"] = trial
            live.update({"sample": sample_net, "30": n30, "60": n60, "label": label})
            state["live_champ"] = dict(live)
            print(f"  *** PROMOTED as {label} (new live gate 30d>{n30:.2f} 60d>{n60:.2f}) ***", flush=True)
            # Continue ablations from ORIGINAL pool150 parent for fair one-knob deltas.
        elif keep:
            trial["status"] = "keep_near_champ"
            # write promotion artifact for keep-near without overwriting champ files
            label = f"keep_{trial['knob']}_{str(trial['value']).replace('.', 'p')}"
            write_promotion(trial, label)
        else:
            trial["status"] = "fail_windows"

        trials.append(trial)
        OUT.write_text(json.dumps(state, indent=2, default=str))

    # restore agent working copy to pool150 or latest promote
    if best_promote:
        shutil.copy2(AGENT_DIR / "strategy_promoted.py", STRAT)
    else:
        shutil.copy2(PARENT, STRAT)

    phase["finished_at"] = datetime.now(timezone.utc).isoformat()
    phase["elapsed_sec"] = round(time.time() - t0, 1)
    state["finished_at"] = phase["finished_at"]
    phase_trials = [t for t in trials if t.get("phase") == "restored_pool150"]
    state["restored_summary"] = {
        "n_tried": len(phase_trials),
        "n_sample_pass": sum(
            1
            for t in phase_trials
            if t.get("sample_net_pnl", 0) >= SAMPLE_DISCARD and not t.get("sample_soft_reject")
        ),
        "n_window_eval": sum(1 for t in phase_trials if "net_30d" in t),
        "n_keep": sum(1 for t in phase_trials if t.get("keep")),
        "n_promoted": sum(1 for t in phase_trials if t.get("status") == "PROMOTED"),
        "anything_beat_pool150_windows": any(
            t.get("net_30d") is not None
            and t.get("net_60d") is not None
            and t["net_30d"] > CHAMP_30
            and t["net_60d"] > CHAMP_60
            for t in phase_trials
        ),
        "best_vs_pool150": state.get("best_vs_pool150"),
        "elapsed_sec": phase["elapsed_sec"],
    }
    OUT.write_text(json.dumps(state, indent=2, default=str))
    print("\n=== RESTORED POOL150 HUNT DONE ===", flush=True)
    print(json.dumps(state["restored_summary"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
