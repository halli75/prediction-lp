#!/usr/bin/env python3
"""Evaluate Strategy on an arbitrary list of slim days (promotion to 30/60d)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prepare import assemble_prices, load_allowlist_markets  # noqa: E402
from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

DD_LIMIT_PCT = 25.0
SLIM = ROOT / "data" / "slim_days"


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


def parse_days(args) -> list[str]:
    if args.days_file:
        return [
            ln.strip()
            for ln in Path(args.days_file).read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    if args.days:
        return [d.strip() for d in args.days.split(",") if d.strip()]
    raise SystemExit("provide --days-file or --days")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-file", type=Path, default=None)
    ap.add_argument("--days", type=str, default=None, help="comma-separated YYYY-MM-DD")
    ap.add_argument("--strategy-module", type=Path, default=None)
    ap.add_argument("--markets", type=Path, default=ROOT / "data" / "markets.json")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--keep-prices",
        type=Path,
        default=None,
        help="optional path to write assembled prices parquet",
    )
    ap.add_argument("--liveish", action="store_true",
                    help="stricter realism defaults (see research/LIVE_REALISM.md)")
    args = ap.parse_args()

    days = parse_days(args)
    paths = []
    for d in days:
        p = SLIM / f"{d}.parquet"
        if not p.exists() or p.stat().st_size == 0:
            raise SystemExit(f"missing slim day: {p}")
        paths.append(p)

    t0 = time.time()
    if args.markets == ROOT / "data" / "markets.json":
        markets = load_allowlist_markets()
    else:
        with open(args.markets) as f:
            markets = json.load(f)

    # memory-light: one day at a time
    import pandas as pd

    frames = []
    for p in paths:
        part = assemble_prices([p], markets)
        if len(part):
            frames.append(part)
    if not frames:
        raise SystemExit("no rows assembled for window")
    prices = pd.concat(frames, ignore_index=True)
    del frames
    prices = (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )

    if args.keep_prices:
        prices.to_parquet(args.keep_prices, index=False)

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
        "window_net_pnl": net,
        "net_pnl": net,
        "return_pct": round(net / float(args.capital) * 100.0, 4),
        "reward_pnl": m.get("reward_pnl"),
        "trading_pnl": m.get("trading_pnl"),
        "max_dd_pct": dd,
        "max_drawdown_pct": dd,
        "n_fills": m.get("n_fills"),
        "n_days": len(days),
        "days": days,
        "n_price_rows": int(len(prices)),
        "n_markets": len(markets),
        "capital0": float(args.capital),
        "soft_reject": dd > DD_LIMIT_PCT,
        "dd_limit_pct": DD_LIMIT_PCT,
        "elapsed_sec": round(elapsed, 3),
        "strategy_module": str(args.strategy_module or (ROOT / "strategy.py")),
        "liveish": bool(args.liveish),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
