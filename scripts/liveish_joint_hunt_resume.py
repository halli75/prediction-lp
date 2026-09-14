#!/usr/bin/env python3
"""Resume liveish joint hunt vs pool100 + targeted follow-ups.

Does not overwrite wave5b champion unless candidate also beats wave5b
liveish gates (496.98 / 861.11).
"""
from __future__ import annotations

import gc
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

OUT = ROOT / "results" / "liveish_joint_hunt.json"
PARENT = ROOT / "research" / "champions" / "strategy_pool100.py"
DAYS_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
DAYS_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"

CHAMP_SAMPLE = 528.35
CHAMP_30 = 473.85
CHAMP_60 = 723.72
WAVE5B_SAMPLE = 528.47
WAVE5B_30 = 496.98
WAVE5B_60 = 861.11
SAMPLE_KEEP = 528.35
SAMPLE_DELTA_FLOOR = 505.0
DD_LIMIT = 25.0

LIVEISH_STRATEGY_CFG = {
    "near_mid_size_mult": 0.5,
    "near_mid_dist": 0.02,
    "portfolio_inv_cap": 400.0,
    "cancel_move": 0.02,
}

PARENT_KNOBS = {
    "spread_frac": 0.6676,
    "size_mult": 1.291,
    "inv_pause_ticks": 8,
    "pull_size_mult": 0.5,
    "skew_bps_per_share": 0.35,
    "mid_move_widen_mult": 1.6,
}

