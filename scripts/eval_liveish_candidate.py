#!/usr/bin/env python3
"""Eval one candidate under liveish engine + LIVEISH_STRATEGY_CFG with optional overlay."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

DD_LIMIT_PCT = 25.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sample", "window"], required=True)
    ap.add_argument("--strategy-module", type=Path, required=True)
    ap.add_argument("--overlay-json", type=str, default="{}")
    ap.add_argument("--days-file", type=Path, default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args()

    import importlib.util as ilu

    spec = ilu.spec_from_file_location("eval_liveish_mod", ROOT / "scripts" / "eval_liveish.py")
    mod = ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    overlay = json.loads(args.overlay_json)
    strat_cfg = {**mod.LIVEISH_STRATEGY_CFG, **overlay}
    StratCls = mod.load_strategy_class(args.strategy_module)
    strat = StratCls(strat_cfg)
    cfg = liveish_engine_config({"capital0": float(args.capital)})

    import pandas as pd
    import time

    t0 = time.time()
    if args.mode == "sample":
        prices = pd.read_parquet(ROOT / "data" / "research_sample_prices.parquet")
        with open(ROOT / "data" / "markets.json") as f:
            markets = json.load(f)
    else:
        if not args.days_file:
            raise SystemExit("--days-file required for window mode")
        from prepare import assemble_prices, load_allowlist_markets

        days = [
            ln.strip()
            for ln in args.days_file.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        markets = load_allowlist_markets()
        frames = []
        for d in days:
            p = ROOT / "data" / "slim_days" / f"{d}.parquet"
            part = assemble_prices([p], markets)
            if len(part):
                frames.append(part)
        prices = (
            pd.concat(frames, ignore_index=True)
            .sort_values(["ts", "market_id"])
            .drop_duplicates(["ts", "market_id"], keep="last")
            .reset_index(drop=True)
        )

    eng = BacktestEngine(markets, strat, cfg)
    m = eng.run(prices, None)
    elapsed = time.time() - t0
    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    out = {
        "sample_net_pnl": net,
        "window_net_pnl": net,
        "net_pnl": net,
        "max_dd_pct": dd,
        "max_drawdown_pct": dd,
        "n_fills": m.get("n_fills"),
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "soft_reject": dd > DD_LIMIT_PCT,
        "elapsed_sec": round(elapsed, 3),
        "liveish": True,
        "strategy_overlay": overlay,
        "strategy_module": str(args.strategy_module),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
