# Polymarket LP Autoresearch

Karpathy-style autoresearch loop over a Polymarket **liquidity-providing (LP)** market-making
backtest. Starting capital **$10,000**. Kalshi is out of scope.

## What this is

1. **`prepare.py`** (fixed) downloads a **sparse-day** subset of HuggingFace
   [`Joseph3222/polymarket-orderbook`](https://huggingface.co/datasets/Joseph3222/polymarket-orderbook)
   config **`orderbook_1min`**, DuckDB-filters to a curated YES-token universe
   (phase-1 Fed/geopolitics + phase-2 Gamma high-`rewardsDailyRate` names),
   writes slim caches under `data/`, and deletes full ~0.5–2.5GB day files **and**
   the HuggingFace hub cache so peak disk stays under ~10GB.
2. **`evaluate.py`** (fixed) runs train/holdout backtests and prints JSON metrics.
3. **`strategy.py`** (editable) — two-sided quoting with inventory skew + optional
   reward-pool spread tightening; autoresearch mutates it.
4. **`scripts/run_autoresearch.py`** — keep/discard via git; logs `results/experiments.jsonl`.

This is **not** live-trading ready.

## Data coverage (honest)

This is **sparse-day sampling across ~6 calendar months**, **not** continuous L2.

| Item | Value |
|------|--------|
| Source | HF `orderbook_1min` only (not the TB raw stream) |
| Default days | 2026-02-22, 2026-03-08, 2026-03-29, 2026-04-05, 2026-04-12, 2026-05-14, 2026-06-01, 2026-06-18, 2026-06-25, 2026-07-20, 2026-08-10 |
| Gaps | Jun 12–17 missing in archive; archives start 2026-02-22 and end 2026-08-10 |
| Markets | ~15–25 YES tokens: Fed Sep 2026 (5) + Iran/Trump + Gamma-discovered high-reward names (Israel PM, Brazil 2026, France 2027, F1, Ballon d'Or, Fed-cuts-in-2026, aliens, Vance, Putin, Iran regime, Taiwan, …) |
| Rewards | Current Gamma `rewardsMinSize` / `rewardsMaxSpread` / `rewardsDailyRate` held **constant**; historical rates may have differed |
| Not used | CLOB `prices-history` (lookback too short / almost no overlap with archives) |
| Disk | Raw day files + HF cache deleted after each DuckDB filter; budget ~10GB download+cache |

Quick first run uses **two days only**: `--quick` → 2026-05-14 + 2026-07-20.

Optional `--discover` sweeps Gamma for extra high-reward tokens (capped by `--max-tokens`, default 25).

## Setup

```bash
cd /workspace/polymarket-lp-autoresearch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# 1) Prepare data (quick 2-day baseline first)
python prepare.py --quick

# Or full sparse set (11 days, watch disk; raw files deleted after filter)
python prepare.py

# 2) Evaluate baseline
python evaluate.py

# 3) Smoke tests (no network)
pytest -q tests/test_smoke.py
python evaluate.py --fixture

# 4) Autoresearch N iterations
python scripts/run_autoresearch.py -n 30
```

Primary metric: **`holdout_net_pnl`**. Soft-reject if holdout max drawdown **> 25% of capital**.

## Simulation assumptions

- Portfolio: cash + YES/NO inventory, $10k start.
- Fills: mid-path crossing of resting quotes, **penetration-scaled** (a 1¢ nick is a partial fill; a through-move is closer to full). Optional trade tape (empty in HF L2 path).
- Adverse selection: mid-path and trade-tape fills boosted when short-horizon mid move favors the aggressor.
- LP rewards: docs-aligned quadratic score, two-sided /c=3, tails must be two-sided, ~1/min samples, $1 min daily payout.
- Competition: **L2 book depth** within max spread when available, with a tightness bump when BBO is 1–2¢; else exogenous `competition_q`.
- Fees: **1 bp** maker fee of notional (cheap residual-friction stand-in); rebate = 0. Documented in `sim/fills.py`.
- Each sparse day is replayed independently in chronological order of timestamps (multi-day concat).

## Project layout

```
prepare.py evaluate.py strategy.py program.md
sim/  scripts/run_autoresearch.py  tests/  fixtures/  data/  results/
```

## Limitations

- Sparse days ≠ continuous path; overnight/weekend gaps between sample days are **not** modeled as holding risk continuously in calendar time beyond concatenated timestamps.
- Reward schedule is **not** historically accurate day-by-day.
- No full queue / aggressor-flow microstructure. Adverse selection is a look-ahead mid-move size boost, not a toxicity model.
- Inventory settlement / merge-split complete-set mechanics simplified.
- Autoresearch mutates a small hyperparameter grid (+ local jitter around the best), not open-ended code gen.
- **Not live-trading ready.** No latency, cancel/replace, venue outages, or inventory settlement at resolution.
