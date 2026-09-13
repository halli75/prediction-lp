#!/usr/bin/env python3
"""
Karpathy-style autoresearch loop over strategy.py.

Each iteration:
  1. Mutate strategy hyperparameters in strategy.py (deterministic search)
  2. Run evaluate.py
  3. Keep via git commit if holdout_net_pnl improves and DD soft-reject is false
  4. Else discard with git checkout
  5. Log to results/experiments.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / "strategy.py"
RESULTS = ROOT / "results"
EXP_LOG = RESULTS / "experiments.jsonl"
PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)


SEARCH_SPACE = [
    {"spread_frac": 0.30, "size_mult": 1.2, "skew_bps_per_share": 0.10, "inv_soft_cap": 400.0, "reward_spread_boost": 0.10},
    {"spread_frac": 0.45, "size_mult": 1.5, "skew_bps_per_share": 0.15, "inv_soft_cap": 500.0, "reward_spread_boost": 0.00},
    {"spread_frac": 0.60, "size_mult": 2.0, "skew_bps_per_share": 0.20, "inv_soft_cap": 600.0, "reward_spread_boost": 0.15},
    {"spread_frac": 0.35, "size_mult": 2.5, "skew_bps_per_share": 0.05, "inv_soft_cap": 350.0, "reward_spread_boost": 0.20},
    {"spread_frac": 0.50, "size_mult": 1.0, "skew_bps_per_share": 0.25, "inv_soft_cap": 700.0, "reward_spread_boost": 0.05},
    {"spread_frac": 0.40, "size_mult": 3.0, "skew_bps_per_share": 0.12, "inv_soft_cap": 450.0, "reward_spread_boost": 0.25},
    {"spread_frac": 0.55, "size_mult": 1.8, "skew_bps_per_share": 0.30, "inv_soft_cap": 550.0, "reward_spread_boost": 0.00},
    {"spread_frac": 0.25, "size_mult": 1.5, "skew_bps_per_share": 0.08, "inv_soft_cap": 300.0, "reward_spread_boost": 0.30},
    {"spread_frac": 0.32, "size_mult": 2.2, "skew_bps_per_share": 0.04, "inv_soft_cap": 320.0, "min_half_spread": 0.012, "reward_spread_boost": 0.18},
    {"spread_frac": 0.28, "size_mult": 1.8, "skew_bps_per_share": 0.06, "inv_soft_cap": 280.0, "max_abs_inv": 600.0, "reward_spread_boost": 0.22},
    {"spread_frac": 0.38, "size_mult": 2.8, "skew_bps_per_share": 0.03, "inv_soft_cap": 380.0, "reward_spread_boost": 0.12},
    {"spread_frac": 0.22, "size_mult": 1.3, "skew_bps_per_share": 0.09, "inv_soft_cap": 250.0, "min_half_spread": 0.015, "reward_spread_boost": 0.08},
    {"spread_frac": 0.42, "size_mult": 2.0, "skew_bps_per_share": 0.07, "inv_soft_cap": 420.0, "max_abs_inv": 1000.0, "reward_spread_boost": 0.16},
    {"spread_frac": 0.36, "size_mult": 1.6, "skew_bps_per_share": 0.11, "inv_soft_cap": 360.0, "reward_spread_boost": 0.28},
    {"spread_frac": 0.48, "size_mult": 2.4, "skew_bps_per_share": 0.02, "inv_soft_cap": 480.0, "reward_spread_boost": 0.35},
    {"spread_frac": 0.33, "size_mult": 3.2, "skew_bps_per_share": 0.05, "inv_soft_cap": 330.0, "min_half_spread": 0.01, "reward_spread_boost": 0.14},
]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)


def evaluate() -> dict:
    cp = run([str(PY), str(ROOT / "evaluate.py")])
    if cp.returncode != 0:
        raise RuntimeError(f"evaluate failed: {cp.stderr or cp.stdout}")
    return json.loads(cp.stdout)


def patch_strategy(params: dict) -> None:
    text = STRATEGY.read_text()
    for k, v in params.items():
        # Replace default in __init__ cfg.get("k", DEFAULT)
        pattern = rf'(self\.{k}\s*=\s*float\(cfg\.get\("{k}",\s*)([0-9.]+)(\)\))'
        repl = rf"\g<1>{float(v)}\g<3>"
        text2, n = re.subn(pattern, repl, text, count=1)
        if n == 0:
            raise RuntimeError(f"could not patch {k} in strategy.py")
        text = text2
    STRATEGY.write_text(text)


def git(*args: str) -> subprocess.CompletedProcess:
    return run(["git", *args])


def append_log(row: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(EXP_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--iters", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    # Ensure clean git baseline of strategy
    if not (ROOT / ".git").exists():
        run(["git", "init"])
    status = git("status", "--porcelain", "strategy.py").stdout.strip()
    if status:
        git("add", "strategy.py")
        git("commit", "-m", "chore: snapshot strategy before autoresearch")

    def slim_metrics(m: dict) -> dict:
        skip = {"train_inventory", "holdout_inventory"}
        return {k: v for k, v in m.items() if k not in skip}

    best = evaluate()
    best_pnl = float(best.get("holdout_net_pnl") or -1e18)
    best_params: dict | None = None
    print(f"[autoresearch] baseline holdout_net_pnl={best_pnl:.4f} soft_reject={best.get('soft_reject')}")
    append_log({"iter": 0, "kept": True, "params": "baseline", "metrics": slim_metrics(best), "ts": time.time()})

    rng = random.Random(args.seed)
    space = list(SEARCH_SPACE)
    rng.shuffle(space)

    for i in range(1, args.iters + 1):
        # After the first full grid pass, 50% of iters mutate the current best
        if best_params is not None and i > len(space) and rng.random() < 0.5:
            params = dict(best_params)
            source = "local"
        else:
            params = dict(space[(i - 1) % len(space)])
            source = "grid"
        # small jitter
        jittered = {
            k: float(v) * rng.uniform(0.85, 1.15) if isinstance(v, (int, float)) else v
            for k, v in params.items()
        }
        print(f"[autoresearch] iter {i}/{args.iters} {source} trying {jittered}")
        try:
            patch_strategy(jittered)
        except Exception as e:
            print(f"  patch error: {e}; skipping")
            git("checkout", "--", "strategy.py")
            append_log({"iter": i, "kept": False, "params": jittered, "error": str(e), "ts": time.time()})
            continue
        try:
            metrics = evaluate()
        except Exception as e:
            print(f"  evaluate error: {e}; discarding")
            git("checkout", "--", "strategy.py")
            append_log({"iter": i, "kept": False, "params": jittered, "error": str(e), "ts": time.time()})
            continue

        pnl = float(metrics.get("holdout_net_pnl") or -1e18)
        soft = bool(metrics.get("soft_reject"))
        improved = pnl > best_pnl and not soft
        if improved:
            best_pnl = pnl
            best_params = dict(jittered)
            msg = f"autoresearch: keep pnl={pnl:.2f} params={jittered}"
            git("add", "strategy.py")
            git("commit", "-m", msg)
            print(f"  KEEP pnl={pnl:.4f}")
            append_log({"iter": i, "kept": True, "params": jittered, "metrics": slim_metrics(metrics), "ts": time.time()})
        else:
            git("checkout", "--", "strategy.py")
            reason = "soft_reject" if soft else "no_improve"
            print(f"  DISCARD ({reason}) pnl={pnl:.4f} best={best_pnl:.4f}")
            append_log(
                {
                    "iter": i,
                    "kept": False,
                    "reason": reason,
                    "params": jittered,
                    "metrics": slim_metrics(metrics),
                    "ts": time.time(),
                }
            )

    print(f"[autoresearch] done. best holdout_net_pnl={best_pnl:.4f}")


if __name__ == "__main__":
    main()
