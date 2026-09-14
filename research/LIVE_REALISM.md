# Live realism gaps vs the optimistic LP backtest

This document explains why overnight / champion PnL can look too good relative to
a deployed Polymarket LP bot, what knobs we added, and how `--liveish` eval uses them.

Current champion under the **legacy optimistic** gate: **pool100**
(`min_daily_reward_pool=100`; sample 1673.11 / 30d 2734.01 / 60d 2604.43).
Prior pool150: sample 1197.56 / 30d 2083.31 / 60d 1913.93.

Document **both** optimistic baseline and liveish deltas for this champion.
Prefer comparing candidates under the **same** liveish flags when promoting.

## Gaps (legacy sim → live)

| Gap | Legacy behavior | Live reality | Mitigation in sim |
|-----|-----------------|--------------|-------------------|
| Quote latency / cancel lag | Strategy quotes replace resting book every price row; cancels are instantaneous | Cancel/replace is delayed by network + matching latency; stale quotes can fill | `quote_latency_rows` — new quotes/cancels apply only after N per-market rows; old quotes stay fillable |
| Full mid-cross fills | Mid path-cross fills **100%** of resting size | Queue position / partial take; often only a fraction fills | `max_fill_frac` < 1 |
| Adverse selection | Trade-tape boost only; mid-cross ignores future path | Fills cluster when flow is informed; mid continues against after hit | `adverse_mid_cross_strength` scales mid-cross size when future mid favors aggressor |
| Instant fill on touch | Single row path-cross → fill | Quote may be canceled or mid may bounce before you get lifted | `fill_persist_rows` — mid must stay through quote for M rows or pending cross cancels |
| Portfolio inventory | Per-market caps only | Live bots cap gross inventory across markets (capital / risk) | `portfolio_inv_cap` in engine + strategy (`portfolio_abs_inv` in state) |
| No latency on rewards | Rewards scored on intended quote same row | Book display lags; rewards accrue on what is actually resting | With latency, reward score uses **resting** open quote |
| Trade tape optional | Sample/window evals use `use_trades=False` | Live sees aggressive flow | Still optional; liveish keeps trades off for apples-to-apples vs gate scripts |

## Config knobs (`sim/engine.py`)

Defaults preserve legacy optimistic behavior (backward compatible):

```python
quote_latency_rows: 0
max_fill_frac: 1.0
adverse_mid_cross_strength: 0.0
fill_persist_rows: 0          # 0 = path-cross model
portfolio_inv_cap: 0.0        # 0 = off
```

**LIVEISH_CONFIG** (used by `scripts/eval_liveish.py --liveish`):

```python
quote_latency_rows: 1
max_fill_frac: 0.40
adverse_mid_cross_strength: 6.0
fill_persist_rows: 1
portfolio_inv_cap: 400.0
adverse_lookback_min: 5
use_trades: False
```

Helper: `sim.engine.liveish_engine_config(base)`.

## Strategy defenses (`strategy.py`)

Champion knobs unchanged. New optional knobs (defaults no-op for baseline parity):

- `cancel_move` — soft cancel threshold in **price units** (alias of `mid_move_cancel_cents / 100`)
- `near_mid_dist` / `near_mid_size_mult` — shrink size when half-spread ≤ dist (default mult=1.0 = off)
- `portfolio_inv_cap` — stand down adding side when `portfolio_abs_inv` ≥ cap (0 = off)

Liveish eval enables mild strategy defenses:

```python
near_mid_size_mult: 0.5
near_mid_dist: 0.02
portfolio_inv_cap: 400.0
cancel_move: 0.02   # same as 2¢ soft cancel already used by champion
```

Inventory soft/hard caps are **not** weakened (soft ≤ 35, hard ≤ 100).

## Measured pool100 deltas

From `results/liveish_vs_baseline.json` (strategy.py = pool100, `min_daily_reward_pool=100`):

| Window | Optimistic baseline | Liveish | Δ (liveish − baseline) | Liveish − optimistic gate |
|--------|--------------------:|--------:|-----------------------:|--------------------------:|
| sample | 1673.11 | 528.35 | -1144.76 | -1144.76 |
| 30d | 2734.01 | 432.94 | -2301.07 | -2301.07 |

Liveish sample and 30d remain **green** (positive net, soft_reject false) but far less optimistic than the gate — overnight decisions should weight the liveish column.

Prior pool150 optimistic gate for reference: sample 1197.56 / 30d 2083.31 / 60d 1913.93.

## Eval

```bash
.venv/bin/python scripts/eval_liveish.py
# writes results/liveish_vs_baseline.json and results/liveish_delta.md
```

Compares baseline (legacy engine defaults) vs liveish on the 12-day research sample
and the 30d window for current `strategy.py`. Optional 60d via `--also-60d`.

## Promotion note

Do **not** overwrite `strategy_current_best` / champion unless **both** liveish-30d
and liveish-60d beat **pool100** under the **same** liveish flags. A candidate that
only wins under optimistic sim is not promotion-ready. See `PROMOTION_GATE.md`.
