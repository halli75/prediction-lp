#!/usr/bin/env python3
"""Wave11: joint hunt from wave5b under Aug10 liveish gates (post wave9 near-miss noise on pull48+widen165)."""
from __future__ import annotations
import json, re, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research/champions/strategy_wave5b_pull24_p46_sf672.py"
AGENT_DIR = ROOT / "research/agents/wave11-from-wave5b"
STRAT = AGENT_DIR / "strategy.py"
OUT = ROOT / "results/window_aware_hunt_wave11_from_wave5b.json"
PY = str(ROOT / ".venv/bin/python")
CHAMP_SAMPLE, CHAMP_30, CHAMP_60 = 528.47, 496.98, 861.11
SAMPLE_DISCARD = 480.0
DAYS_30 = "research/window_30d_liveish_gate_days.txt"
DAYS_60 = "research/window_60d_liveish_gate_days.txt"
OVERLAY_KNOBS = {"near_mid_size_mult", "near_mid_dist", "portfolio_inv_cap", "cancel_move"}

# Wave9: pull48+widen165 only +~$3 on 30/60 (noise) and sample -8; skew lifts 30d / kills 60d.
# Wave11: sample-preserving joint around wave5b — soft-cancel, hard-cancel, size, pool, pull ridge.
JOINT_MUTATIONS = [
    # Wave10: pool110 crushed windows (30d +199 / 60d +131) but sample -10.5.
    # Wave11: pool ridge 102–120 + size/pull/pause/spread compensators to recover sample.
    ("sf672_pool102_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 102.0)]),
    ("sf672_pool105_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 105.0)]),
    ("sf672_pool108_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 108.0)]),
    ("sf672_pool112_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 112.0)]),
    ("sf672_pool115_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 115.0)]),
    ("sf672_pool120_pull24", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 120.0)]),
    ("sf672_pool105_size1250", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 105.0), ("size_mult", 1.250)]),
    ("sf672_pool108_size1260", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 108.0), ("size_mult", 1.260)]),
    ("sf672_pool110_size1240", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 110.0), ("size_mult", 1.240)]),
    ("sf672_pool112_size1255", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 112.0), ("size_mult", 1.255)]),
    ("sf672_pool105_pull22_p450", [("spread_frac", 0.672), ("inv_pause_ticks", 22), ("pull_size_mult", 0.450), ("min_daily_reward_pool", 105.0)]),
    ("sf672_pool108_pull26_p450", [("spread_frac", 0.672), ("inv_pause_ticks", 26), ("pull_size_mult", 0.450), ("min_daily_reward_pool", 108.0)]),
    ("sf672_pool110_pull28_p440", [("spread_frac", 0.672), ("inv_pause_ticks", 28), ("pull_size_mult", 0.440), ("min_daily_reward_pool", 110.0)]),
    ("sf672_pool110_pull24_p480", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.480), ("min_daily_reward_pool", 110.0)]),
    ("sf672_pool105_sf678", [("spread_frac", 0.678), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 105.0)]),
    ("sf672_pool110_sf675_size1260", [("spread_frac", 0.675), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 110.0), ("size_mult", 1.260)]),
    ("sf672_pool108_sf670_pull26", [("spread_frac", 0.670), ("inv_pause_ticks", 26), ("pull_size_mult", 0.455), ("min_daily_reward_pool", 108.0)]),
    ("sf672_pool110_soft32", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 110.0), ("inv_soft_cap", 32.0)]),
    ("sf672_pool108_nearmid080", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 108.0), ("near_mid_size_mult", 0.80), ("near_mid_dist", 0.025)]),
    ("sf672_pool110_mhs017_size1250", [("spread_frac", 0.672), ("inv_pause_ticks", 24), ("pull_size_mult", 0.464), ("min_daily_reward_pool", 110.0), ("min_half_spread", 0.017), ("size_mult", 1.250)]),
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
        return json.loads(out[i:]) if i >= 0 else {"error": "no_json", "stdout": out[-2000:]}


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
    promo = {
        "job": f"wave11_promotion_{label}", "label": label, "parent": "wave5b_pull24_p46_sf672", "eval": "liveish",
        "mutation_label": trial.get("mutation_label"), "knobs": trial.get("knobs"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gate_liveish_aug10": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "windows_liveish": {"sample": trial["sample_net_pnl"], "30d": trial["net_30d"], "60d": trial["net_60d"],
                            "deltas": {"sample": trial.get("delta_sample"), "30d": trial.get("delta_30d"), "60d": trial.get("delta_60d")}},
    }
    (ROOT / f"results/promotion_{label}.json").write_text(json.dumps(promo, indent=2, default=str))
    (ROOT / "research/PROMOTION_GATE.md").write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish-validated Aug10; wave11 `{trial.get('mutation_label')}`)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