REMAINING = [
    {"name": "s069_widen18", "mut": {"spread_frac": 0.69, "mid_move_widen_mult": 1.8}, "family": "spread_widen"},
    {"name": "s068_skew040", "mut": {"spread_frac": 0.68, "skew_bps_per_share": 0.40}, "family": "spread_skew"},
    {"name": "s0675_size127_pause9", "mut": {"spread_frac": 0.675, "size_mult": 1.27, "inv_pause_ticks": 9}, "family": "triple"},
    # follow-ups from first 25: 0.68 has only -18 60d; pull 0.35 recovered 155 on 0.69 60d
    {"name": "s068_pull035", "mut": {"spread_frac": 0.68, "pull_size_mult": 0.35}, "family": "followup"},
    {"name": "s068_pull030", "mut": {"spread_frac": 0.68, "pull_size_mult": 0.30}, "family": "followup"},
    {"name": "s0685_pull035", "mut": {"spread_frac": 0.685, "pull_size_mult": 0.35}, "family": "followup"},
    {"name": "s068_pause16_pull040", "mut": {"spread_frac": 0.68, "inv_pause_ticks": 16, "pull_size_mult": 0.40}, "family": "followup"},
    {"name": "s068_pause24_pull046", "mut": {"spread_frac": 0.68, "inv_pause_ticks": 24, "pull_size_mult": 0.46}, "family": "followup"},
    {"name": "s0675_pause24_pull046", "mut": {"spread_frac": 0.675, "inv_pause_ticks": 24, "pull_size_mult": 0.46}, "family": "followup"},
    {"name": "s068_pull035_skew040", "mut": {"spread_frac": 0.68, "pull_size_mult": 0.35, "skew_bps_per_share": 0.40}, "family": "followup"},
    {"name": "s069_pull035_pause16", "mut": {"spread_frac": 0.69, "pull_size_mult": 0.35, "inv_pause_ticks": 16}, "family": "followup"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mem_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        return -1.0
    return -1.0


def load_days(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def assemble_window(days, markets):
    from prepare import assemble_prices
    import pandas as pd

    frames = []
    for d in days:
        p = ROOT / "data" / "slim_days" / f"{d}.parquet"
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
        gc.collect()
    prices = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    return (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )


def load_strategy_class():
    import importlib.util

    spec = importlib.util.spec_from_file_location("joint_parent", PARENT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.Strategy


def run_liveish(prices, markets, StratCls, overlay, capital=10_000.0):
    strat = StratCls({**LIVEISH_STRATEGY_CFG, **overlay})
    eng = BacktestEngine(markets, strat, liveish_engine_config({"capital0": capital}))
    m = eng.run(prices, None)
    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    return {
        "net_pnl": net,
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "max_dd_pct": dd,
        "n_fills": m.get("n_fills"),
        "soft_reject": dd > DD_LIMIT,
    }


def save(state):
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.replace(OUT)


def _patch_file(path: Path, knob: str, value) -> None:
    text = path.read_text()
    if isinstance(value, float):
        new_default = f"{value}" if "." in f"{value}" else f"{value}.0"
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


def do_promote(trial):
    mut = trial["mut"]
    label = f"liveish_joint_{trial['name']}"
    named = ROOT / "research" / "champions" / f"strategy_{label}.py"
    shutil.copy2(PARENT, named)
    for k, v in mut.items():
        _patch_file(named, k, v)
    for dest in [ROOT / "research" / "champions" / "strategy_current_best.py", ROOT / "strategy.py"]:
        shutil.copy2(named, dest)
    promo = {
        "job": f"COMMANDER_promotion_{label}",
        "label": label,
        "parent": "pool100",
        "eval": "liveish",
        "mut": mut,
        "created_at": now_iso(),
        "beats_pool100": True,
        "beats_wave5b": True,
        "windows_liveish": {
            "sample": trial["sample_net_pnl"],
            "30d": trial["net_30d"],
            "60d": trial["net_60d"],
            "deltas_vs_pool100": {"30d": trial.get("delta_30d"), "60d": trial.get("delta_60d")},
            "deltas_vs_wave5b": {
                "30d": round(trial["net_30d"] - WAVE5B_30, 4),
                "60d": round(trial["net_60d"] - WAVE5B_60, 4),
            },
        },
    }
    (ROOT / "results" / f"promotion_{label}.json").write_text(json.dumps(promo, indent=2, default=str))
    (ROOT / "research" / "PROMOTION_GATE.md").write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish joint-hunt compensating pair; also beats wave5b)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

Mutations vs pool100: `{json.dumps(mut)}`

| Window (LIVEISH) | Net PnL to beat |
|------------------|----------------:|
| sample | **{trial['sample_net_pnl']:.2f}** |
| 30d | **{trial['net_30d']:.2f}** |
| 60d | **{trial['net_60d']:.2f}** |

Prior wave5b: sample 528.47 / 30d 496.98 / 60d 861.11
Prior pool100: sample 528.35 / 30d 473.85 / 60d 723.72

## Rules
1. No optimistic-only promotes.
2. Same `--liveish` flags required.
3. Soft <=35, hard <=100.
"""
    )
    path = ROOT / "research" / "shared_findings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["updated_at"] = now_iso()
    data["current_champion"] = {
        "label": label,
        "eval": "liveish_aug10",
        "mut": mut,
        "sample_net_pnl": trial["sample_net_pnl"],
        "net_30d": trial["net_30d"],
        "net_60d": trial["net_60d"],
        "parent": "pool100",
        "also_beats_wave5b": True,
    }
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append({"ts": data["updated_at"], "agent": "liveish-joint-hunt", "event": "promoted_over_wave5b", "label": label, "mut": mut})
    path.write_text(json.dumps(data, indent=2, default=str))
    digest = ROOT / "results" / "overnight_digest.md"
    block = (
        f"\n\n## PROMOTED liveish joint hunt — {data['updated_at']}\n\n"
        f"Label `{label}` also beats wave5b. Mut vs pool100: `{json.dumps(mut)}`.\n"
        f"sample {trial['sample_net_pnl']:.2f} / 30d {trial['net_30d']:.2f} / 60d {trial['net_60d']:.2f}\n"
    )
    if digest.exists():
        digest.write_text(digest.read_text() + block)
    return label


def main():
    import pandas as pd
    from prepare import load_allowlist_markets

    t0 = time.time()
    state = json.loads(OUT.read_text()) if OUT.exists() else {"trials": []}
    done = {t.get("name") for t in state.get("trials", [])}
    planned = [s for s in REMAINING if s["name"] not in done]
    print(f"resume: already {len(done)} trials, {len(planned)} remaining+followup rss={mem_mb():.0f}MB", flush=True)
    state.setdefault("resume", []).append({"ts": now_iso(), "n_done": len(done), "n_todo": len(planned)})
    save(state)

    StratCls = load_strategy_class()
    markets_sample = json.loads((ROOT / "data" / "markets.json").read_text())
    markets_win = load_allowlist_markets()
    sample_prices = pd.read_parquet(ROOT / "data" / "research_sample_prices.parquet")
    print("assembling 30d...", flush=True)
    prices_30 = assemble_window(load_days(DAYS_30), markets_win)
    print(f"30d rows={len(prices_30)} rss={mem_mb():.0f}MB", flush=True)
    print("assembling 60d...", flush=True)
    prices_60 = assemble_window(load_days(DAYS_60), markets_win)
    print(f"60d rows={len(prices_60)} rss={mem_mb():.0f}MB", flush=True)

    best_joint = state.get("best_by_min_window_delta")
    best_score = state.get("best_by_score_sum")
    promoted = bool(state.get("promoted"))
    try_n = max((t.get("try") or 0) for t in state.get("trials", [])) if state.get("trials") else 0

    for spec in planned:
        try_n += 1
        mut = spec["mut"]
        trial = {
            "try": try_n,
            "name": spec["name"],
            "family": spec["family"],
            "mut": mut,
            "parent_knobs": {k: PARENT_KNOBS.get(k) for k in mut},
            "ts": now_iso(),
            "eval": "liveish",
            "phase": "resume_followup",
        }
        print(f"\n=== TRY {try_n} {spec['name']} {mut} rss={mem_mb():.0f}MB ===", flush=True)
        t_s = time.time()
        s = run_liveish(sample_prices, markets_sample, StratCls, mut)
        sample_net = float(s["net_pnl"])
        trial.update({
            "sample_net_pnl": sample_net,
            "sample_reward_pnl": s.get("reward_pnl"),
            "sample_trading_pnl": s.get("trading_pnl"),
            "sample_max_dd_pct": s.get("max_dd_pct"),
            "sample_soft_reject": s.get("soft_reject"),
            "sample_n_fills": s.get("n_fills"),
            "sample_elapsed_sec": round(time.time() - t_s, 3),
            "delta_sample": round(sample_net - CHAMP_SAMPLE, 4),
        })
        print(f"  liveish sample={sample_net:.2f} (d{trial['delta_sample']:+.2f}) dd={s.get('max_dd_pct')} fills={s.get('n_fills')}", flush=True)
        gc.collect()

        keep = sample_net > SAMPLE_KEEP and not s.get("soft_reject")
        delta_only = (not keep) and sample_net >= SAMPLE_DELTA_FLOOR and not s.get("soft_reject")
        trial["keep"] = keep
        trial["delta_only_windows"] = bool(delta_only)
        if not keep and not delta_only:
            trial["status"] = "discard_sample"
            state["trials"].append(trial)
            save(state)
            print("  discard sample -> skip windows", flush=True)
            continue

        why = "KEEP sample>528.35" if keep else f"delta-report sample>={SAMPLE_DELTA_FLOOR}"
        print(f"  {why} -> liveish 30d+60d", flush=True)
        t30 = time.time()
        w30 = run_liveish(prices_30, markets_win, StratCls, mut)
        gc.collect()
        t60 = time.time()
        w60 = run_liveish(prices_60, markets_win, StratCls, mut)
        gc.collect()
        n30, n60 = float(w30["net_pnl"]), float(w60["net_pnl"])
        trial.update({
            "net_30d": n30, "net_60d": n60,
            "reward_30d": w30.get("reward_pnl"), "reward_60d": w60.get("reward_pnl"),
            "trading_30d": w30.get("trading_pnl"), "trading_60d": w60.get("trading_pnl"),
            "dd_30d": w30.get("max_dd_pct"), "dd_60d": w60.get("max_dd_pct"),
            "fills_30d": w30.get("n_fills"), "fills_60d": w60.get("n_fills"),
            "soft_30d": bool(w30.get("soft_reject")), "soft_60d": bool(w60.get("soft_reject")),
            "elapsed_30d": round(t60 - t30, 3), "elapsed_60d": round(time.time() - t60, 3),
            "delta_30d": round(n30 - CHAMP_30, 4), "delta_60d": round(n60 - CHAMP_60, 4),
            "delta_30d_vs_wave5b": round(n30 - WAVE5B_30, 4),
            "delta_60d_vs_wave5b": round(n60 - WAVE5B_60, 4),
            "score_sum": round((sample_net - CHAMP_SAMPLE) + (n30 - CHAMP_30) + (n60 - CHAMP_60), 4),
            "score_min_window": round(min(n30 - CHAMP_30, n60 - CHAMP_60), 4),
        })
        beats_p100 = sample_net > CHAMP_SAMPLE and n30 > CHAMP_30 and n60 > CHAMP_60 and not trial["soft_30d"] and not trial["soft_60d"] and not s.get("soft_reject")
        beats_w5 = n30 > WAVE5B_30 and n60 > WAVE5B_60 and not trial["soft_30d"] and not trial["soft_60d"] and not s.get("soft_reject")
        trial["beats_pool100_liveish"] = beats_p100
        trial["beats_wave5b_liveish"] = beats_w5
        trial["promote_eligible"] = bool(beats_p100 and beats_w5)
        print(f"  liveish 30d={n30:.2f} (d{trial['delta_30d']:+.2f} vs p100, d{trial['delta_30d_vs_wave5b']:+.2f} vs w5b)  60d={n60:.2f} (d{trial['delta_60d']:+.2f} / d{trial['delta_60d_vs_wave5b']:+.2f})  p100={beats_p100} w5b={beats_w5}", flush=True)

        if best_score is None or trial["score_sum"] > best_score.get("score_sum", -1e18):
            best_score = dict(trial)
            state["best_by_score_sum"] = best_score
        if best_joint is None or trial["score_min_window"] > best_joint.get("score_min_window", -1e18):
            best_joint = dict(trial)
            state["best_by_min_window_delta"] = best_joint

        if trial["promote_eligible"] and not promoted:
            label = do_promote(trial)
            trial["status"] = "PROMOTED"
            trial["promoted_label"] = label
            promoted = True
            state["promoted"] = True
            state["promoted_trial"] = trial
            print(f"  *** PROMOTED {label} ***", flush=True)
        else:
            trial["status"] = "fail_liveish_windows" if keep else "windows_delta_only_sample_below_gate"
        state["trials"].append(trial)
        save(state)

    elapsed = round(time.time() - t0, 1)
    pt = state["trials"]
    windowed = [t for t in pt if "net_30d" in t]
    both_pos = [t for t in windowed if (t.get("delta_30d") or 0) > 0 and (t.get("delta_60d") or 0) > 0]
    state["summary"] = {
        "n_tried": len(pt),
        "n_window_eval": len(windowed),
        "n_keep_sample": sum(1 for t in pt if t.get("keep")),
        "n_discard_sample": sum(1 for t in pt if t.get("status") == "discard_sample"),
        "n_both_windows_positive_vs_pool100": len(both_pos),
        "n_promoted": sum(1 for t in pt if t.get("status") == "PROMOTED"),
        "anything_beat_pool100_liveish": any(t.get("beats_pool100_liveish") for t in pt),
        "anything_beat_wave5b_liveish": any(t.get("beats_wave5b_liveish") for t in pt),
        "best_by_score_sum": state.get("best_by_score_sum"),
        "best_by_min_window_delta": state.get("best_by_min_window_delta"),
        "both_windows_positive_vs_pool100": [
            {"name": t["name"], "mut": t["mut"], "sample": t.get("sample_net_pnl"),
             "d_sample": t.get("delta_sample"), "d30": t.get("delta_30d"), "d60": t.get("delta_60d")}
            for t in both_pos
        ],
        "gate_pool100": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "gate_wave5b_current": {"sample": WAVE5B_SAMPLE, "30d": WAVE5B_30, "60d": WAVE5B_60},
        "resume_elapsed_sec": elapsed,
        "promoted": promoted,
    }
    state["finished_at"] = now_iso()
    save(state)

    path = ROOT / "research" / "shared_findings.json"
    if path.exists():
        data = json.loads(path.read_text())
        data["updated_at"] = now_iso()
        findings = data.setdefault("findings", [])
        if isinstance(findings, list):
            findings.append({
                "ts": data["updated_at"],
                "agent": "liveish-joint-hunt",
                "event": "liveish_joint_hunt_complete",
                "promoted": promoted,
                "n_tried": len(pt),
                "n_window_eval": len(windowed),
                "n_both_windows_positive_vs_pool100": len(both_pos),
                "best_min_window": {
                    "name": (best_joint or {}).get("name"),
                    "mut": (best_joint or {}).get("mut"),
                    "d30": (best_joint or {}).get("delta_30d"),
                    "d60": (best_joint or {}).get("delta_60d"),
                    "sample": (best_joint or {}).get("sample_net_pnl"),
                },
                "note": "Compensating-pair hunt vs pool100 Aug10 liveish 473.85/723.72. Current champ wave5b 496.98/861.11 not overwritten unless beaten.",
            })
        path.write_text(json.dumps(data, indent=2, default=str))

    digest = ROOT / "results" / "overnight_digest.md"
    best = best_joint or {}
    block = (
        f"\n\n## Liveish joint hunt (compensating pairs) — {state['finished_at']}\n\n"
        f"Parent pool100. {len(pt)} trials, {len(windowed)} window evals, "
        f"{len(both_pos)} both-windows-positive vs pool100, promoted={promoted}.\n\n"
        f"Best min-window-delta vs pool100: `{best.get('name')}` mut=`{json.dumps(best.get('mut'))}` "
        f"sample={best.get('sample_net_pnl')} d30={best.get('delta_30d')} d60={best.get('delta_60d')}.\n"
        f"Did not overwrite wave5b unless both windows also beat 496.98/861.11.\n"
        f"Artifact: `results/liveish_joint_hunt.json`.\n"
    )
    if digest.exists():
        digest.write_text(digest.read_text() + block)

    print("\n=== LIVEISH JOINT HUNT RESUME DONE ===", flush=True)
    print(json.dumps(state["summary"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
