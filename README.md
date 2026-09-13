# Polymarket LP Autoresearch

Karpathy-style autoresearch loop over a Polymarket **liquidity-providing (LP)** market-making
backtest. Starting capital **$10,000**. Kalshi is out of scope.

## What this is

1. **`scripts/discover_reward_markets.py`** — ranks Gamma markets by `rewardsDailyRate`
   (plus volume), writes `data/reward_universe.json` (~40–80 YES tokens listed before
   the archive end).
2. **`prepare.py`** downloads **continuous UTC days** of HuggingFace
   [`Joseph3222/polymarket-orderbook`](https://huggingface.co/datasets/Joseph3222/polymarket-orderbook)
   config **`orderbook_1min`** for **2026-05-01 → 2026-08-10** (skip Jun 12–17).
   One raw day at a time → DuckDB-filter to the reward-token allowlist → slim parquet
   → **delete raw day + HF cache immediately**. Never keep more than ~1–2 raw days.
3. **`evaluate.py`** (fixed) runs train/holdout backtests and prints JSON metrics.
4. **`strategy.py`** (editable) — two-sided quoting with inventory skew, reward-pool
   spread tightening, and continuous-book defenses (inventory caps, cancel-on-move,
   shrink size near mid, pause after fills). Autoresearch mutates it.
5. **`scripts/run_autoresearch.py`** — keep/discard via git; logs `results/experiments.jsonl`.
6. **`scripts/eval_sample.py`** — last-N-day slice of the cached `prices.parquet`
   (default 12 days). No download. Use for sample-fast iteration; confirm with full
   `evaluate.py`.

This is **not** live-trading ready. Continuous-within-archive ≠ a live CLOB.

## Data coverage (honest)

| Item | Value |
|------|--------|
| Source | HF `orderbook_1min` only (not the TB raw stream) |
| Default window | **Continuous** 2026-05-01 → 2026-08-10 |
| Known gap | Jun 12–17 missing in the archive (6 days) |
| Archive bounds | starts 2026-02-22, ends 2026-08-10 |
| Markets | 40–80+ YES tokens ranked by Gamma `rewardsDailyRate` |
| Rewards | Current Gamma `rewardsMinSize` / `rewardsMaxSpread` / `rewardsDailyRate` held **constant**; historical rates may have differed |
| Disk hygiene | 1 raw day (~0.5–2.5GB) + HF cache; both deleted after filter. Slim caches stay. |
| Evaluate bars | Slim is 1-min; `prices.parquet` may be N-minute last-print (`--bar-minutes`) so a 30–50 iter search is tractable. Reward samples/day are inferred from the bar. |

`--sparse` restores the old 11-day set. `--quick` is two days only.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# 1) Rank reward markets (no order-book download)
python scripts/discover_reward_markets.py --max-tokens 80

# 2) Continuous May→Aug prepare (one day at a time; deletes raw)
python prepare.py --bar-minutes 5

# 3) Fast 12-day sample (cached parquet only) or full evaluate
python scripts/eval_sample.py --last-days 12
python evaluate.py

# 4) Smoke tests (no network)
pytest -q tests/test_smoke.py
python evaluate.py --fixture

# 5) Autoresearch
python scripts/run_autoresearch.py -n 40
```

Primary metric: **`holdout_net_pnl`**. Soft-reject if holdout max drawdown **> 25% of capital**.

## Simulation assumptions

- Portfolio: cash + YES/NO inventory, $10k start.
- Fills: mid-path crossing, penetration-scaled; 5-min look-ahead adverse size boost.
- LP rewards: docs-aligned quadratic score; sample count inferred from bar width.
- Competition: BBO tightness (full L2 JSON is not stored in slim).
- Fees: **1 bp** maker fee of notional; rebate = 0.
- Days are concatenated in timestamp order. The Jun 12–17 hole is a **true archive gap**, not a calendar hold.

## Limitations

- Continuous archive days ≠ live trading. No latency, cancels, or resolution settlement.
- Reward schedule is **not** historically accurate day-by-day (current Gamma constants).
- Jun 12–17 are missing; `2026-08-10` is a short stub.
- If `--bar-minutes` > 1, the evaluate clock is coarser than the 1-min slim books.
- Autoresearch mutates a hyperparameter grid, not open-ended code gen.
- Current kept `strategy.py` (iter-38 params + overnight defenses) prints **holdout +$4,674.63 (+46.75% on $10k, DD 7.00%)** on the 96×79 cache. That is a **model number**, not live LP expectancy.
