#!/usr/bin/env python3
"""Targeted liveish joint hunt: compensating pairs around spread_frac=0.69.

Parent: wave5b_pull24_p46_sf672. Same --liveish flags as scripts/eval_sample.py --liveish and
scripts/eval_window.py --liveish (LIVEISH_CONFIG + LIVEISH_STRATEGY_CFG).

Protocol:
  mutate -> liveish sample -> if sample > 528.47 keep and run liveish 30d+60d
  promote only if both windows beat wave5b Aug10 gates (496.98 / 861.11)
  and sample > 528.47, soft_reject false, max_dd < 25, inv caps defensive.

Targeted exception (delta reporting only, not a promote path):
  compensating pairs with sample >= 505 still get 30d+60d so we can measure
  whether size/pause/pull fix the known 0.69 60d hole.
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

PY = str(ROOT / ".venv/bin/python")
OUT = ROOT / "results" / "liveish_joint_hunt.json"
PARENT = ROOT / "research" / "champions" / "strategy_wave5b_pull24_p46_sf672.py"
STRAT_TMP = ROOT / "research" / "agents" / "window-aware-hunt" / "strategy_joint_hunt.py"
DAYS_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
DAYS_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"
DAYS_90 = ROOT / "research" / "window_90d_days.txt"

CHAMP_SAMPLE = 528.47
CHAMP_30 = 496.98
CHAMP_60 = 861.11
SAMPLE_KEEP = 528.47  # official keep / window / promote sample gate
SAMPLE_DELTA_FLOOR = 505.0  # compensating family only: report windows
DD_LIMIT = 25.0

LIVEISH_STRATEGY_CFG = {
    "near_mid_size_mult": 0.5,
    "near_mid_dist": 0.02,
    "portfolio_inv_cap": 400.0,
    "cancel_move": 0.02,
}

PARENT_KNOBS = {
    "spread_frac": 0.672,
    "size_mult": 1.291,
    "inv_pause_ticks": 24,
    "pull_size_mult": 0.464,
    "skew_bps_per_share": 0.35,
    "mid_move_widen_mult": 1.6,
    "max_abs_inv": 100.0,
    "inv_soft_cap": 35.0,
}

# Structured compensating-pair grid (~28). All stay inv-defensive.
TRIALS = [
    # A. mild spread steps (closer to parent; more likely to pass sample gate)
    {"name": "spread_0p675", "mut": {"spread_frac": 0.675}, "family": "spread_step"},
    {"name": "spread_0p680", "mut": {"spread_frac": 0.68}, "family": "spread_step"},
    {"name": "spread_0p685", "mut": {"spread_frac": 0.685}, "family": "spread_step"},
    {"name": "spread_0p690", "mut": {"spread_frac": 0.69}, "family": "spread_step"},
    {"name": "spread_0p700", "mut": {"spread_frac": 0.70}, "family": "spread_step"},
    # B. 0.69 + smaller size
    {"name": "s069_size127", "mut": {"spread_frac": 0.69, "size_mult": 1.27}, "family": "spread_size"},
    {"name": "s069_size125", "mut": {"spread_frac": 0.69, "size_mult": 1.25}, "family": "spread_size"},
    {"name": "s069_size122", "mut": {"spread_frac": 0.69, "size_mult": 1.22}, "family": "spread_size"},
    {"name": "s068_size125", "mut": {"spread_frac": 0.68, "size_mult": 1.25}, "family": "spread_size"},
    # C. 0.69 + longer pause
    {"name": "s069_pause9", "mut": {"spread_frac": 0.69, "inv_pause_ticks": 9}, "family": "spread_pause"},
    {"name": "s069_pause10", "mut": {"spread_frac": 0.69, "inv_pause_ticks": 10}, "family": "spread_pause"},
    {"name": "s069_pause12", "mut": {"spread_frac": 0.69, "inv_pause_ticks": 12}, "family": "spread_pause"},
    {"name": "s068_pause10", "mut": {"spread_frac": 0.68, "inv_pause_ticks": 10}, "family": "spread_pause"},
    # D. 0.69 + tighter pull
    {"name": "s069_pull045", "mut": {"spread_frac": 0.69, "pull_size_mult": 0.45}, "family": "spread_pull"},
    {"name": "s069_pull040", "mut": {"spread_frac": 0.69, "pull_size_mult": 0.40}, "family": "spread_pull"},
    {"name": "s069_pull035", "mut": {"spread_frac": 0.69, "pull_size_mult": 0.35}, "family": "spread_pull"},
    {"name": "s068_pull040", "mut": {"spread_frac": 0.68, "pull_size_mult": 0.40}, "family": "spread_pull"},
    # E. triples / quads — the compensating pairs
    {"name": "s069_size125_pause10", "mut": {"spread_frac": 0.69, "size_mult": 1.25, "inv_pause_ticks": 10}, "family": "triple"},
    {"name": "s069_size125_pull040", "mut": {"spread_frac": 0.69, "size_mult": 1.25, "pull_size_mult": 0.40}, "family": "triple"},
    {"name": "s069_pause10_pull040", "mut": {"spread_frac": 0.69, "inv_pause_ticks": 10, "pull_size_mult": 0.40}, "family": "triple"},
    {"name": "s068_size125_pause10", "mut": {"spread_frac": 0.68, "size_mult": 1.25, "inv_pause_ticks": 10}, "family": "triple"},
    {"name": "s0685_size127_pause9_pull045", "mut": {"spread_frac": 0.685, "size_mult": 1.27, "inv_pause_ticks": 9, "pull_size_mult": 0.45}, "family": "quad"},
    {"name": "s069_size127_pause9_pull042", "mut": {"spread_frac": 0.69, "size_mult": 1.27, "inv_pause_ticks": 9, "pull_size_mult": 0.42}, "family": "quad"},
    {"name": "s070_size122_pause10_pull040", "mut": {"spread_frac": 0.70, "size_mult": 1.22, "inv_pause_ticks": 10, "pull_size_mult": 0.40}, "family": "quad"},
    # F. other compensators that might recover sample
    {"name": "s069_skew040", "mut": {"spread_frac": 0.69, "skew_bps_per_share": 0.40}, "family": "spread_skew"},
    {"name": "s069_widen18", "mut": {"spread_frac": 0.69, "mid_move_widen_mult": 1.8}, "family": "spread_widen"},
    {"name": "s068_skew040", "mut": {"spread_frac": 0.68, "skew_bps_per_share": 0.40}, "family": "spread_skew"},
    {"name": "s0675_size127_pause9", "mut": {"spread_frac": 0.675, "size_mult": 1.27, "inv_pause_ticks": 9}, "family": "triple"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_days(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def assemble_window(days: list[str], markets: list):
    from prepare import assemble_prices
    import pandas as pd

    frames = []
    for d in days:
        p = ROOT / "data" / "slim_days" / f"{d}.parquet"
        if not p.exists() or p.stat().st_size == 0:
            raise SystemExit(f"missing slim day: {p}")
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
        gc.collect()
    if not frames:
        raise SystemExit("no rows assembled")
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


def run_liveish(prices, markets, StratCls, overlay: dict, capital: float = 10_000.0) -> dict:
    strat_cfg = {**LIVEISH_STRATEGY_CFG, **overlay}
    strat = StratCls(strat_cfg)
    cfg = liveish_engine_config({"capital0": capital})
    eng = BacktestEngine(markets, strat, cfg)
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


def save(state: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.replace(OUT)


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


def do_promote(trial: dict) -> str:
    mut = trial["mut"]
    label = f"liveish_joint_{trial['name']}"
    named = ROOT / "research" / "champions" / f"strategy_{label}.py"
    shutil.copy2(PARENT, named)
    for k, v in mut.items():
        _patch_file(named, k, v)
    for dest in [
        ROOT / "research" / "champions" / "strategy_current_best.py",
        ROOT / "strategy.py",
    ]:
        shutil.copy2(named, dest)
    shutil.copy2(named, STRAT_TMP)

    promo = {
        "job": f"COMMANDER_promotion_{label}",
        "label": label,
        "parent": "wave5b_pull24_p46_sf672",
        "eval": "liveish",
        "mut": mut,
        "created_at": now_iso(),
        "gate_liveish_aug10": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "windows_liveish": {
            "sample": trial["sample_net_pnl"],
            "30d": trial["net_30d"],
            "60d": trial["net_60d"],
            "deltas": {
                "sample": trial.get("delta_sample"),
                "30d": trial.get("delta_30d"),
                "60d": trial.get("delta_60d"),
            },
        },
        "note": "Beats wave5b under SAME Aug10 liveish flags via compensating pair",
    }
    (ROOT / "results" / f"promotion_{label}.json").write_text(
        json.dumps(promo, indent=2, default=str)
    )

    (ROOT / "research" / "PROMOTION_GATE.md").write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish-validated Aug10 compensating pair)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

Mutations vs wave5b: `{json.dumps(mut)}`

| Window (LIVEISH) | Net PnL to beat |
|------------------|----------------:|
| sample | **{trial['sample_net_pnl']:.2f}** |
| 30d | **{trial['net_30d']:.2f}** |
| 60d | **{trial['net_60d']:.2f}** |

Prior wave5b Aug10 liveish: sample 528.47 / 30d 496.98 / 60d 861.11 (pool100 was 528.35/473.85/723.72)

## Rules
1. No optimistic-only promotes.
2. Same `--liveish` flags required.
3. Soft <=35, hard <=100.
4. To replace champion: both liveish-30d and liveish-60d must exceed these numbers, soft_reject false, max_dd_pct < 25.
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
        "parent": "wave5b_pull24_p46_sf672",
    }
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append(
            {
                "ts": data["updated_at"],
                "agent": "liveish-joint-hunt",
                "event": "promoted_liveish_aug10_joint",
                "label": label,
                "mut": mut,
                "sample": trial["sample_net_pnl"],
                "net_30d": trial["net_30d"],
                "net_60d": trial["net_60d"],
            }
        )
    path.write_text(json.dumps(data, indent=2, default=str))

    digest = ROOT / "results" / "overnight_digest.md"
    block = (
        f"\n\n## PROMOTED liveish joint hunt — {data['updated_at']}\n\n"
        f"Label `{label}`. Mut vs wave5b: `{json.dumps(mut)}`.\n\n"
        f"| Window | Net | vs pool100 |\n"
        f"|--------|----:|-----------:|\n"
        f"| sample | {trial['sample_net_pnl']:.2f} | {trial['delta_sample']:+.2f} |\n"
        f"| 30d | {trial['net_30d']:.2f} | {trial['delta_30d']:+.2f} |\n"
        f"| 60d | {trial['net_60d']:.2f} | {trial['delta_60d']:+.2f} |\n"
        f"\nChampion files synced. New liveish gate above.\n"
    )
    if digest.exists():
        digest.write_text(digest.read_text() + block)
    else:
        digest.write_text(block)
    return label


def mem_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        return -1.0
    return -1.0


def main() -> None:
    import pandas as pd
    from prepare import load_allowlist_markets

    t0 = time.time()
    print(f"liveish joint hunt start rss={mem_mb():.0f}MB", flush=True)
    print(f"gates sample>{CHAMP_SAMPLE} 30d>{CHAMP_30} 60d>{CHAMP_60}", flush=True)

    StratCls = load_strategy_class()
    markets_sample = json.loads((ROOT / "data" / "markets.json").read_text())
    markets_win = load_allowlist_markets()
    sample_prices = pd.read_parquet(ROOT / "data" / "research_sample_prices.parquet")
    print(f"sample rows={len(sample_prices)} rss={mem_mb():.0f}MB", flush=True)

    print("assembling 30d...", flush=True)
    prices_30 = assemble_window(load_days(DAYS_30), markets_win)
    print(f"30d rows={len(prices_30)} rss={mem_mb():.0f}MB", flush=True)
    print("assembling 60d...", flush=True)
    prices_60 = assemble_window(load_days(DAYS_60), markets_win)
    print(f"60d rows={len(prices_60)} rss={mem_mb():.0f}MB", flush=True)

    state = {
        "job": "liveish_joint_hunt",
        "parent": "research/champions/strategy_pool100.py",
        "eval": "liveish",
        "liveish_engine": {
            "quote_latency_rows": 1,
            "max_fill_frac": 0.40,
            "adverse_mid_cross_strength": 6.0,
            "fill_persist_rows": 1,
            "portfolio_inv_cap": 400,
            "use_trades": False,
        },
        "liveish_strategy": dict(LIVEISH_STRATEGY_CFG),
        "parent_knobs": dict(PARENT_KNOBS),
        "gate": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "protocol": {
            "sample_keep": SAMPLE_KEEP,
            "sample_delta_floor_compensating": SAMPLE_DELTA_FLOOR,
            "promote": "sample>528.47 AND 30d>496.98 AND 60d>861.11, soft_reject false",
            "n_planned": len(TRIALS),
        },
        "started_at": now_iso(),
        "trials": [],
        "promoted": False,
    }
    save(state)

    # sanity: parent overlay-only should ~tie sample
    print("sanity parent liveish sample...", flush=True)
    san = run_liveish(sample_prices, markets_sample, StratCls, {})
    state["parent_sanity_sample"] = san
    save(state)
    print(
        f"  parent sample={san['net_pnl']:.2f} fills={san['n_fills']} dd={san['max_dd_pct']}",
        flush=True,
    )
    gc.collect()

    best_joint = None  # max min(d30, d60) among windowed, or score
    best_score = None
    promoted = False

    for i, spec in enumerate(TRIALS, 1):
        mut = spec["mut"]
        # defensive inv floors
        if float(mut.get("max_abs_inv", 100)) > 100 or float(mut.get("inv_soft_cap", 35)) > 35:
            print(f"skip {spec['name']}: inv caps relaxed", flush=True)
            continue
        trial = {
            "try": i,
            "name": spec["name"],
            "family": spec["family"],
            "mut": mut,
            "parent_knobs": {k: PARENT_KNOBS.get(k) for k in mut},
            "ts": now_iso(),
            "eval": "liveish",
        }
        print(f"\n=== TRY {i}/{len(TRIALS)} {spec['name']} {mut} rss={mem_mb():.0f}MB ===", flush=True)

        t_s = time.time()
        s = run_liveish(sample_prices, markets_sample, StratCls, mut)
        sample_net = float(s["net_pnl"])
        trial.update(
            {
                "sample_net_pnl": sample_net,
                "sample_reward_pnl": s.get("reward_pnl"),
                "sample_trading_pnl": s.get("trading_pnl"),
                "sample_max_dd_pct": s.get("max_dd_pct"),
                "sample_soft_reject": s.get("soft_reject"),
                "sample_n_fills": s.get("n_fills"),
                "sample_elapsed_sec": round(time.time() - t_s, 3),
                "delta_sample": round(sample_net - CHAMP_SAMPLE, 4),
            }
        )
        print(
            f"  liveish sample={sample_net:.2f} (d{trial['delta_sample']:+.2f}) "
            f"dd={s.get('max_dd_pct')} fills={s.get('n_fills')}",
            flush=True,
        )
        gc.collect()

        keep = sample_net > SAMPLE_KEEP and not s.get("soft_reject")
        compensating = spec["family"] != "spread_step" or "spread_frac" in mut
        delta_only = (
            (not keep)
            and compensating
            and sample_net >= SAMPLE_DELTA_FLOOR
            and not s.get("soft_reject")
        )
        trial["keep"] = keep
        trial["delta_only_windows"] = bool(delta_only)

        if not keep and not delta_only:
            trial["status"] = "discard_sample"
            state["trials"].append(trial)
            save(state)
            print("  discard sample (not >528.47 and below compensating floor) -> skip windows", flush=True)
            continue

        why = "KEEP sample>528.47" if keep else f"delta-report sample>={SAMPLE_DELTA_FLOOR}"
        print(f"  {why} -> liveish 30d+60d", flush=True)

        t30 = time.time()
        w30 = run_liveish(prices_30, markets_win, StratCls, mut)
        gc.collect()
        t60 = time.time()
        w60 = run_liveish(prices_60, markets_win, StratCls, mut)
        gc.collect()

        n30 = float(w30["net_pnl"])
        n60 = float(w60["net_pnl"])
        trial.update(
            {
                "net_30d": n30,
                "net_60d": n60,
                "reward_30d": w30.get("reward_pnl"),
                "reward_60d": w60.get("reward_pnl"),
                "trading_30d": w30.get("trading_pnl"),
                "trading_60d": w60.get("trading_pnl"),
                "dd_30d": w30.get("max_dd_pct"),
                "dd_60d": w60.get("max_dd_pct"),
                "fills_30d": w30.get("n_fills"),
                "fills_60d": w60.get("n_fills"),
                "soft_30d": bool(w30.get("soft_reject")),
                "soft_60d": bool(w60.get("soft_reject")),
                "elapsed_30d": round(t60 - t30, 3),
                "elapsed_60d": round(time.time() - t60, 3),
                "delta_30d": round(n30 - CHAMP_30, 4),
                "delta_60d": round(n60 - CHAMP_60, 4),
                "score_sum": round(
                    (sample_net - CHAMP_SAMPLE) + (n30 - CHAMP_30) + (n60 - CHAMP_60), 4
                ),
                "score_min_window": round(min(n30 - CHAMP_30, n60 - CHAMP_60), 4),
            }
        )
        beats = (
            sample_net > CHAMP_SAMPLE
            and n30 > CHAMP_30
            and n60 > CHAMP_60
            and not trial["soft_30d"]
            and not trial["soft_60d"]
            and not s.get("soft_reject")
        )
        trial["beats_pool100_liveish"] = beats
        trial["promote_eligible"] = bool(beats and keep)
        print(
            f"  liveish 30d={n30:.2f} (d{trial['delta_30d']:+.2f})  "
            f"60d={n60:.2f} (d{trial['delta_60d']:+.2f})  "
            f"beats={beats} promote={trial['promote_eligible']}",
            flush=True,
        )

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
            trial["status"] = (
                "fail_liveish_windows"
                if keep
                else "windows_delta_only_sample_below_gate"
            )

        state["trials"].append(trial)
        save(state)

    elapsed = round(time.time() - t0, 1)
    pt = state["trials"]
    windowed = [t for t in pt if "net_30d" in t]
    both_pos = [
        t
        for t in windowed
        if (t.get("delta_30d") or 0) > 0 and (t.get("delta_60d") or 0) > 0
    ]
    state["summary"] = {
        "n_tried": len(pt),
        "n_window_eval": len(windowed),
        "n_keep_sample": sum(1 for t in pt if t.get("keep")),
        "n_discard_sample": sum(1 for t in pt if t.get("status") == "discard_sample"),
        "n_both_windows_positive": len(both_pos),
        "n_promoted": sum(1 for t in pt if t.get("status") == "PROMOTED"),
        "anything_beat_pool100_liveish": any(t.get("beats_pool100_liveish") for t in pt),
        "best_by_score_sum": state.get("best_by_score_sum"),
        "best_by_min_window_delta": state.get("best_by_min_window_delta"),
        "both_windows_positive": [
            {
                "name": t["name"],
                "mut": t["mut"],
                "sample": t.get("sample_net_pnl"),
                "d_sample": t.get("delta_sample"),
                "d30": t.get("delta_30d"),
                "d60": t.get("delta_60d"),
            }
            for t in both_pos
        ],
        "gate": state["gate"],
        "elapsed_sec": elapsed,
        "promoted": promoted,
    }
    state["finished_at"] = now_iso()
    save(state)

    # always append a hunt-complete finding (even if no promote)
    path = ROOT / "research" / "shared_findings.json"
    if path.exists():
        data = json.loads(path.read_text())
        data["updated_at"] = now_iso()
        findings = data.setdefault("findings", [])
        if isinstance(findings, list):
            findings.append(
                {
                    "ts": data["updated_at"],
                    "agent": "liveish-joint-hunt",
                    "event": "liveish_joint_hunt_complete",
                    "promoted": promoted,
                    "n_tried": len(pt),
                    "n_window_eval": len(windowed),
                    "n_both_windows_positive": len(both_pos),
                    "best_min_window": {
                        "name": (best_joint or {}).get("name"),
                        "mut": (best_joint or {}).get("mut"),
                        "d30": (best_joint or {}).get("delta_30d"),
                        "d60": (best_joint or {}).get("delta_60d"),
                        "sample": (best_joint or {}).get("sample_net_pnl"),
                    },
                    "note": "Compensating-pair hunt vs wave5b Aug10 liveish 496.98/861.11.",
                }
            )
        path.write_text(json.dumps(data, indent=2, default=str))

    digest = ROOT / "results" / "overnight_digest.md"
    best = best_joint or {}
    block = (
        f"\n\n## Liveish joint hunt (compensating pairs) — {state['finished_at']}\n\n"
        f"Parent pool100. {len(pt)} trials, {len(windowed)} window evals, "
        f"{len(both_pos)} both-windows-positive, promoted={promoted}. "
        f"Elapsed {elapsed}s.\n\n"
        f"Best min-window-delta: `{best.get('name')}` mut=`{json.dumps(best.get('mut'))}` "
        f"sample={best.get('sample_net_pnl')} d30={best.get('delta_30d')} d60={best.get('delta_60d')}.\n"
        f"Artifact: `results/liveish_joint_hunt.json`.\n"
    )
    if digest.exists():
        digest.write_text(digest.read_text() + block)

    print("\n=== LIVEISH JOINT HUNT DONE ===", flush=True)
    print(json.dumps(state["summary"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
