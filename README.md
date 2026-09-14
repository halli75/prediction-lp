# Polymarket LP Autoresearch

Karpathy-style autoresearch loop over a Polymarket **liquidity-providing (LP)** market-making
backtest. Starting capital **$10,000**. Kalshi is out of scope.

## What this is

1. **`prepare.py`** (fixed) downloads a **sparse-day** subset of HuggingFace
   [`Joseph3222/polymarket-orderbook`](https://huggingface.co/datasets/Joseph3222/polymarket-orderbook)
   config **`orderbook_1min`**, DuckDB-filters to a curated YES-token universe, writes slim
   caches under `data/`, and deletes full ~1–2GB day files.
2. **`evaluate.py`** (fixed) runs train/holdout backtests and prints JSON metrics.
3. **`strategy.py`** (editable) — two-sided quoting with inventory skew; autoresearch mutates it.
4. **`scripts/run_autoresearch.py`** — keep/discard via git; logs `results/experiments.jsonl`.

## Data coverage

**Continuous** ~3-month L2 from HF `orderbook_1min` (day-at-a-time; raw deleted after filter).

| Item | Value |
|------|--------|
| Source | HF `orderbook_1min` only (not the TB raw stream) |
| Default range | **2026-05-14 → 2026-08-10** continuous (83 days) |
| Gaps | Jun 12–17 missing in archive; archives end 2026-08-10 |
| Markets | Allowlist in `data/top_reward_markets.json` (~40–80 YES tokens ranked by `rewardsDailyRate`, long-lived overlap preferred) |
| Rewards | Current Gamma/CLOB `rewardsMinSize` / `rewardsMaxSpread` / `rewardsDailyRate` held **constant**; historical rates may have differed |
| Disk | Downloads **one day** (~1–2GB), DuckDB-filters to allowlist, writes `data/slim_days/YYYY-MM-DD.parquet`, deletes raw immediately |
| Resume | `python prepare.py --continuous --resume` (state in `data/manifest.json`) |

Quick smoke: `--quick` → 2026-05-14 + 2026-07-20. Legacy sparse: `--sparse`.

## Setup

```bash
cd /workspace/polymarket-lp-autoresearch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# 1) Prepare continuous May14–Aug10 (resume-friendly; one day at a time)
python prepare.py --continuous
# python prepare.py --continuous --resume

# Quick smoke / legacy sparse
# python prepare.py --quick
# python prepare.py --sparse

# 2) Evaluate baseline
python evaluate.py

# 3) Smoke tests (no network)
pytest -q tests/test_smoke.py
python evaluate.py --fixture

# 4) Autoresearch N iterations
python scripts/run_autoresearch.py -n 5
```

Primary metric: **`holdout_net_pnl`**. Soft-reject if holdout max drawdown **> 25% of capital**.

## Simulation assumptions

- Portfolio: cash + YES/NO inventory, $10k start.
- Fills: mid-path crossing of resting quotes; optional trade tape (empty in HF L2 path).
- Adverse selection: trade-tape fills boosted when short-horizon mid move favors aggressor.
- LP rewards: docs-aligned quadratic score, two-sided /c=3, tails must be two-sided, ~1/min samples, $1 min daily payout.
- Competition: **L2 book depth** within max spread when available; else exogenous `competition_q`.
- Fees: maker fee/rebate ≈ 0 bps (Polymarket maker-favorable); documented in `sim/fills.py`.
- Each sparse day is replayed independently in chronological order of timestamps (multi-day concat).

## Project layout

```
prepare.py evaluate.py strategy.py program.md
sim/  scripts/run_autoresearch.py  tests/  fixtures/  data/  results/
```

## Limitations

- Continuous day concat still has the Jun 12–17 archive gap; overnight inventory carries across day boundaries via timestamps.
- Reward schedule is **not** historically accurate day-by-day.
- No full adverse-selection microstructure from aggressor flow when trade tape absent.
- Inventory settlement / merge-split complete-set mechanics simplified.
- Autoresearch mutates a small hyperparameter grid, not open-ended code gen.
