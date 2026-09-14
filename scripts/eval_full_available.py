#!/usr/bin/env python3
"""Evaluate a strategy on the full locally available continuous slim window.

Uses research/window_90d_days.txt (all cached slim days; skips Jun12–17 archive gap).
Does not download any HF data.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAYS = ROOT / "research" / "window_90d_days.txt"
DEFAULT_STRAT = ROOT / "research" / "champions" / "strategy_pool150.py"
EVAL_WINDOW = ROOT / "scripts" / "eval_window.py"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strategy-module",
        type=Path,
        default=DEFAULT_STRAT,
        help="strategy .py to load (default: pool150 champion)",
    )
    ap.add_argument(
        "--days-file",
        type=Path,
        default=DEFAULT_DAYS,
        help="day list (default: window_90d_days.txt = all available)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write JSON here (default: results/eval_full_available_<label>.json)",
    )
    ap.add_argument("--label", type=str, default=None, help="label for default out path")
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args()

    days_file = args.days_file
    if not days_file.exists():
        raise SystemExit(f"missing days file: {days_file}")
    strat = args.strategy_module
    if not strat.exists():
        raise SystemExit(f"missing strategy: {strat}")

    label = args.label or strat.stem.replace("strategy_", "")
    out = args.out or (ROOT / "results" / f"eval_full_available_{label}.json")

    cmd = [
        sys.executable,
        str(EVAL_WINDOW),
        "--days-file",
        str(days_file),
        "--strategy-module",
        str(strat),
        "--capital",
        str(args.capital),
    ]
    print(f"[eval_full_available] label={label}", flush=True)
    print(f"[eval_full_available] days={days_file}", flush=True)
    print(f"[eval_full_available] strategy={strat}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "eval_window failed\n")
        raise SystemExit(proc.returncode)

    raw = proc.stdout.strip()
    # eval_window prints JSON; tolerate trailing noise
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise SystemExit(f"no JSON in eval_window output:\n{raw[:500]}")
    metrics = json.loads(raw[start : end + 1])
    metrics["label"] = label
    metrics["window"] = "full_available"
    metrics["days_file"] = str(days_file.relative_to(ROOT))
    metrics["note"] = (
        "Longest honest local continuous window: all slim_days "
        "(May14→Jul21, skip Jun12–17). No post-Jul21 data downloaded."
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    print(json.dumps(metrics, indent=2, default=str))
    print(f"[eval_full_available] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
