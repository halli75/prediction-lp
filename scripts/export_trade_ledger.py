#!/usr/bin/env python3
"""Export human-readable fill + round-trip trade ledgers for a liveish backtest.

Usage:
  .venv/bin/python scripts/export_trade_ledger.py
  .venv/bin/python scripts/export_trade_ledger.py --days-file research/window_30d_days.txt --tag 30d
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.engine import BacktestEngine, liveish_engine_config  # noqa: E402

DEFAULT_OVERLAY = {
    "day_flatten": True,
    "day_flatten_max_net": 8,
    "min_daily_reward_pool": 110,
}
DEFAULT_STRATEGY = ROOT / "research" / "champions" / "strategy_current_best.py"
DEFAULT_DAYS = ROOT / "research" / "window_90d_days.txt"
OUT_DIR = ROOT / "results" / "ledgers"


def load_eval_liveish():
    import importlib.util as ilu

    spec = ilu.spec_from_file_location("eval_liveish_mod", ROOT / "scripts" / "eval_liveish.py")
    mod = ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def assemble_window(days: list[str], markets: list) -> "pd.DataFrame":
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
        raise SystemExit("no rows assembled for window")
    prices = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()
    return (
        prices.sort_values(["ts", "market_id"])
        .drop_duplicates(["ts", "market_id"], keep="last")
        .reset_index(drop=True)
    )


def load_days(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def edge_vs_mid_cents(side: str, price: float, mid: float) -> float:
    if mid != mid:  # NaN
        return float("nan")
    if side == "buy_yes":
        return (mid - price) * 100.0
    return (price - mid) * 100.0


def action_plain(side: str) -> str:
    if side == "buy_yes":
        return "Bought YES (bid hit)"
    return "Sold YES (ask lifted)"


def fills_to_dataframe(raw_fills: list[dict[str, Any]]):
    import pandas as pd

    rows = []
    for i, f in enumerate(raw_fills, start=1):
        mid = float(f.get("mid_at_fill") or float("nan"))
        price = float(f["price"])
        size = float(f["size"])
        side = str(f["side"])
        ts = int(f["ts"])
        dt = pd.Timestamp(ts, unit="s", tz="UTC")
        mid_id = str(f["market_id"])
        inv_yes = float(f["inv_yes_after"])
        inv_no = float(f["inv_no_after"])
        rows.append(
            {
                "fill_id": i,
                "datetime_utc": dt.isoformat(),
                "date": str(dt.date()),
                "market_question": f.get("question") or "",
                "market_id_short": mid_id[:10],
                "market_id": mid_id,
                "side": side,
                "action": f.get("action") or ("BUY_YES" if side == "buy_yes" else "SELL_YES"),
                "action_plain": action_plain(side),
                "size_shares": round(size, 6),
                "price": round(price, 4),
                "notional_usd": round(float(f.get("notional", size * price)), 4),
                "mid": round(mid, 4) if mid == mid else None,
                "edge_vs_mid_cents": round(edge_vs_mid_cents(side, price, mid), 4)
                if mid == mid
                else None,
                "inv_yes_after": round(inv_yes, 6),
                "inv_no_after": round(inv_no, 6),
                "net_inv_after": round(inv_yes - inv_no, 6),
                "cash_after": round(float(f["cash_after"]), 4),
                "fee": round(float(f.get("fee") or 0.0), 6),
                "rebate": round(float(f.get("rebate") or 0.0), 6),
                "ts": ts,
            }
        )
    cols = [
        "fill_id",
        "datetime_utc",
        "date",
        "market_question",
        "market_id_short",
        "side",
        "action_plain",
        "size_shares",
        "price",
        "notional_usd",
        "mid",
        "edge_vs_mid_cents",
        "inv_yes_after",
        "inv_no_after",
        "net_inv_after",
        "cash_after",
        "fee",
        "rebate",
        # extras kept for round-trip builder / debugging (will drop from human CSV)
        "market_id",
        "action",
        "ts",
    ]
    return pd.DataFrame(rows, columns=cols)


HUMAN_FILL_COLS = [
    "fill_id",
    "datetime_utc",
    "date",
    "market_question",
    "market_id_short",
    "side",
    "action_plain",
    "size_shares",
    "price",
    "notional_usd",
    "mid",
    "edge_vs_mid_cents",
    "inv_yes_after",
    "inv_no_after",
    "net_inv_after",
    "cash_after",
    "fee",
    "rebate",
]


def build_round_trips(
    fills_df,
    last_mids: dict[str, float],
    questions: dict[str, str],
    end_ts: int | None = None,
):
    """FIFO-match buy_yes <-> sell_yes per market; MTM leftovers at last mid."""
    import pandas as pd

    trips: list[dict[str, Any]] = []
    trade_id = 0

    # open lots: market -> deque of {side, price, size, ts, mid}
    open_lots: dict[str, deque] = defaultdict(deque)

    for row in fills_df.itertuples(index=False):
        mid_id = str(row.market_id)
        side = str(row.side)
        size_left = float(row.size_shares)
        price = float(row.price)
        ts = int(row.ts)
        fill_mid = float(row.mid) if row.mid is not None and row.mid == row.mid else float("nan")
        q = open_lots[mid_id]

        while size_left > 1e-12 and q and q[0]["side"] != side:
            lot = q[0]
            matched = min(size_left, lot["size"])
            entry_side = lot["side"]
            exit_side = side
            entry_price = lot["price"]
            exit_price = price
            entry_time = lot["ts"]
            exit_time = ts
            entry_mid = lot["mid"]
            exit_mid = fill_mid

            # PnL in YES terms: long = buy then sell; short = sell then buy
            if entry_side == "buy_yes":
                gross = matched * (exit_price - entry_price)
            else:
                gross = matched * (entry_price - exit_price)

            hold_h = (exit_time - entry_time) / 3600.0
            trade_id += 1
            trips.append(
                {
                    "trade_id": trade_id,
                    "market_question": questions.get(mid_id, row.market_question),
                    "market_id": mid_id,
                    "entry_time": pd.Timestamp(entry_time, unit="s", tz="UTC").isoformat(),
                    "exit_time": pd.Timestamp(exit_time, unit="s", tz="UTC").isoformat(),
                    "hold_hours": round(hold_h, 4),
                    "entry_side": entry_side,
                    "exit_side": exit_side,
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(exit_price, 4),
                    "size": round(matched, 6),
                    "gross_pnl_usd": round(gross, 4),
                    "pnl_cents_per_share": round((gross / matched) * 100.0, 4) if matched else 0.0,
                    "entry_mid": round(entry_mid, 4) if entry_mid == entry_mid else None,
                    "exit_mid": round(exit_mid, 4) if exit_mid == exit_mid else None,
                    "status": "closed",
                    "exit_reason": "opposite_fill",
                }
            )
            lot["size"] -= matched
            size_left -= matched
            if lot["size"] <= 1e-12:
                q.popleft()

        if size_left > 1e-12:
            q.append(
                {
                    "side": side,
                    "price": price,
                    "size": size_left,
                    "ts": ts,
                    "mid": fill_mid,
                }
            )

    # Mark open lots to market
    for mid_id, q in open_lots.items():
        last_mid = float(last_mids.get(mid_id, float("nan")))
        while q:
            lot = q.popleft()
            size = float(lot["size"])
            if size <= 1e-12:
                continue
            entry_side = lot["side"]
            entry_price = float(lot["price"])
            entry_time = int(lot["ts"])
            entry_mid = float(lot["mid"])
            if last_mid == last_mid:
                exit_price = last_mid
                if entry_side == "buy_yes":
                    gross = size * (exit_price - entry_price)
                else:
                    gross = size * (entry_price - exit_price)
                exit_mid = last_mid
            else:
                exit_price = entry_price
                gross = 0.0
                exit_mid = float("nan")
            trade_id += 1
            exit_ts = int(end_ts) if end_ts is not None else entry_time
            hold_h = (exit_ts - entry_time) / 3600.0 if end_ts is not None else None
            trips.append(
                {
                    "trade_id": trade_id,
                    "market_question": questions.get(mid_id, ""),
                    "market_id": mid_id,
                    "entry_time": pd.Timestamp(entry_time, unit="s", tz="UTC").isoformat(),
                    "exit_time": pd.Timestamp(exit_ts, unit="s", tz="UTC").isoformat(),
                    "hold_hours": round(hold_h, 4) if hold_h is not None else None,
                    "entry_side": entry_side,
                    "exit_side": "eod_mark",
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(exit_price, 4) if exit_price == exit_price else None,
                    "size": round(size, 6),
                    "gross_pnl_usd": round(gross, 4),
                    "pnl_cents_per_share": round((gross / size) * 100.0, 4) if size else 0.0,
                    "entry_mid": round(entry_mid, 4) if entry_mid == entry_mid else None,
                    "exit_mid": round(exit_mid, 4) if exit_mid == exit_mid else None,
                    "status": "open_at_end",
                    "exit_reason": "eod_mark",
                }
            )

    cols = [
        "trade_id",
        "market_question",
        "entry_time",
        "exit_time",
        "hold_hours",
        "entry_side",
        "exit_side",
        "entry_price",
        "exit_price",
        "size",
        "gross_pnl_usd",
        "pnl_cents_per_share",
        "entry_mid",
        "exit_mid",
        "status",
        "exit_reason",
    ]
    return pd.DataFrame(trips, columns=cols) if trips else pd.DataFrame(columns=cols)


def write_summary(
    path: Path,
    metrics: dict,
    fills_df,
    trips_df,
    tag: str,
    overlay: dict,
    strategy_module: str,
    days_file: str,
    n_days: int,
    elapsed: float,
    n_fills_ok: bool,
):
    n_open = int((trips_df["status"] == "open_at_end").sum()) if len(trips_df) else 0
    n_closed = int((trips_df["status"] == "closed").sum()) if len(trips_df) else 0

    top_by_fills = []
    if len(fills_df):
        g = (
            fills_df.groupby(["market_question", "market_id_short"], dropna=False)
            .size()
            .reset_index(name="n_fills")
            .sort_values("n_fills", ascending=False)
            .head(10)
        )
        top_by_fills = g.to_dict(orient="records")

    top_by_pnl = []
    if len(trips_df):
        g2 = (
            trips_df.groupby("market_question", dropna=False)["gross_pnl_usd"]
            .sum()
            .reset_index()
        )
        g2["abs_pnl"] = g2["gross_pnl_usd"].abs()
        g2 = g2.sort_values("abs_pnl", ascending=False).head(10)
        top_by_pnl = [
            {
                "market_question": r.market_question,
                "gross_pnl_usd": round(float(r.gross_pnl_usd), 4),
            }
            for r in g2.itertuples(index=False)
        ]

    out = {
        "tag": tag,
        "strategy_module": strategy_module,
        "overlay": overlay,
        "days_file": days_file,
        "n_days": n_days,
        "liveish": True,
        "net_pnl": metrics.get("net_pnl"),
        "reward_pnl": metrics.get("reward_pnl"),
        "trading_pnl": metrics.get("trading_pnl"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "n_fills": metrics.get("n_fills"),
        "ledger_n_fills": int(len(fills_df)),
        "n_fills_match": n_fills_ok,
        "n_round_trips": int(len(trips_df)),
        "n_closed": n_closed,
        "n_open": n_open,
        "round_trip_gross_pnl_sum": round(float(trips_df["gross_pnl_usd"].sum()), 4)
        if len(trips_df)
        else 0.0,
        "top_markets_by_fill_count": top_by_fills,
        "top_markets_by_abs_pnl": top_by_pnl,
        "elapsed_sec": round(elapsed, 3),
        "expected_90d_net_pnl_approx": 2137.37,
    }
    path.write_text(json.dumps(out, indent=2, default=str))
    return out


def write_readme(path: Path) -> None:
    path.write_text(
        """# Trade ledgers (champion `df_max8_pool110`)

