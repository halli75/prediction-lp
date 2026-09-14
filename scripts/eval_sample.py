#!/usr/bin/env python3
"""Evaluate Strategy once on the 12-day research sample (no holdout split)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

DD_LIMIT_PCT = 25.0
DEFAULT_PRICES = ROOT / "data" / "research_sample_prices.parquet"
DEFAULT_MARKETS = ROOT / "data" / "markets.json"


def load_strategy(module_path: Path | None):
    if module_path is None:
        from strategy import Strategy

        return Strategy()
    spec = importlib.util.spec_from_file_location("agent_strategy", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load strategy module: {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Strategy()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    ap.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    ap.add_argument(
        "--strategy-module",
        type=Path,
        default=None,
        help="Path to strategy.py (default: repo root strategy.py)",
    )
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--liveish", action="store_true",
                    help="stricter realism defaults (see research/LIVE_REALISM.md)")
    args = ap.parse_args()

    import pandas as pd

    t0 = time.time()
    if not args.prices.exists():
        print(
            json.dumps(
                {
                    "error": "no_prices",
                    "hint": "run scripts/build_research_sample.py first",
                    "prices": str(args.prices),
                }
            )
        )
        sys.exit(2)

    prices = pd.read_parquet(args.prices)
    with open(args.markets) as f:
        markets = json.load(f)

    if args.liveish:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "eval_liveish_mod", ROOT / "scripts" / "eval_liveish.py"
        )
        _mod = _ilu.module_from_spec(_spec)
        assert _spec.loader is not None
        _spec.loader.exec_module(_mod)
        StratCls = _mod.load_strategy_class(args.strategy_module)
        strat = StratCls(_mod.LIVEISH_STRATEGY_CFG)
        cfg = liveish_engine_config({"capital0": float(args.capital)})
    else:
        strat = load_strategy(args.strategy_module)
        cfg = {"capital0": float(args.capital), "use_trades": False}
    eng = BacktestEngine(markets, strat, cfg)
    m = eng.run(prices, None)
    elapsed = time.time() - t0

    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    out = {
        "sample_net_pnl": net,
        "net_pnl": net,
        "return_pct": round(net / float(args.capital) * 100.0, 4),
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "max_dd_pct": dd,
        "max_drawdown_pct": dd,
        "max_drawdown_usd": m.get("max_drawdown_usd"),
        "n_fills": m.get("n_fills"),
        "end_equity": m.get("end_equity"),
        "n_price_rows": int(len(prices)),
        "n_markets": len(markets),
        "n_markets_with_prices": int(prices["market_id"].nunique())
        if "market_id" in prices.columns
        else None,
        "capital0": float(args.capital),
        "soft_reject": dd > DD_LIMIT_PCT,
        "dd_limit_pct": DD_LIMIT_PCT,
        "primary_metric": "sample_net_pnl",
        "elapsed_sec": round(elapsed, 3),
        "prices": str(args.prices),
        "strategy_module": str(args.strategy_module or (ROOT / "strategy.py")),
        "liveish": bool(args.liveish),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
