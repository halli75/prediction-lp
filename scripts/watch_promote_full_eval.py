#!/usr/bin/env python3
"""Watch results/promotion_*.json; if a new champion beats pool150, run full-available eval.

Usage:
  python scripts/watch_promote_full_eval.py --once   # scan once
  python scripts/watch_promote_full_eval.py --poll 30 # poll every 30s
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DIGEST = RESULTS / "overnight_digest.md"
POOL150 = RESULTS / "promotion_pool150.json"
STATE = RESULTS / ".full_eval_watch_state.json"
FULL_EVAL = ROOT / "scripts" / "eval_full_available.py"


def load_pool150_bars() -> dict:
    """Load current champion bars (prefer pool100 / market-set, else pool150)."""
    candidates = [
        RESULTS / "promotion_pool100.json",
        RESULTS / "promotion_market_set_pool_ge_100.json",
        POOL150,
    ]
    for path in candidates:
        if not path.exists():
            continue
        p = json.loads(path.read_text())
        w = p.get("windows") or {}
        b30 = (w.get("30d") or {}).get("net_pnl")
        b60 = (w.get("60d") or {}).get("net_pnl")
        if b30 is None or b60 is None:
            continue
        return {
            "30d": float(b30),
            "60d": float(b60),
            "label": p.get("label") or path.stem,
        }
    return {"30d": 0.0, "60d": 0.0, "label": "unknown"}


def beats_pool150(promo: dict, bars: dict) -> bool:
    w = promo.get("windows") or {}
    # Accept several shapes used by promotion artifacts
    def pnl(key: str) -> float | None:
        block = w.get(key) or promo.get(key) or {}
        if isinstance(block, (int, float)):
            return float(block)
        if isinstance(block, dict):
            for k in ("net_pnl", "window_net_pnl", "candidate"):
                if k in block and block[k] is not None:
                    return float(block[k])
        beat = (promo.get("beat_previous_champion") or {}).get(key) or {}
        if isinstance(beat, dict) and beat.get("candidate") is not None:
            return float(beat["candidate"])
        return None

    p30, p60 = pnl("30d"), pnl("60d")
    if p30 is None or p60 is None:
        # explicit flag
        if promo.get("beat_previous_champion") and promo.get("promoted"):
            return True
        if promo.get("new_champion") or promo.get("is_champion"):
            return True
        return False
    soft = False
    for key in ("30d", "60d"):
        block = w.get(key) or {}
        if isinstance(block, dict) and block.get("soft_reject"):
            soft = True
    if soft:
        return False
    return p30 > bars["30d"] and p60 > bars["60d"]


def append_digest(text: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = f"\n\n## Full-available eval (auto) — {ts}\n\n{text}\n"
    with open(DIGEST, "a") as f:
        f.write(block)


def already_done(state: dict, path: Path) -> bool:
    key = path.name
    done = state.get("evaluated") or {}
    return key in done


def mark_done(state: dict, path: Path, out_json: Path) -> None:
    state.setdefault("evaluated", {})[path.name] = {
        "mtime": path.stat().st_mtime,
        "out": str(out_json),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def process_once() -> int:
    if not POOL150.exists():
        print("[watch] no promotion_pool150.json yet", flush=True)
        return 0
    bars = load_pool150_bars()
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            state = {}
    # Always ensure pool150 itself has full eval
    pool_out = RESULTS / "eval_full_available_pool150.json"
    n = 0
    for promo_path in sorted(RESULTS.glob("promotion_*.json")):
        if already_done(state, promo_path) and promo_path.name != "promotion_pool150.json":
            # re-check pool150 only if missing out
            continue
        if promo_path.name == "promotion_pool150.json":
            if pool_out.exists():
                if not already_done(state, promo_path):
                    mark_done(state, promo_path, pool_out)
                continue
            # pool150 always gets full eval once if missing
            label = "pool150"
            strat = ROOT / "research" / "champions" / "strategy_pool150.py"
            out = pool_out
        else:
            try:
                promo = json.loads(promo_path.read_text())
            except Exception as e:
                print(f"[watch] skip {promo_path.name}: {e}", flush=True)
                continue
            if not beats_pool150(promo, bars):
                continue
            label = promo.get("label") or promo_path.stem.replace("promotion_", "")
            strat_s = promo.get("strategy") or promo.get("strategy_module")
            # Prefer live champion when promo strategy field is descriptive (market-set)
            if (not strat_s) or (" " in str(strat_s)) or (not (ROOT / str(strat_s).split()[0]).exists()):
                for cand in (
                    ROOT / "strategy.py",
                    ROOT / "research" / "champions" / "strategy_pool100.py",
                    ROOT / "research" / "champions" / "strategy_current_best.py",
                ):
                    if cand.exists():
                        strat_s = str(cand.relative_to(ROOT))
                        break
            if not strat_s:
                print(f"[watch] {promo_path.name} beats bars but no strategy path", flush=True)
                continue
            strat = ROOT / str(strat_s).split()[0]
            if not strat.exists():
                print(f"[watch] missing strategy {strat}", flush=True)
                continue
            out = RESULTS / f"eval_full_available_{label}.json"
            if out.exists() and already_done(state, promo_path):
                continue

        print(f"[watch] running full-available eval for {label}", flush=True)
        cmd = [
            sys.executable,
            str(FULL_EVAL),
            "--strategy-module",
            str(strat),
            "--label",
            label,
            "--out",
            str(out),
        ]
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"[watch] eval failed for {label} rc={proc.returncode}", flush=True)
            continue
        metrics = json.loads(out.read_text())
        summary = (
            f"- **{label}** full-available ({metrics.get('n_days')}d "
            f"{(metrics.get('days') or ['?'])[0]}→{(metrics.get('days') or ['?'])[-1]}): "
            f"net_pnl=**{metrics.get('net_pnl')}**, "
            f"reward={metrics.get('reward_pnl')}, trading={metrics.get('trading_pnl')}, "
            f"fills={metrics.get('n_fills')}, max_dd%={metrics.get('max_dd_pct')}, "
            f"soft_reject={metrics.get('soft_reject')}\n"
            f"- Artifact: `{out.relative_to(ROOT)}` (from `{promo_path.name}`)"
        )
        append_digest(summary)
        mark_done(state, promo_path, out)
        n += 1
        print(f"[watch] done {label} → {out}", flush=True)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=float, default=0.0, help="seconds between scans")
    args = ap.parse_args()
    if args.once or args.poll <= 0:
        n = process_once()
        print(f"[watch] processed {n} full eval(s)", flush=True)
        return
    print(f"[watch] polling every {args.poll}s", flush=True)
    while True:
        process_once()
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
