#!/usr/bin/env python3
"""Evaluate the pool150 champion Strategy on one market allowlist.

Non-destructive: does not edit strategy.py. Applies allowlist + optional
min_daily_reward_pool at runtime. Filters prices/markets to the set to save RAM.

Usage:
  python scripts/eval_market_set.py --set research/market_sets/top5.json
  python scripts/eval_market_set.py --set research/market_sets/top5.json \\
      --days-file research/window_30d_days.txt --out results/foo.json
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine  # noqa: E402

DD_LIMIT_PCT = 25.0
DEFAULT_PRICES = ROOT / "data" / "research_sample_prices.parquet"
DEFAULT_MARKETS = ROOT / "data" / "markets.json"
SLIM = ROOT / "data" / "slim_days"


def parse_days(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def load_set(path: Path) -> dict:
    rec = json.loads(path.read_text())
    if "market_ids" not in rec:
        raise SystemExit(f"set file missing market_ids: {path}")
    return rec


def apply_set_to_strategy(strat, rec: dict) -> None:
    ids = [str(x) for x in rec["market_ids"]]
    strat._market_allowlist = set(ids)
    # Named allowlists (min_pool==0): allowlist is the only filter.
    # Pool-threshold sets: also enforce that pool floor (matches champion knob).
    min_pool = float(rec.get("min_pool") or 0.0)
    strat.min_daily_reward_pool = min_pool
    strat.enforce_pool_allowlist = True


def load_window_prices(days: list[str], markets: list[dict]):
    from prepare import assemble_prices
    import pandas as pd

    paths = []
    for d in days:
        p = SLIM / f"{d}.parquet"
        if not p.exists() or p.stat().st_size == 0:
            raise SystemExit(f"missing slim day: {p}")
        paths.append(p)
    frames = []
    for p in paths:
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
        del part
        gc.collect()
    if not frames:
        raise SystemExit("no rows assembled for window")
    prices = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    prices = (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )
    return prices


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", type=Path, required=True, help="research/market_sets/<name>.json")
    ap.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    ap.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    ap.add_argument("--days-file", type=Path, default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rec = load_set(args.set)
    allow = set(str(x) for x in rec["market_ids"])

    import pandas as pd
    from strategy import Strategy

    t0 = time.time()
    with open(args.markets) as f:
        markets_all = json.load(f)
    markets = [m for m in markets_all if str(m["market_id"]) in allow]
    if not markets:
        raise SystemExit(f"no markets matched allowlist in {args.set}")

    window = None
    days = None
    if args.days_file:
        days = parse_days(args.days_file)
        prices = load_window_prices(days, markets)
        window = f"{len(days)}d"
    else:
        if not args.prices.exists():
            print(json.dumps({"error": "no_prices", "prices": str(args.prices)}))
            sys.exit(2)
        prices = pd.read_parquet(args.prices)
        if "market_id" in prices.columns:
            prices = prices[prices["market_id"].astype(str).isin(allow)].copy()
        window = "sample"

    strat = Strategy()
    apply_set_to_strategy(strat, rec)

    eng = BacktestEngine(markets, strat, {"capital0": float(args.capital), "use_trades": False})
    m = eng.run(prices, None)
    elapsed = time.time() - t0

    net = float(m.get("net_pnl") or 0.0)
    dd = float(m.get("max_drawdown_pct") or 0.0)
    out = {
        "set_name": rec.get("name"),
        "set_kind": rec.get("kind"),
        "set_n": rec.get("n"),
        "set_min_pool": rec.get("min_pool"),
        "set_path": str(args.set),
        "window": window,
        "n_days": len(days) if days else None,
        "days": days,
        "sample_net_pnl": net if window == "sample" else None,
        "window_net_pnl": net if window != "sample" else None,
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
        "n_markets_in_set": len(markets),
        "n_markets_with_prices": int(prices["market_id"].nunique()) if "market_id" in prices.columns else None,
        "capital0": float(args.capital),
        "soft_reject": dd > DD_LIMIT_PCT,
        "dd_limit_pct": DD_LIMIT_PCT,
        "elapsed_sec": round(elapsed, 3),
        "strategy": "pool150_champion",
        "champion_knobs_held": {
            "spread_frac": 0.6676,
            "size_mult": 1.291,
            "inv_soft_cap": 35.0,
            "max_abs_inv": 100.0,
        },
        "applied_min_daily_reward_pool": float(rec.get("min_pool") or 0.0),
        "market_ids": rec.get("market_ids"),
    }
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")

    del prices, eng, strat
    gc.collect()


if __name__ == "__main__":
    main()