| Window (LIVEISH) | Net PnL to beat |
|------------------|----------------:|
| sample | **{trial['sample_net_pnl']:.2f}** |
| 30d | **{trial['net_30d']:.2f}** |
| 60d | **{trial['net_60d']:.2f}** |

Prior wave5b Aug10 liveish: sample 528.47 / 30d 496.98 / 60d 861.11

## Rules
1. No optimistic-only promotes.
2. Same `--liveish` flags required.
3. Soft <=35, hard <=100; soft >=20.
"""
    )
    path = ROOT / "research/shared_findings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["current_champion"] = {"label": label, "eval": "liveish_aug10", "wave": "wave11", "mutation_label": trial.get("mutation_label"),
                                "knobs": trial.get("knobs"), "sample_net_pnl": trial["sample_net_pnl"], "net_30d": trial["net_30d"], "net_60d": trial["net_60d"]}
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append({"ts": data["updated_at"], "agent": "wave11-from-wave5b", "event": "promoted_liveish_aug10", "label": label})
        data["findings"] = findings[-200:]
    path.write_text(json.dumps(data, indent=2, default=str))
    with open(ROOT / "results/overnight_digest.md", "a") as f:
        f.write(f"\n\n## Wave11 PROMOTION — {label} — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n\n- Knobs: `{trial.get('knobs')}`\n- Liveish sample **{trial['sample_net_pnl']:.2f}** / 30d **{trial['net_30d']:.2f}** / 60d **{trial['net_60d']:.2f}**\n- Beat wave5b Aug10 gates. Champion synced.\n")


def main():
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PARENT, STRAT)
    state = {"trials": [], "wave": "wave11", "phase": "from_wave5b_liveish_aug10"}
    trials = state["trials"]
    best = None
    promoted = False
    t0 = time.time()
    print(f"Wave11 from wave5b gates S>{CHAMP_SAMPLE} 30>{CHAMP_30} 60>{CHAMP_60}", flush=True)
    for i, (mlabel, knobs) in enumerate(JOINT_MUTATIONS, 1):
        knobs_d = dict(knobs)
        if "inv_soft_cap" in knobs_d and not (20 <= float(knobs_d["inv_soft_cap"]) <= 35):
            continue
        if "max_abs_inv" in knobs_d and float(knobs_d["max_abs_inv"]) > 100:
            continue
        print(f"\n=== TRY 11-{i}/{len(JOINT_MUTATIONS)}: {mlabel} {knobs} ===", flush=True)
        trial = {"try": 10100+i, "phase": "wave11_from_wave5b", "mutation_label": mlabel, "knobs": knobs,
                 "parent_label": "wave5b_pull24_p46_sf672", "eval": "liveish", "ts": datetime.now(timezone.utc).isoformat()}
        overlay = {k: v for k, v in knobs if k in OVERLAY_KNOBS} or None
        try:
            shutil.copy2(PARENT, STRAT)
            for knob, value in knobs:
                _patch_file(STRAT, knob, value)
        except Exception as e:
            trial["error"] = f"patch_failed: {e}"; trial["status"] = "error"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        s = eval_sample(overlay)
        if "sample_net_pnl" not in s:
            trial["error"] = s; trial["status"] = "error"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        sample_net = float(s["sample_net_pnl"])
        trial.update({"sample_net_pnl": sample_net, "sample_max_dd_pct": s.get("max_dd_pct"), "sample_soft_reject": s.get("soft_reject"),
                      "delta_sample": round(sample_net - CHAMP_SAMPLE, 4)})
        print(f"  sample={sample_net:.2f} d{trial['delta_sample']:+.2f}", flush=True)
        if sample_net < SAMPLE_DISCARD or s.get("soft_reject"):
            trial["status"] = "discard_sample"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        if sample_net < CHAMP_SAMPLE * 0.95:
            trial["status"] = "skip_windows_sample_weak"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        print("  -> windows", flush=True)
        w30 = eval_window(DAYS_30, overlay); w60 = eval_window(DAYS_60, overlay)
        if "window_net_pnl" not in w30 or "window_net_pnl" not in w60:
            trial["error_windows"] = {"30d": w30, "60d": w60}; trial["status"] = "error_windows"; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        n30, n60 = float(w30["window_net_pnl"]), float(w60["window_net_pnl"])
        soft30, soft60 = bool(w30.get("soft_reject")), bool(w60.get("soft_reject"))
        trial.update({"net_30d": n30, "net_60d": n60, "soft_30d": soft30, "soft_60d": soft60,
                      "delta_30d": round(n30 - CHAMP_30, 4), "delta_60d": round(n60 - CHAMP_60, 4),
                      "score_vs_wave5b_liveish_aug10": round((sample_net - CHAMP_SAMPLE) + (n30 - CHAMP_30) + (n60 - CHAMP_60), 4)})
        beats = (sample_net > CHAMP_SAMPLE and n30 > CHAMP_30 and n60 > CHAMP_60 and not soft30 and not soft60 and not s.get("soft_reject"))
        # Also require clear margin: total 30+60 delta >= ~$5 (noise floor)
        margin_ok = (n30 - CHAMP_30) + (n60 - CHAMP_60) >= 5.0
        trial["beats_wave5b_liveish"] = beats and margin_ok
        print(f"  30d={n30:.2f} d{trial['delta_30d']:+.2f}  60d={n60:.2f} d{trial['delta_60d']:+.2f} beats={trial['beats_wave5b_liveish']}", flush=True)
        if best is None or trial["score_vs_wave5b_liveish_aug10"] > best.get("score_vs_wave5b_liveish_aug10", -1e18):
            best = dict(trial); shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py"); state["best"] = best
        if trial["beats_wave5b_liveish"] and not promoted:
            label = f"wave11_{mlabel}"
            do_promote(trial, label)
            trial["status"] = "PROMOTED"; trial["promoted_label"] = label; promoted = True
            state["promoted"] = True; state["promoted_trial"] = trial
            print(f"  *** PROMOTED {label} ***", flush=True)
        else:
            trial["status"] = "fail_liveish_windows" if sample_net >= CHAMP_SAMPLE * 0.95 else trial.get("status", "fail")
        trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str))
    shutil.copy2(PARENT if not promoted else AGENT_DIR / "strategy_best_so_far.py", STRAT)
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["elapsed_sec"] = round(time.time() - t0, 1)
    state["summary"] = {"n_tried": len(trials), "n_window_eval": sum(1 for t in trials if "net_30d" in t),
                        "n_promoted": sum(1 for t in trials if t.get("status") == "PROMOTED"),
                        "best": best}
    OUT.write_text(json.dumps(state, indent=2, default=str))
    print(f"\nWave11 done promoted={promoted} n={len(trials)} best={best.get('mutation_label') if best else None}", flush=True)


if __name__ == "__main__":
    main()
