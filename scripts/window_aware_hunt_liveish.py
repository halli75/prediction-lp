#!/usr/bin/env python3
"""Liveish window-aware hunt vs pool100 Aug10 gates. No optimistic-only promotes."""
from __future__ import annotations

import json, re, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research/agents/window-aware-hunt/strategy_parent_liveish.py"
AGENT_DIR = ROOT / "research/agents/window-aware-hunt"
STRAT = AGENT_DIR / "strategy.py"
OUT = ROOT / "results/window_aware_hunt.json"
PY = str(ROOT / ".venv/bin/python")

CHAMP_SAMPLE = 528.47
CHAMP_30 = 496.98
CHAMP_60 = 861.11
CHAMP_90 = 669.01
SAMPLE_DISCARD = 400.0
DAYS_30 = "research/window_30d_liveish_gate_days.txt"
DAYS_60 = "research/window_60d_liveish_gate_days.txt"
DAYS_90 = "research/window_90d_days.txt"
OVERLAY_KNOBS = {"near_mid_size_mult", "near_mid_dist", "portfolio_inv_cap", "cancel_move"}

MUTATIONS = [
    ("inv_soft_cap", 25.0),
    ("inv_soft_cap", 30.0),
    ("max_abs_inv", 80.0),
    ("min_edge_vs_bbo", 0.01),
    ("vol_filter", 0.03),
    ("near_mid_size_mult", 0.35),
    ("near_mid_size_mult", 0.25),
    ("portfolio_inv_cap", 300.0),
    ("portfolio_inv_cap", 250.0),
    ("cancel_move", 0.015),
    ("pull_size_mult", 0.30),
    ("inv_pause_ticks", 9),
    ("mid_move_hard_cancel_cents", 3.0),
    ("spread_frac", 0.69),
    ("size_mult", 1.25),
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
    for dest in [ROOT / "research/champions/strategy_current_best.py", ROOT / "research/champions/strategy_hybrid_spread_size.py", ROOT / "strategy.py"]:
        shutil.copy2(STRAT, dest)
    shutil.copy2(STRAT, AGENT_DIR / "strategy_promoted.py")
    promo = {
        "job": f"COMMANDER_promotion_{label}",
        "label": label,
        "parent": "pool100",
        "eval": "liveish",
        "knob": trial["knob"],
        "value": trial["value"],
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

**Current champion:** `{label}` (liveish-validated Aug10; `{trial['knob']}={trial['value']}`)
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
3. Soft <=35, hard <=100.
"""
    )
    path = ROOT / "research/shared_findings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["current_champion"] = {"label": label, "eval": "liveish_aug10", "knob": trial["knob"], "value": trial["value"],
                                "sample_net_pnl": trial["sample_net_pnl"], "net_30d": trial["net_30d"], "net_60d": trial["net_60d"]}
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append({"ts": data["updated_at"], "agent": "window-aware-hunt", "event": "promoted_liveish_aug10", "label": label})
    path.write_text(json.dumps(data, indent=2, default=str))


def main():
    if not PARENT.exists():
        raise SystemExit(f"missing {PARENT}")
    shutil.copy2(PARENT, STRAT)
    state = json.loads(OUT.read_text()) if OUT.exists() else {"trials": []}
    trials = state.setdefault("trials", [])
    phase = {
        "name": "liveish_aug10_from_pool100",
        "parent": str(PARENT.relative_to(ROOT)),
        "gate_liveish": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60, "90d_info": CHAMP_90},
        "days_30": DAYS_30, "days_60": DAYS_60,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "n_planned": len(MUTATIONS),
    }
    state["phase_liveish_aug10"] = phase
    best = None
    live = {"sample": CHAMP_SAMPLE, "30": CHAMP_30, "60": CHAMP_60}
    promoted = False
    try_offset = 4000
    t0 = time.time()
    print(f"Aug10 liveish gates sample>{CHAMP_SAMPLE} 30d>{CHAMP_30} 60d>{CHAMP_60}", flush=True)

    for i, (knob, value) in enumerate(MUTATIONS, 1):
        if knob == "max_abs_inv" and float(value) > 100:
            continue
        if knob == "inv_soft_cap" and float(value) > 35:
            continue
        try_n = try_offset + i
        print(f"\n=== TRY {try_n} (aug10 {i}/{len(MUTATIONS)}): {knob}={value} ===", flush=True)
        trial = {"try": try_n, "phase": "liveish_aug10_from_pool100", "knob": knob, "value": value,
                 "parent_label": "pool100", "eval": "liveish", "gate": "aug10",
                 "ts": datetime.now(timezone.utc).isoformat()}
        overlay = {knob: value} if knob in OVERLAY_KNOBS else None
        try:
            shutil.copy2(PARENT, STRAT)
            _patch_file(STRAT, knob, value)
        except Exception as e:
            trial["error"] = f"patch_failed: {e}"
            trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue

        s = eval_sample(overlay)
        if "sample_net_pnl" not in s:
            trial["error"] = s; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
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
            trial["error_windows"] = {"30d": w30, "60d": w60}; trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str)); continue
        n30, n60 = float(w30["window_net_pnl"]), float(w60["window_net_pnl"])
        soft30, soft60 = bool(w30.get("soft_reject")), bool(w60.get("soft_reject"))
        trial.update({"net_30d": n30, "net_60d": n60, "dd_30d": w30.get("max_dd_pct"), "dd_60d": w60.get("max_dd_pct"),
                      "soft_30d": soft30, "soft_60d": soft60,
                      "delta_30d": round(n30 - CHAMP_30, 4), "delta_60d": round(n60 - CHAMP_60, 4),
                      "score_vs_pool100_liveish_aug10": round((sample_net - CHAMP_SAMPLE) + (n30 - CHAMP_30) + (n60 - CHAMP_60), 4)})
        beats = (sample_net > CHAMP_SAMPLE and n30 > CHAMP_30 and n60 > CHAMP_60 and not soft30 and not soft60 and not s.get("soft_reject"))
        beats_live = (sample_net > live["sample"] and n30 > live["30"] and n60 > live["60"] and not soft30 and not soft60 and not s.get("soft_reject"))
        trial["beats_pool100_liveish"] = beats
        trial["promote_eligible"] = beats and beats_live
        print(f"  liveish 30d={n30:.2f} (d{trial['delta_30d']:+.2f})  60d={n60:.2f} (d{trial['delta_60d']:+.2f})  beats={beats} promote={trial['promote_eligible']}", flush=True)

        if best is None or trial["score_vs_pool100_liveish_aug10"] > best.get("score_vs_pool100_liveish_aug10", -1e18):
            best = dict(trial); shutil.copy2(STRAT, AGENT_DIR / "strategy_best_so_far.py"); state["best_vs_pool100_liveish_aug10"] = best

        if trial["promote_eligible"]:
            if Path(DAYS_90).exists():
                print("  liveish 90d informational...", flush=True)
                w90 = eval_window(DAYS_90, overlay)
                if "window_net_pnl" in w90:
                    trial["net_90d"] = float(w90["window_net_pnl"]); trial["dd_90d"] = w90.get("max_dd_pct")
                    print(f"  liveish 90d={trial['net_90d']:.2f}", flush=True)
            label = f"liveish_aug10_{knob}_{str(value).replace('.', 'p')}"
            do_promote(trial, label)
            trial["status"] = "PROMOTED"; trial["promoted_label"] = label
            live.update({"sample": sample_net, "30": n30, "60": n60}); promoted = True
            state["promoted_liveish_aug10"] = True; state["promoted_trial"] = trial
            print(f"  *** PROMOTED {label} ***", flush=True)
        else:
            trial["status"] = "fail_liveish_windows" if not beats else "beats_but_not_live"

        trials.append(trial); OUT.write_text(json.dumps(state, indent=2, default=str))

    shutil.copy2(PARENT if not promoted else AGENT_DIR / "strategy_promoted.py", STRAT)
    phase["finished_at"] = datetime.now(timezone.utc).isoformat()
    phase["elapsed_sec"] = round(time.time() - t0, 1)
    pt = [t for t in trials if t.get("phase") == "liveish_aug10_from_pool100"]
    state["liveish_aug10_summary"] = {
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
    print("\n=== LIVEISH AUG10 HUNT DONE ===", flush=True)
    print(json.dumps(state["liveish_aug10_summary"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
