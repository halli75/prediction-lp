#!/usr/bin/env python3
"""
Compare baseline (optimistic) vs liveish (stricter realism) engine configs
on the 12-day research sample and the 30d window for current strategy.py.

Usage:
  .venv/bin/python scripts/eval_liveish.py
  .venv/bin/python scripts/eval_liveish.py --also-60d
  .venv/bin/python scripts/eval_liveish.py --strategy-module path/to/strategy.py

Writes:
  results/liveish_vs_baseline.json
  results/liveish_delta.md
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine, LIVEISH_CONFIG, liveish_engine_config  # noqa: E402

DD_LIMIT_PCT = 25.0
DEFAULT_PRICES = ROOT / "data" / "research_sample_prices.parquet"
DEFAULT_MARKETS = ROOT / "data" / "markets.json"
SLIM = ROOT / "data" / "slim_days"

# Mild live-bot strategy defenses (champion numeric knobs unchanged)
LIVEISH_STRATEGY_CFG = {
    "near_mid_size_mult": 0.5,
    "near_mid_dist": 0.02,
    "portfolio_inv_cap": 400.0,
    "cancel_move": 0.02,
}


def load_strategy_class(module_path: Path | None):
    if module_path is None:
        from strategy import Strategy

        return Strategy
    spec = importlib.util.spec_from_file_location("agent_strategy", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load strategy module: {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Strategy


def load_days(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def assemble_window(days: list[str], markets: list) -> "pd.DataFrame":
    from prepare import assemble_prices
    import pandas as pd

    frames = []
    for d in days:
        p = SLIM / f"{d}.parquet"
        if not p.exists() or p.stat().st_size == 0:
            raise SystemExit(f"missing slim day: {p}")
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
        gc.collect()
    if not frames:
        raise SystemExit("no rows assembled for window")
    prices = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    return (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )


def run_one(
    prices,
    markets,
    StratCls,
    *,
    liveish: bool,
    capital: float,
) -> dict:
    if liveish:
        eng_cfg = liveish_engine_config({"capital0": capital})
        strat = StratCls(LIVEISH_STRATEGY_CFG)
    else:
        eng_cfg = {"capital0": capital, "use_trades": False}
        strat = StratCls()
    eng = BacktestEngine(markets, strat, eng_cfg)
    m = eng.run(prices, None)
    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    return {
        "net_pnl": net,
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "max_dd_pct": dd,
        "max_drawdown_usd": m.get("max_drawdown_usd"),
        "n_fills": m.get("n_fills"),
        "end_equity": m.get("end_equity"),
        "soft_reject": dd > DD_LIMIT_PCT,
        "realism": m.get("realism"),
        "engine_cfg": {
            k: eng_cfg.get(k)
            for k in (
                "quote_latency_rows",
                "max_fill_frac",
                "adverse_mid_cross_strength",
                "fill_persist_rows",
                "portfolio_inv_cap",
                "use_trades",
            )
            if k in eng_cfg or liveish
        },
        "strategy_cfg": LIVEISH_STRATEGY_CFG if liveish else {},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-module", type=Path, default=None)
    ap.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    ap.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--also-60d", action="store_true")
    ap.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "results" / "liveish_vs_baseline.json",
    )
    ap.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "results" / "liveish_delta.md",
    )
    args = ap.parse_args()

    import pandas as pd
    from prepare import load_allowlist_markets

    t0 = time.time()
    StratCls = load_strategy_class(args.strategy_module)

    if args.markets == DEFAULT_MARKETS or args.markets == ROOT / "data" / "markets.json":
        try:
            markets = load_allowlist_markets()
        except Exception:
            with open(args.markets) as f:
                markets = json.load(f)
    else:
        with open(args.markets) as f:
            markets = json.load(f)

    if not args.prices.exists():
        print(json.dumps({"error": "no_prices", "prices": str(args.prices)}))
        sys.exit(2)

    sample_prices = pd.read_parquet(args.prices)
    out: dict = {
        "strategy_module": str(args.strategy_module or (ROOT / "strategy.py")),
        "capital0": float(args.capital),
        "liveish_engine": dict(LIVEISH_CONFIG),
        "liveish_strategy": dict(LIVEISH_STRATEGY_CFG),
        "champion_optimistic_gate": {
            "label": "pool100",
            "min_daily_reward_pool": 100.0,
            "sample": 1673.11,
            "30d": 2734.01,
            "60d": 2604.43,
            "prior_pool150": {"sample": 1197.56, "30d": 2083.31, "60d": 1913.93},
        },
        "windows": {},
    }

    # --- sample ---
    print("running sample baseline...", flush=True)
    base_s = run_one(sample_prices, markets, StratCls, liveish=False, capital=args.capital)
    gc.collect()
    print("running sample liveish...", flush=True)
    live_s = run_one(sample_prices, markets, StratCls, liveish=True, capital=args.capital)
    gc.collect()
    out["windows"]["sample"] = {
        "baseline": base_s,
        "liveish": live_s,
        "delta_net_pnl": round(live_s["net_pnl"] - base_s["net_pnl"], 4),
        "n_price_rows": int(len(sample_prices)),
    }
    del sample_prices
    gc.collect()

    # --- 30d ---
    days_30 = load_days(ROOT / "research" / "window_30d_days.txt")
    print(f"assembling 30d ({len(days_30)} days)...", flush=True)
    prices_30 = assemble_window(days_30, markets)
    print("running 30d baseline...", flush=True)
    base_30 = run_one(prices_30, markets, StratCls, liveish=False, capital=args.capital)
    gc.collect()
    print("running 30d liveish...", flush=True)
    live_30 = run_one(prices_30, markets, StratCls, liveish=True, capital=args.capital)
    gc.collect()
    out["windows"]["30d"] = {
        "baseline": base_30,
        "liveish": live_30,
        "delta_net_pnl": round(live_30["net_pnl"] - base_30["net_pnl"], 4),
        "n_days": len(days_30),
        "n_price_rows": int(len(prices_30)),
    }
    del prices_30
    gc.collect()

    if args.also_60d:
        days_60 = load_days(ROOT / "research" / "window_60d_days.txt")
        print(f"assembling 60d ({len(days_60)} days)...", flush=True)
        prices_60 = assemble_window(days_60, markets)
        print("running 60d baseline...", flush=True)
        base_60 = run_one(prices_60, markets, StratCls, liveish=False, capital=args.capital)
        gc.collect()
        print("running 60d liveish...", flush=True)
        live_60 = run_one(prices_60, markets, StratCls, liveish=True, capital=args.capital)
        gc.collect()
        out["windows"]["60d"] = {
            "baseline": base_60,
            "liveish": live_60,
            "delta_net_pnl": round(live_60["net_pnl"] - base_60["net_pnl"], 4),
            "n_days": len(days_60),
            "n_price_rows": int(len(prices_60)),
        }
        del prices_60
        gc.collect()

    out["elapsed_sec"] = round(time.time() - t0, 3)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2, default=str))

    # Short markdown delta
    lines = [
        "# Liveish vs baseline",
        "",
        f"Strategy: `{out['strategy_module']}`",
        f"Elapsed: {out['elapsed_sec']}s",
        "",
        "Liveish engine flags:",
        "```",
        json.dumps(LIVEISH_CONFIG, indent=2),
        "```",
        "",
        "| Window | Baseline net | Liveish net | Δ | Baseline DD% | Liveish DD% | Liveish fills |",
        "|--------|-------------:|------------:|--:|-------------:|------------:|--------------:|",
    ]
    for wname, w in out["windows"].items():
        b, l = w["baseline"], w["liveish"]
        lines.append(
            f"| {wname} | {b['net_pnl']:.2f} | {l['net_pnl']:.2f} | "
            f"{w['delta_net_pnl']:.2f} | {b['max_dd_pct']:.2f} | {l['max_dd_pct']:.2f} | "
            f"{l['n_fills']} |"
        )
    gate = out["champion_optimistic_gate"]
    lines.extend(
        [
            "",
            "## Vs champion optimistic gate (pool100)",
            "",
            f"| Window | Optimistic gate | Baseline (this run) | Liveish | Liveish − gate |",
            f"|--------|----------------:|--------------------:|--------:|---------------:|",
        ]
    )
    for wname, gkey in (("sample", "sample"), ("30d", "30d"), ("60d", "60d")):
        if wname not in out["windows"]:
            continue
        w = out["windows"][wname]
        g = float(gate[gkey])
        b = w["baseline"]["net_pnl"]
        l = w["liveish"]["net_pnl"]
        lines.append(
            f"| {wname} | {g:.2f} | {b:.2f} | {l:.2f} | {l - g:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- Liveish should usually show **lower** net PnL and/or fewer optimistic fills than baseline.",
            "- Report deltas vs **both** optimistic baseline (same run) and the pool100 optimistic gate.",
            "- Use liveish numbers for actionable overnight decisions; optimistic gate remains in PROMOTION_GATE.md.",
            "- Do not promote over pool100 unless liveish-30d **and** liveish-60d both beat pool100 under the same flags.",
            "",
        ]
    )
    args.out_md.write_text("\n".join(lines))

    print(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {args.out_json}", flush=True)
    print(f"wrote {args.out_md}", flush=True)


if __name__ == "__main__":
    main()
