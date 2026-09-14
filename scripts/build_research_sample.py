#!/usr/bin/env python3
"""Build 12-day research sample prices for fast overnight evals (does not touch prepare download)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prepare import assemble_prices  # noqa: E402

SLIM = ROOT / "data" / "slim_days"
OUT_PRICES = ROOT / "data" / "research_sample_prices.parquet"
DAYS_FILE = ROOT / "research" / "sample_days.txt"
MANIFEST = ROOT / "research" / "sample_manifest.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-file", type=Path, default=DAYS_FILE)
    ap.add_argument("--out", type=Path, default=OUT_PRICES)
    ap.add_argument("--markets", type=Path, default=ROOT / "data" / "markets.json")
    args = ap.parse_args()

    days = [
        ln.strip()
        for ln in args.days_file.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    paths = []
    missing = []
    for d in days:
        p = SLIM / f"{d}.parquet"
        if p.exists() and p.stat().st_size > 0:
            paths.append(p)
        else:
            missing.append(d)
    if missing:
        print(json.dumps({"warning_missing_days": missing}))
    if not paths:
        raise SystemExit("no slim days available")

    markets = json.loads(args.markets.read_text())
    prices = assemble_prices(paths, markets)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(args.out, index=False)

    # Also mirror under research/sample for convenience
    sample_dir = ROOT / "research" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(sample_dir / "prices.parquet", index=False)
    (sample_dir / "markets.json").write_text(json.dumps(markets, indent=2))

    meta = {
        "days": days,
        "days_present": [p.stem for p in paths],
        "missing_days": missing,
        "n_rows": int(len(prices)),
        "n_markets": int(prices["market_id"].nunique()) if len(prices) else 0,
        "prices_path": str(args.out.relative_to(ROOT)),
        "markets_path": str(args.markets.relative_to(ROOT)),
    }
    (sample_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text())
        man["build_meta"] = meta
        MANIFEST.write_text(json.dumps(man, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