These CSVs come from a **liveish** backtest of `research/champions/strategy_current_best.py`
with overlay `day_flatten=true`, `day_flatten_max_net=8`, `min_daily_reward_pool=110`
(via `LIVEISH_STRATEGY_CFG` + `liveish_engine_config`).

**`*_fills.csv`** — one row per engine fill. `action_plain` says whether our resting bid was hit
(Bought YES) or ask was lifted (Sold YES). `edge_vs_mid_cents` is how many cents better than mid
we got at fill time. Inventory and cash columns are post-fill.

**`*_round_trips.csv`** — FIFO-matched buys and sells per market. Closed rows have
`exit_reason=opposite_fill`. Leftover inventory at the end of the window is marked to the last mid
(`status=open_at_end`, `exit_reason=eod_mark`). `gross_pnl_usd` is share PnL only (excludes LP rewards).

**`*_summary.json`** — net/reward/trading PnL from the engine metrics, fill counts (should match
`n_fills`), and top markets by activity / abs round-trip PnL. Prefer engine `net_pnl` as the
checksum (~2137.37 on the 90d window).
"""
    )


def run_export(
    *,
    days_file: Path,
    tag: str,
    strategy_module: Path,
    overlay: dict,
    capital: float,
    out_dir: Path,
) -> dict:
    import pandas as pd
    from prepare import load_allowlist_markets

    mod = load_eval_liveish()
    StratCls = mod.load_strategy_class(strategy_module)
    strat_cfg = {**mod.LIVEISH_STRATEGY_CFG, **overlay}
    strat = StratCls(strat_cfg)
    eng_cfg = liveish_engine_config({"capital0": float(capital)})

    # Prefer allowlist loader (same as eval_liveish_candidate window mode)
    try:
        markets = load_allowlist_markets()
    except Exception:
        with open(ROOT / "data" / "markets.json") as f:
            markets = json.load(f)

    days = load_days(days_file)
    print(f"[{tag}] assembling {len(days)} days from {days_file}...", flush=True)
    t0 = time.time()
    prices = assemble_window(days, markets)
    print(f"[{tag}] prices rows={len(prices)}; running engine...", flush=True)

    eng = BacktestEngine(markets, strat, eng_cfg)
    metrics = eng.run(prices, None)
    elapsed = time.time() - t0

    raw_fills = list(eng.fills_ledger)
    last_mids = dict(getattr(eng, "_last_mids", {}) or {})
    questions = {str(m["market_id"]): m.get("question", "") for m in markets}

    fills_df = fills_to_dataframe(raw_fills)
    end_ts = int(metrics.get("end_ts") or (fills_df["ts"].max() if len(fills_df) else 0))
    trips_df = build_round_trips(fills_df, last_mids, questions, end_ts=end_ts)

    n_fills_metric = int(metrics.get("n_fills") or 0)
    n_fills_ok = n_fills_metric == len(fills_df)

    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"champion_df_max8_pool110_{tag}"
    fills_path = out_dir / f"{prefix}_fills.csv"
    trips_path = out_dir / f"{prefix}_round_trips.csv"
    summary_path = out_dir / f"{prefix}_summary.json"

    fills_out = fills_df[HUMAN_FILL_COLS].copy()
    fills_out.to_csv(fills_path, index=False, float_format="%.6g")
    trips_df.to_csv(trips_path, index=False, float_format="%.6g")

    # Optional rewards ledger sidecar
    if eng.rewards_ledger:
        rew = pd.DataFrame(eng.rewards_ledger)
        rew.to_csv(out_dir / f"{prefix}_rewards.csv", index=False, float_format="%.6g")

    summary = write_summary(
        summary_path,
        metrics,
        fills_df,
        trips_df,
        tag=tag,
        overlay=overlay,
        strategy_module=str(strategy_module),
        days_file=str(days_file),
        n_days=len(days),
        elapsed=elapsed,
        n_fills_ok=n_fills_ok,
    )
    write_readme(out_dir / "README.md")

    print(
        json.dumps(
            {
                "tag": tag,
                "net_pnl": summary["net_pnl"],
                "n_fills": summary["n_fills"],
                "ledger_n_fills": summary["ledger_n_fills"],
                "n_fills_match": n_fills_ok,
                "n_round_trips": summary["n_round_trips"],
                "n_open": summary["n_open"],
                "fills_csv": str(fills_path),
                "round_trips_csv": str(trips_path),
                "summary_json": str(summary_path),
                "elapsed_sec": summary["elapsed_sec"],
            },
            indent=2,
        ),
        flush=True,
    )

    del prices
    gc.collect()
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-file", type=Path, default=DEFAULT_DAYS)
    ap.add_argument("--tag", type=str, default=None, help="Filename tag, e.g. 90d or 30d")
    ap.add_argument("--strategy-module", type=Path, default=DEFAULT_STRATEGY)
    ap.add_argument("--overlay-json", type=str, default=json.dumps(DEFAULT_OVERLAY))
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument(
        "--also-30d",
        action="store_true",
        help="Also export 30d ledger (runs after primary unless primary is already 30d)",
    )
    ap.add_argument(
        "--only-30d",
        action="store_true",
        help="Only run 30d window (faster smoke)",
    )
    args = ap.parse_args()

    overlay = json.loads(args.overlay_json)

    if args.only_30d:
        run_export(
            days_file=ROOT / "research" / "window_30d_days.txt",
            tag="30d",
            strategy_module=args.strategy_module,
            overlay=overlay,
            capital=args.capital,
            out_dir=args.out_dir,
        )
        return

    tag = args.tag
    if tag is None:
        name = args.days_file.name
        if "30d" in name:
            tag = "30d"
        elif "60d" in name:
            tag = "60d"
        elif "90d" in name:
            tag = "90d"
        else:
            tag = "custom"

    # Prefer finishing primary (usually 90d); optionally also 30d first for faster artifact
    if args.also_30d and tag != "30d":
        print("=== pre-run 30d for faster artifact ===", flush=True)
        run_export(
            days_file=ROOT / "research" / "window_30d_days.txt",
            tag="30d",
            strategy_module=args.strategy_module,
            overlay=overlay,
            capital=args.capital,
            out_dir=args.out_dir,
        )
        gc.collect()

    print(f"=== primary run tag={tag} ===", flush=True)
    run_export(
        days_file=args.days_file,
        tag=tag,
        strategy_module=args.strategy_module,
        overlay=overlay,
        capital=args.capital,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()
