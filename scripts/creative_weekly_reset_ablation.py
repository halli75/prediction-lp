#!/usr/bin/env python3
"""
Deploy-policy ablation (no strategy change):
  Sum PnL of independent $10k weekly (7-day) resets across archive
  vs one continuous run on 60d / 90d / full available.

Writes:
  results/creative_weekly_reset_ablation.json
  results/creative_weekly_reset_ablation.md
"""
from __future__ import annotations

import gc
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prepare import assemble_prices, load_allowlist_markets  # noqa: E402
from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

DD_LIMIT = 25.0
SLIM = ROOT / "data" / "slim_days"
CHAMP = ROOT / "research" / "champions" / "strategy_wave5b_pull24_p46_sf672.py"
OUT_JSON = ROOT / "results" / "creative_weekly_reset_ablation.json"
OUT_MD = ROOT / "results" / "creative_weekly_reset_ablation.md"


def load_days(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def load_strategy_class(module_path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("ablation_strat", module_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.Strategy


def liveish_strat_cfg():
    import importlib.util as ilu

    spec = ilu.spec_from_file_location("el", ROOT / "scripts" / "eval_liveish.py")
    mod = ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return dict(mod.LIVEISH_STRATEGY_CFG)


def assemble(days: list[str], markets: list):
    import pandas as pd

    frames = []
    for d in days:
        p = SLIM / f"{d}.parquet"
        if not p.exists() or p.stat().st_size == 0:
            continue
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
        gc.collect()
    if not frames:
        return None
    prices = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    return (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )


def run_window(days: list[str], markets, StratCls, strat_cfg, capital=10_000.0) -> dict:
    prices = assemble(days, markets)
    if prices is None or len(prices) == 0:
        return {"error": "no_prices", "days": days}
    eng = BacktestEngine(markets, StratCls(strat_cfg), liveish_engine_config({"capital0": capital}))
    m = eng.run(prices, None)
    del prices
    gc.collect()
    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    return {
        "net_pnl": net,
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "max_dd_pct": dd,
        "soft_reject": dd > DD_LIMIT,
        "n_fills": m.get("n_fills"),
        "n_days": len(days),
        "day_start": days[0],
        "day_end": days[-1],
    }


def chunk_weeks(days: list[str], week_len: int = 7) -> list[list[str]]:
    return [days[i : i + week_len] for i in range(0, len(days), week_len) if days[i : i + week_len]]


def main() -> None:
    t0 = time.time()
    markets = load_allowlist_markets()
    StratCls = load_strategy_class(CHAMP)
    strat_cfg = liveish_strat_cfg()

    full_days = load_days(ROOT / "research" / "window_full_available_days.txt")
    days_60 = load_days(ROOT / "research" / "window_60d_liveish_gate_days.txt")
    days_90 = load_days(ROOT / "research" / "window_90d_days.txt")

    print(f"[ablation] full={len(full_days)} 60d={len(days_60)} 90d={len(days_90)}", flush=True)

    # Continuous baselines
    print("[ablation] continuous 60d...", flush=True)
    cont_60 = run_window(days_60, markets, StratCls, strat_cfg)
    print(f"  cont60={cont_60.get('net_pnl')}", flush=True)

    print("[ablation] continuous 90d...", flush=True)
    cont_90 = run_window(days_90, markets, StratCls, strat_cfg)
    print(f"  cont90={cont_90.get('net_pnl')}", flush=True)

    print("[ablation] continuous full...", flush=True)
    cont_full = run_window(full_days, markets, StratCls, strat_cfg)
    print(f"  cont_full={cont_full.get('net_pnl')}", flush=True)

    # Weekly resets on full archive
    weeks = chunk_weeks(full_days, 7)
    week_rows = []
    for i, wdays in enumerate(weeks):
        print(f"[ablation] week {i+1}/{len(weeks)} {wdays[0]}..{wdays[-1]} ({len(wdays)}d)", flush=True)
        row = run_window(wdays, markets, StratCls, strat_cfg)
        row["week_index"] = i
        week_rows.append(row)
        print(f"  -> {row.get('net_pnl')}", flush=True)

    sum_weeks = sum(float(r.get("net_pnl") or 0.0) for r in week_rows if not r.get("error"))
    # Also weekly on 60d window only
    weeks_60 = chunk_weeks(days_60, 7)
    week60_rows = []
    for i, wdays in enumerate(weeks_60):
        print(f"[ablation] 60d-week {i+1}/{len(weeks_60)}", flush=True)
        row = run_window(wdays, markets, StratCls, strat_cfg)
        row["week_index"] = i
        week60_rows.append(row)
    sum_weeks_60 = sum(float(r.get("net_pnl") or 0.0) for r in week60_rows if not r.get("error"))

    out = {
        "job": "creative_weekly_reset_ablation",
        "strategy": "wave5b_pull24_p46_sf672",
        "liveish": True,
        "capital_per_book": 10000.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.time() - t0, 2),
        "continuous": {
            "60d": cont_60,
            "90d": cont_90,
            "full_83d": cont_full,
        },
        "weekly_resets_full": {
            "n_weeks": len(week_rows),
            "week_len": 7,
            "weeks": week_rows,
            "sum_net_pnl": sum_weeks,
        },
        "weekly_resets_60d": {
            "n_weeks": len(week60_rows),
            "weeks": week60_rows,
            "sum_net_pnl": sum_weeks_60,
        },
        "headline": {
            "sum_weekly_full_vs_continuous_full": {
                "sum_weekly": sum_weeks,
                "continuous": cont_full.get("net_pnl"),
                "delta_weekly_minus_cont": sum_weeks - float(cont_full.get("net_pnl") or 0.0),
            },
            "sum_weekly_60_vs_continuous_60": {
                "sum_weekly": sum_weeks_60,
                "continuous": cont_60.get("net_pnl"),
                "delta_weekly_minus_cont": sum_weeks_60 - float(cont_60.get("net_pnl") or 0.0),
            },
            "sum_weekly_full_vs_continuous_90": {
                "sum_weekly_full": sum_weeks,
                "continuous_90": cont_90.get("net_pnl"),
            },
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))

    h = out["headline"]
    md = f"""# Creative weekly-reset ablation (ops lever)

Strategy: champion `wave5b_pull24_p46_sf672` under liveish. No strategy change — only deploy policy.

## Headline

| Comparison | Weekly sum | Continuous | Δ (weekly − cont) |
|------------|----------:|-----------:|------------------:|
| Full archive (~83d) | **{sum_weeks:.2f}** | **{float(cont_full.get('net_pnl') or 0):.2f}** | **{h['sum_weekly_full_vs_continuous_full']['delta_weekly_minus_cont']:.2f}** |
| 60d gate window | **{sum_weeks_60:.2f}** | **{float(cont_60.get('net_pnl') or 0):.2f}** | **{h['sum_weekly_60_vs_continuous_60']['delta_weekly_minus_cont']:.2f}** |
| 90d continuous (ref) | (full weekly {sum_weeks:.2f}) | **{float(cont_90.get('net_pnl') or 0):.2f}** | — |

Independent **$10k** capital reset each 7-day chunk. Continuous = one book across the window.

## Interpretation

- If weekly sum >> continuous: path-dependent inventory bleed dominates; **restart book weekly** is a creative ops lever.
- If weekly ≈ continuous: toxicity is within-week; structural flatten modes matter more than resets.

## Week detail (full archive)

| week | start | end | n_days | net_pnl | dd% |
|-----:|-------|-----|-------:|--------:|----:|
"""
    for r in week_rows:
        md += (
            f"| {r.get('week_index')} | {r.get('day_start')} | {r.get('day_end')} | "
            f"{r.get('n_days')} | {float(r.get('net_pnl') or 0):.2f} | {float(r.get('max_dd_pct') or 0):.2f} |\n"
        )
    md += f"\nArtifact: `{OUT_JSON.relative_to(ROOT)}`\n"
    OUT_MD.write_text(md)
    print(json.dumps(out["headline"], indent=2), flush=True)
    print("[ablation] done", flush=True)


if __name__ == "__main__":
    main()
