#!/usr/bin/env python3
"""Wave5 joint-mutation liveish hunt vs pool100 Aug10 gates.

Prefer mild multi-lever changes that could help BOTH 30d and 60d.
Avoid known-bad: portfolio_inv_cap<=300, hard_cancel=3.0 alone, aggressive soft-cap cuts.
Promote only if sample>528.35 AND liveish 30d>473.85 AND liveish 60d>723.72.
"""
from __future__ import annotations

import json, re, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research/champions/strategy_pool100.py"
AGENT_DIR = ROOT / "research/agents/wave5-joint-hunt"
STRAT = AGENT_DIR / "strategy.py"
OUT = ROOT / "results/window_aware_hunt_wave5_joint.json"
LOG = ROOT / "results/window_aware_hunt_wave5_joint.log"
PY = str(ROOT / ".venv/bin/python")

CHAMP_SAMPLE = 528.35
CHAMP_30 = 473.85
CHAMP_60 = 723.72
CHAMP_90 = 669.01
SAMPLE_DISCARD = 400.0
DAYS_30 = "research/window_30d_liveish_gate_days.txt"
DAYS_60 = "research/window_60d_liveish_gate_days.txt"
DAYS_90 = "research/window_90d_days.txt"
OVERLAY_KNOBS = {"near_mid_size_mult", "near_mid_dist", "portfolio_inv_cap", "cancel_move"}

