#!/usr/bin/env python3
"""
Fast evaluate on a fixed slice of the already-cached prices.parquet.

Does not download anything. Default: last 12 UTC days in the cache
(the same length the local swarm uses). Prints the same JSON shape as
evaluate.py so keep/discard scripts can parse holdout_net_pnl.

  python scripts/eval_sample.py
  python scripts/eval_sample.py --last-days 12 --config '{"cancel_move": 0.03}'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluate import DD_LIMIT_PCT, run_split
from sim.data import load_manifest, load_markets, load_prices, load_trades, train_holdout_split
from strategy import Strategy


def last_n_days(prices, n: int):
    ts = prices["ts"].astype("int64")
    days = sorted({datetime.fromtimestamp(int(t), timezone.utc).date().isoformat() for t in ts.unique()})
    keep = set(days[-n:]) if n > 0 else set(days)
    day_of = ts.map(lambda t: datetime.fromtimestamp(int(t), timezone.utc).date().isoformat())
    out = prices[day_of.isin(keep)].copy()
    return out, sorted(keep)


def evaluate_sample(
    last_days: int = 12,
    holdout_frac: float = 0.25,
    capital: float = 10_000.0,
    config: dict | None = None,
    prices=None,
    markets=None,
    trades=None,
    manifest=None,
) -> dict:
    if prices is None:
        prices = load_prices()
    if markets is None:
        markets = load_markets()
    if trades is None:
        trades = load_trades()
    if manifest is None:
        manifest = load_manifest()
    prices, days = last_n_days(prices, int(last_days))
    if prices.empty:
        return {"error": "no_prices_in_sample"}

    train, holdout = train_holdout_split(prices, holdout_frac=holdout_frac)
    cfg = {"capital0": float(capital), "use_trades": True}
    train_m = run_split("train", train, trades, markets, Strategy(config), cfg)
    hold_m = run_split("holdout", holdout, trades, markets, Strategy(config), cfg)
    soft = float(hold_m.get("holdout_max_drawdown_pct") or 0) > DD_LIMIT_PCT
    return {
        **train_m,
        **hold_m,
        "soft_reject": soft,
        "dd_limit_pct": DD_LIMIT_PCT,
        "capital0": capital,
        "holdout_frac": holdout_frac,
        "n_train_rows": int(len(train)),
        "n_holdout_rows": int(len(holdout)),
        "n_markets": len(markets),
        "data_mode": "sample_" + str(manifest.get("mode")),
        "data_days": days,
        "sample_last_days": int(last_days),
        "primary_metric": "holdout_net_pnl",
        "holdout_net_pnl": hold_m.get("holdout_net_pnl"),
        "strategy_config": config or {},
    }


def _slim(m: dict) -> dict:
    keys = (
        "holdout_net_pnl",
        "holdout_max_drawdown_pct",
        "holdout_trading_pnl",
        "holdout_reward_pnl",
        "holdout_n_fills",
        "train_net_pnl",
        "train_max_drawdown_pct",
        "soft_reject",
        "n_train_rows",
        "n_holdout_rows",
        "data_days",
        "strategy_config",
    )
    return {k: m.get(k) for k in keys}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last-days", type=int, default=12)
    ap.add_argument("--holdout-frac", type=float, default=0.25)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--config", type=str, default="", help="JSON object of Strategy() overrides")
    ap.add_argument("--sweep", action="store_true", help="run a small defense-knob sweep (loads cache once)")
    args = ap.parse_args()

    config = json.loads(args.config) if args.config.strip() else None
    if args.sweep:
        prices = load_prices()
        markets = load_markets()
        trades = load_trades()
        manifest = load_manifest()
        variants = [
            {"name": "defaults"},
            {"name": "no_cancel", "cancel_move": 1.0},
            {"name": "tight_cancel", "cancel_move": 0.015},
            {"name": "wide_cancel", "cancel_move": 0.04},
            {"name": "short_pause", "pause_secs": 300.0},
            {"name": "long_pause", "pause_secs": 1800.0},
            {"name": "no_shrink", "near_mid_size_frac": 1.0},
            {"name": "hard_shrink", "near_mid_size_frac": 0.35},
            {"name": "loose_port", "portfolio_inv_cap": 8000.0},
            {"name": "tight_port", "portfolio_inv_cap": 2500.0},
            {"name": "no_reserve", "cash_reserve_frac": 0.0},
        ]
        rows = []
        for v in variants:
            name = v.pop("name")
            m = evaluate_sample(
                last_days=int(args.last_days),
                holdout_frac=float(args.holdout_frac),
                capital=float(args.capital),
                config=v or None,
                prices=prices,
                markets=markets,
                trades=trades,
                manifest=manifest,
            )
            slim = _slim(m)
            slim["name"] = name
            rows.append(slim)
            print(json.dumps(slim, default=str), flush=True)
        best = max(rows, key=lambda r: (not r.get("soft_reject"), r.get("holdout_net_pnl") or -1e18))
        print(json.dumps({"best": best}, indent=2, default=str))
        return

    out = evaluate_sample(
        last_days=int(args.last_days),
        holdout_frac=float(args.holdout_frac),
        capital=float(args.capital),
        config=config,
    )
    if out.get("error"):
        print(json.dumps(out))
        sys.exit(2)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
