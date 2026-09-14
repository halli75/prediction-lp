#!/usr/bin/env python3
"""
Live PAPER trader for Polymarket LP rewards.

SIMULATE ONLY — never places real CLOB orders, never uses private keys.
Polls public books, runs Strategy.quote, paper-fills on mid-cross.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.live_feed import (  # noqa: E402
    discover_reward_markets,
    fetch_market_snapshot,
    load_markets_live,
    save_markets_live,
)
from paper.paper_engine import CHAMPION_LABEL, PaperEngine  # noqa: E402

# Mild live-bot strategy defenses (from scripts/eval_liveish.py)
LIVEISH_STRATEGY_CFG = {
    "near_mid_size_mult": 0.5,
    "near_mid_dist": 0.02,
    "portfolio_inv_cap": 400.0,
    "cancel_move": 0.02,
}

STOP = False


def _handle_sig(_signum, _frame) -> None:
    global STOP
    STOP = True
    print("[paper] SIGTERM/SIGINT — graceful stop requested", flush=True)


def refresh_markets(path: Path, min_pool: float) -> list[dict]:
    print(f"[paper] discovering reward markets (pool>={min_pool}) ...", flush=True)
    markets = discover_reward_markets(min_pool=min_pool, skip_ended=True)
    save_markets_live(markets, path)
    print(f"[paper] wrote {path} n_markets={len(markets)}", flush=True)
    return markets


def poll_snapshots(markets: list[dict], max_markets: int | None = None) -> dict[str, dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    snaps: dict[str, dict] = {}
    subset = markets if not max_markets else markets[: max_markets]
    jobs = [(m["market_id"], str(m["yes_token"])) for m in subset if m.get("yes_token")]

    def _one(pair):
        mid, tok = pair
        return mid, fetch_market_snapshot(tok)

    # Bounded concurrency — read-only public books
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_one, j) for j in jobs]
        for fut in as_completed(futs):
            mid, snap = fut.result()
            snaps[mid] = snap
    return snaps


def main() -> None:
    ap = argparse.ArgumentParser(description="Polymarket LP paper trader (simulate only)")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--poll-sec", type=float, default=15.0)
    ap.add_argument(
        "--status-path",
        type=Path,
        default=ROOT / "results" / "paper" / "status.json",
    )
    ap.add_argument(
        "--fills-csv",
        type=Path,
        default=ROOT / "results" / "paper" / "fills.csv",
    )
    ap.add_argument(
        "--equity-csv",
        type=Path,
        default=ROOT / "results" / "paper" / "equity.csv",
    )
    ap.add_argument(
        "--pid-file",
        type=Path,
        default=ROOT / "results" / "paper" / "paper.pid",
    )
    ap.add_argument(
        "--markets-path",
        type=Path,
        default=ROOT / "data" / "markets_live.json",
    )
    ap.add_argument("--min-pool", type=float, default=110.0)
    ap.add_argument("--rediscover-sec", type=float, default=3600.0)
    ap.add_argument("--max-markets", type=int, default=0, help="0 = all discovered")
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)

    args.status_path.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.write_text(str(os.getpid()))

    from strategy import Strategy

    strat_cfg = dict(LIVEISH_STRATEGY_CFG)
    strategy = Strategy(strat_cfg)

    markets = refresh_markets(args.markets_path, args.min_pool)
    if not markets:
        # fallback: try existing file without ended filter already applied
        markets = load_markets_live(args.markets_path)
        print(f"[paper] discovery empty; loaded cached n={len(markets)}", flush=True)

    max_m = args.max_markets if args.max_markets > 0 else None
    eng = PaperEngine(
        markets,
        strategy,
        capital0=args.capital,
        poll_sec=args.poll_sec,
        fills_csv=args.fills_csv,
        equity_csv=args.equity_csv,
        champion=CHAMPION_LABEL,
    )

    print(
        f"[paper] START pid={os.getpid()} capital={args.capital} "
        f"poll={args.poll_sec}s n_markets={len(markets)} champion={CHAMPION_LABEL} "
        f"SIMULATE_ONLY=1",
        flush=True,
    )

    last_discover = time.time()
    while not STOP:
        t0 = time.time()
        try:
            if time.time() - last_discover >= float(args.rediscover_sec):
                markets = refresh_markets(args.markets_path, args.min_pool)
                if markets:
                    eng.set_markets(markets)
                last_discover = time.time()

            snaps = poll_snapshots(markets, max_m)
            status = eng.process_cycle(snaps)
            eng.write_status(args.status_path, status)
            print(
                f"[paper] cycle={status['cycle']} equity={status['equity']:.2f} "
                f"quoted={status['n_markets_quoted']}/{status['n_markets_book_ok']} "
                f"fills={status['n_fills']} reward_est={status['reward_pnl_est']:.4f}",
                flush=True,
            )
        except Exception as e:
            print(f"[paper] cycle error: {e!r}", flush=True)
            err_status = {
                "ts": int(time.time()),
                "error": repr(e),
                "champion": CHAMPION_LABEL,
                "paper": True,
                "real_orders": False,
                "uptime_sec": round(time.time() - eng.started_at, 1),
            }
            try:
                eng.write_status(args.status_path, err_status)
            except Exception:
                pass

        elapsed = time.time() - t0
        sleep_for = max(0.5, float(args.poll_sec) - elapsed)
        # interruptible sleep
        end = time.time() + sleep_for
        while not STOP and time.time() < end:
            time.sleep(min(0.5, end - time.time()))

    # final status
    final = {
        "ts": int(time.time()),
        "iso_time": datetime.now(timezone.utc).isoformat(),
        "stopped": True,
        "champion": CHAMPION_LABEL,
        "paper": True,
        "real_orders": False,
        "n_fills": eng.n_fills,
        "equity": round(eng.port.mark_to_market(eng.last_mids), 4),
        "cash": round(eng.port.cash, 4),
        "uptime_sec": round(time.time() - eng.started_at, 1),
    }
    eng.write_status(args.status_path, final)
    print(f"[paper] stopped. final equity={final['equity']}", flush=True)
    try:
        args.pid_file.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