# Joint mutations: list of (label, [(knob, value), ...])
JOINT_MUTATIONS = [
    ("spread_mild_pause", [("spread_frac", 0.675), ("inv_pause_ticks", 12)]),
    ("spread_mild_pull_pause", [("spread_frac", 0.68), ("pull_size_mult", 0.40), ("inv_pause_ticks", 10)]),
    ("size_down_pause", [("size_mult", 1.22), ("inv_pause_ticks", 12)]),
    ("size_down_pull", [("size_mult", 1.25), ("pull_size_mult", 0.35)]),
    ("pause_12", [("inv_pause_ticks", 12)]),
    ("pause_16_pull", [("inv_pause_ticks", 16), ("pull_size_mult", 0.40)]),
    ("near_mid_size_down", [("near_mid_size_mult", 0.45), ("size_mult", 1.25)]),
    ("skew_mild_pause", [("skew_bps_per_share", 0.32), ("inv_pause_ticks", 12)]),
    ("inv_hard_90", [("max_abs_inv", 90.0)]),
    ("spread_tiny_size_pause", [("spread_frac", 0.672), ("size_mult", 1.25), ("inv_pause_ticks", 10)]),
    ("cancel_soft_hard_pair", [("mid_move_cancel_cents", 2.5), ("mid_move_hard_cancel_cents", 5.0), ("mid_move_widen_mult", 1.8)]),
    ("pull_near_mid", [("pull_size_mult", 0.45), ("near_mid_size_mult", 0.40)]),
    ("spread_0678_pause14", [("spread_frac", 0.678), ("inv_pause_ticks", 14)]),
    ("size_120_skew38_pause", [("size_mult", 1.20), ("skew_bps_per_share", 0.38), ("inv_pause_ticks", 12)]),
    ("pause_10_pull30_size125", [("inv_pause_ticks", 10), ("pull_size_mult", 0.30), ("size_mult", 1.25)]),
    ("near_mid_035_dist02", [("near_mid_size_mult", 0.35), ("near_mid_dist", 0.02)]),
    ("widen_minhalf_pause", [("spread_frac", 0.685), ("min_half_spread", 0.018), ("inv_pause_ticks", 12)]),
    ("inv_soft_32_pause", [("inv_soft_cap", 32.0), ("inv_pause_ticks", 12)]),  # mild, still >=20
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
        pat = re.compile(r'(self\.inv_pause_ticks\s*=\s*int\(cfg\.get\("inv_pause_ticks",\s*)(\d+)(\))')
        text2, n = pat.subn(rf"\g<1>{int(value)}\3", text, count=1)
    elif knob == "mid_move_hard_cancel_cents":
        pat = re.compile(r'(cfg\.get\("mid_move_hard_cancel_cents",\s*)([^)]+)(\))')
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
    elif knob == "mid_move_cancel_cents":
        pat = re.compile(r'(self\.mid_move_cancel_cents\s*=\s*float\(cfg\.get\("mid_move_cancel_cents",\s*)[^)]+(\))')
        text2, n = pat.subn(rf"\g<1>{new_default}\2", text, count=1)
    elif knob == "mid_move_widen_mult":
        pat = re.compile(r'(self\.mid_move_widen_mult\s*=\s*float\(cfg\.get\("mid_move_widen_mult",\s*)([^)]+)(\))')
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
    elif knob == "cancel_move":
        cents = float(value) * 100.0
        pat = re.compile(r'(self\.mid_move_cancel_cents\s*=\s*float\(cfg\.get\("mid_move_cancel_cents",\s*)[^)]+(\))')
        text2, n = pat.subn(rf"\g<1>{cents}\2", text, count=1)
        if n != 1:
            raise RuntimeError(f"cancel_move patch n={n}")
        path.write_text(text2)
        return
    else:
        pat = re.compile(rf'(self\.{re.escape(knob)}\s*=\s*float\(cfg\.get\("{re.escape(knob)}",\s*)([^)]+)(\))')
        text2, n = pat.subn(rf"\g<1>{new_default}\3", text, count=1)
    if n != 1:
        raise RuntimeError(f"failed patch {knob}={value} n={n}")
    path.write_text(text2)


def run_json(cmd, timeout=1800):
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {"error": "nonzero_exit", "code": r.returncode, "stderr": (r.stderr or "")[-2000:], "stdout": (r.stdout or "")[-2000:]}
    out = (r.stdout or "").strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        i = out.rfind("{")
        if i < 0:
            return {"error": "no_json", "stdout": out[-2000:]}
        return json.loads(out[i:])


def eval_sample(overlay=None):
    if overlay:
        return run_json([PY, "scripts/eval_liveish_candidate.py", "--mode", "sample", "--strategy-module", str(STRAT), "--overlay-json", json.dumps(overlay)], 300)
    return run_json([PY, "scripts/eval_sample.py", "--liveish", "--strategy-module", str(STRAT)], 300)


def eval_window(days_file, overlay=None):
    if overlay:
        return run_json([PY, "scripts/eval_liveish_candidate.py", "--mode", "window", "--days-file", days_file, "--strategy-module", str(STRAT), "--overlay-json", json.dumps(overlay)], 1800)
    return run_json([PY, "scripts/eval_window.py", "--liveish", "--days-file", days_file, "--strategy-module", str(STRAT)], 1800)


def do_promote(trial, label):
    named = ROOT / f"research/champions/strategy_{label}.py"
    shutil.copy2(STRAT, named)
    for dest in [ROOT / "research/champions/strategy_current_best.py", ROOT / "strategy.py"]:
        shutil.copy2(STRAT, dest)
    shutil.copy2(STRAT, AGENT_DIR / "strategy_promoted.py")
    promo = {
        "job": f"wave5_promotion_{label}",
        "label": label,
        "parent": "pool100",
        "eval": "liveish",
        "mutation_label": trial.get("mutation_label"),
        "knobs": trial.get("knobs"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gate_liveish_aug10": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60, "90d_info": CHAMP_90},
        "windows_liveish": {
            "sample": trial["sample_net_pnl"], "30d": trial["net_30d"], "60d": trial["net_60d"], "90d": trial.get("net_90d"),
            "deltas": {"sample": trial.get("delta_sample"), "30d": trial.get("delta_30d"), "60d": trial.get("delta_60d")},
        },
        "note": "Beats pool100 under SAME Aug10 liveish flags; optimistic-only not used",
    }
    (ROOT / f"results/promotion_{label}.json").write_text(json.dumps(promo, indent=2, default=str))
    (ROOT / "research/PROMOTION_GATE.md").write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish-validated Aug10; wave5 joint `{trial.get('mutation_label')}`)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

| Window (LIVEISH) | Net PnL to beat |
|------------------|----------------:|
| sample | **{trial['sample_net_pnl']:.2f}** |
| 30d | **{trial['net_30d']:.2f}** |
| 60d | **{trial['net_60d']:.2f}** |

Prior pool100 Aug10 liveish: sample 528.35 / 30d 473.85 / 60d 723.72 / 90d 669.01

## Rules
1. No optimistic-only promotes.
2. Same `--liveish` flags required.
3. Soft <=35, hard <=100; soft >=20.
"""
    )
    path = ROOT / "research/shared_findings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["current_champion"] = {
        "label": label, "eval": "liveish_aug10", "wave": "wave5",
        "mutation_label": trial.get("mutation_label"), "knobs": trial.get("knobs"),
        "sample_net_pnl": trial["sample_net_pnl"], "net_30d": trial["net_30d"], "net_60d": trial["net_60d"],
    }
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append({"ts": data["updated_at"], "agent": "wave5-joint-hunt", "event": "promoted_liveish_aug10", "label": label})
        data["findings"] = findings[-200:]
    path.write_text(json.dumps(data, indent=2, default=str))
    digest = ROOT / "results/overnight_digest.md"
    if digest.exists():
        with open(digest, "a") as f:
            f.write(
                f"\n\n## Wave5 PROMOTION — {label} — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n\n"
                f"- Knobs: `{trial.get('knobs')}`\n"
                f"- Liveish sample **{trial['sample_net_pnl']:.2f}** / 30d **{trial['net_30d']:.2f}** / 60d **{trial['net_60d']:.2f}**\n"
                f"- Beat pool100 Aug10 gates. Champion synced.\n"
            )


def main():
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    if not PARENT.exists():
        raise SystemExit(f"missing {PARENT}")
    shutil.copy2(PARENT, STRAT)
    state = {"trials": [], "wave": "wave5", "phase": "joint_liveish_aug10"}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
            if prev.get("phase") == "joint_liveish_aug10":
                state = prev
        except Exception:
            pass
    trials = state.setdefault("trials", [])
    done_labels = {t.get("mutation_label") for t in trials if t.get("mutation_label") and t.get("status") not in (None, "error")}
    phase = {
        "name": "wave5_joint_liveish_aug10",
        "parent": "pool100",
        "gate_liveish": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60, "90d_info": CHAMP_90},
        "days_30": DAYS_30, "days_60": DAYS_60,
        "started_at": state.get("phase_meta", {}).get("started_at") or datetime.now(timezone.utc).isoformat(),
        "n_planned": len(JOINT_MUTATIONS),
    }
    state["phase_meta"] = phase
    best = state.get("best_vs_pool100_liveish_aug10")
    live = {"sample": CHAMP_SAMPLE, "30": CHAMP_30, "60": CHAMP_60}
    promoted = bool(state.get("promoted_liveish_aug10"))
    try_offset = 5000
    t0 = time.time()
    print(f"Wave5 joint Aug10 liveish gates sample>{CHAMP_SAMPLE} 30d>{CHAMP_30} 60d>{CHAMP_60}", flush=True)

    for i, (mlabel, knobs) in enumerate(JOINT_MUTATIONS, 1):
        if mlabel in done_labels:
            print(f"skip already-done {mlabel}", flush=True)
            continue
        # Safety: skip known-bad patterns
        knobs_d = dict(knobs)
        if "portfolio_inv_cap" in knobs_d and float(knobs_d["portfolio_inv_cap"]) <= 300:
            print(f"skip known-bad portfolio_inv_cap {mlabel}", flush=True)
            continue
        if set(knobs_d.keys()) == {"mid_move_hard_cancel_cents"} and float(knobs_d["mid_move_hard_cancel_cents"]) == 3.0:
            print(f"skip known-bad hard_cancel=3 alone {mlabel}", flush=True)
            continue
        if "inv_soft_cap" in knobs_d and float(knobs_d["inv_soft_cap"]) < 20:
            continue
        if "inv_soft_cap" in knobs_d and float(knobs_d["inv_soft_cap"]) > 35:
            continue
        if "max_abs_inv" in knobs_d and float(knobs_d["max_abs_inv"]) > 100:
            continue

        try_n = try_offset + i
        print(f"\n=== TRY {try_n} wave5 {i}/{len(JOINT_MUTATIONS)}: {mlabel} {knobs} ===", flush=True)
        trial = {
            "try": try_n, "phase": "wave5_joint_liveish_aug10", "mutation_label": mlabel,
            "knobs": knobs, "parent_label": "pool100", "eval": "liveish", "gate": "aug10",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        overlay = {k: v for k, v in knobs if k in OVERLAY_KNOBS} or None
        try:
            shutil.copy2(PARENT, STRAT)
            for knob, value in knobs:
                _patch_file(STRAT, knob, value)
        except Exception as e:
            trial["error"] = f"patch_failed: {e}"; trial["status"] = "error"
            trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue

        s = eval_sample(overlay)
        if "sample_net_pnl" not in s:
            trial["error"] = s; trial["status"] = "error"
            trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        sample_net = float(s["sample_net_pnl"])
        trial.update({"sample_net_pnl": sample_net, "sample_max_dd_pct": s.get("max_dd_pct"),
                      "sample_soft_reject": s.get("soft_reject"), "sample_n_fills": s.get("n_fills"),
                      "sample_elapsed_sec": s.get("elapsed_sec"),
                      "delta_sample": round(sample_net - CHAMP_SAMPLE, 4)})
        print(f"  liveish sample={sample_net:.2f} (d{trial['delta_sample']:+.2f}) dd={s.get('max_dd_pct')}", flush=True)

        if sample_net < SAMPLE_DISCARD or s.get("soft_reject"):
            trial["status"] = "discard_sample"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        if sample_net < CHAMP_SAMPLE * 0.95:
            trial["status"] = "skip_windows_sample_weak"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str))
            print("  sample < 95% champ -> skip windows", flush=True); continue

        print("  competitive -> liveish 30d+60d (Aug10 days)", flush=True)
        w30 = eval_window(DAYS_30, overlay); w60 = eval_window(DAYS_60, overlay)
        if "window_net_pnl" not in w30 or "window_net_pnl" not in w60:
            trial["error_windows"] = {"30d": w30, "60d": w60}; trial["status"] = "error_windows"
            trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        n30, n60 = float(w30["window_net_pnl"]), float(w60["window_net_pnl"])
        soft30, soft60 = bool(w30.get("soft_reject")), bool(w60.get("soft_reject"))
        trial.update({"net_30d": n30, "net_60d": n60, "dd_30d": w30.get("max_dd_pct"), "dd_60d": w60.get("max_dd_pct"),
                      "soft_30d": soft30, "soft_60d": soft60,
                      "delta_30d": round(n30 - CHAMP_30, 4), "delta_60d": round(n60 - CHAMP_60, 4),
                      "score_vs_pool100_liveish_aug10": round((sample_net - CHAMP_SAMPLE) + (n30 - CHAMP_30) + (n60 - CHAMP_60), 4)})
        # Gate: BOTH windows (and sample) must beat; soft_reject false
        beats = (sample_net > CHAMP_SAMPLE and n30 > CHAMP_30 and n60 > CHAMP_60 and not soft30 and not soft60 and not s.get("soft_reject"))
        trial["beats_pool100_liveish"] = beats
        trial["promote_eligible"] = beats
        print(f"  liveish 30d={n30:.2f} (d{trial['delta_30d']:+.2f})  60d={n60:.2f} (d{trial['delta_60d']:+.2f})  beats={beats}", flush=True)

        if best is None or trial["score_vs_pool100_liveish_aug10"] > best.get("score_vs_pool100_liveish_aug10", -1e18):
            best = dict(trial); shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py"); state["best_vs_pool100_liveish_aug10"] = best

        if trial["promote_eligible"] and not promoted:
            if Path(DAYS_90).exists():
                print("  liveish 90d informational...", flush=True)
                w90 = eval_window(DAYS_90, overlay)
                if "window_net_pnl" in w90:
                    trial["net_90d"] = float(w90["window_net_pnl"]); trial["dd_90d"] = w90.get("max_dd_pct")
            label = f"wave5_{mlabel}"
            do_promote(trial, label)
            trial["status"] = "PROMOTED"; trial["promoted_label"] = label
            live.update({"sample": sample_net, "30": n30, "60": n60}); promoted = True
            state["promoted_liveish_aug10"] = True; state["promoted_trial"] = trial
            print(f"  *** PROMOTED {label} ***", flush=True)
        else:
            trial["status"] = "fail_liveish_windows" if not beats else "already_have_promo"

        trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str))

    shutil.copy2(PARENT if not promoted else AGENT_DIR / "strategy_promoted.py", STRAT)
    phase["finished_at"] = datetime.now(timezone.utc).isoformat()
    phase["elapsed_sec"] = round(time.time() - t0, 1)
    pt = [t for t in trials if t.get("phase") == "wave5_joint_liveish_aug10"]
    state["wave5_joint_summary"] = {
        "n_tried": len(pt),
        "n_window_eval": sum(1 for t in pt if "net_30d" in t),
        "n_promoted": sum(1 for t in pt if t.get("status") == "PROMOTED"),
        "anything_beat_pool100_liveish_aug10": any(t.get("beats_pool100_liveish") for t in pt),
        "best": state.get("best_vs_pool100_liveish_aug10"),
        "gate": phase["gate_liveish"],
        "elapsed_sec": phase["elapsed_sec"],
    }
    state["finished_at"] = phase["finished_at"]
    OUT.write_text(json.dumps(state, indent=2, default=str))
    print("\n=== WAVE5 JOINT LIVEISH AUG10 HUNT DONE ===", flush=True)
    print(json.dumps(state["wave5_joint_summary"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
