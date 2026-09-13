#!/usr/bin/env python3
"""
Fixed evaluation harness.

Loads cached data from prepare.py, runs Strategy on train + holdout,
prints a single JSON object to stdout, and exits non-zero on hard failures.

Soft-reject (max DD > 25% of capital) is reported as soft_reject=true but
still returns metrics (autoresearch decides keep/discard).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sim.data import load_manifest, load_markets, load_prices, load_trades, train_holdout_split
from sim.engine import BacktestEngine
from strategy import Strategy


DD_LIMIT_PCT = 25.0


def run_split(name: str, prices, trades, markets, strategy, config) -> dict:
    eng = BacktestEngine(markets, strategy, config)
    m = eng.run(prices, trades)
    return {f"{name}_{k}": v for k, v in m.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout-frac", type=float, default=0.25)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--fixture", action="store_true", help="Use fixtures/ tiny data")
    ap.add_argument("--no-trades", action="store_true")
    args = ap.parse_args()

    if args.fixture:
        data_dir = ROOT / "fixtures"
        prices = __import__("pandas").read_parquet(data_dir / "prices.parquet")
        with open(data_dir / "markets.json") as f:
            markets = json.load(f)
        trades = None
        manifest = {"mode": "fixture"}
    else:
        prices = load_prices()
        markets = load_markets()
        trades = None if args.no_trades else load_trades()
        manifest = load_manifest()

    if prices is None or len(prices) == 0:
        print(json.dumps({"error": "no_prices", "hint": "run prepare.py first"}))
        sys.exit(2)

    train, holdout = train_holdout_split(prices, holdout_frac=args.holdout_frac)
    cfg = {"capital0": float(args.capital), "use_trades": not args.no_trades}

    strat = Strategy()
    train_m = run_split("train", train, trades, markets, strat, cfg)
    # Fresh strategy instance for holdout (no leaked state)
    strat_h = Strategy()
    hold_m = run_split("holdout", holdout, trades, markets, strat_h, cfg)

    soft = float(hold_m.get("holdout_max_drawdown_pct") or 0) > DD_LIMIT_PCT
    out = {
        **train_m,
        **hold_m,
        "soft_reject": soft,
        "dd_limit_pct": DD_LIMIT_PCT,
        "capital0": args.capital,
        "holdout_frac": args.holdout_frac,
        "n_train_rows": int(len(train)),
        "n_holdout_rows": int(len(holdout)),
        "n_markets": len(markets),
        "data_mode": manifest.get("mode"),
        "data_days": manifest.get("days"),
        "data_start_iso": manifest.get("start_iso"),
        "data_end_iso": manifest.get("end_iso"),
        "primary_metric": "holdout_net_pnl",
        "holdout_net_pnl": hold_m.get("holdout_net_pnl"),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
