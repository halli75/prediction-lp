# Phase 3 report — continuous May–Aug window + top-reward universe

This is **continuous-within-archive**, not live trading.

## Coverage (what actually ran)

| Item | Value |
|------|--------|
| Mode | `continuous_day_l2` |
| Date range | **2026-05-01 00:00 UTC → 2026-08-10 00:40 UTC** |
| n_days | **96** archive days (every UTC day except Jun 12–17) |
| Known gap | Jun 12–17 (6 days missing in HF `orderbook_1min`) |
| n_markets | **79** YES tokens (80 requested; `will_paulo_costa_be_the_ufc` had 0 L2 rows) |
| Combined current daily pool | **$7,231/day** (Gamma, held constant) |
| n_price_rows | 2,014,670 (5-min last-print of 1-min slim books) |
| Slim cache | 96 × 1-min days, **24.7 MB** |
| Raw on disk | **1 day at a time** (~138GB transient); raw + HF cache deleted |
| Capital | $10,000 |
| Split | time 75/25 on concatenated timestamps |

Discovery: `scripts/discover_reward_markets.py` ranked Gamma `clobRewards.rewardsDailyRate` for names listed before 2026-08-10. CLOB `/rewards` endpoints returned nothing useful.

## Baseline vs best keep

Starting `strategy.py` was the last sparse-day keep. Numbers below are on the **continuous 79×96 cache**. Overnight defenses later beat the 40-iter keep — see that section.

| Metric | Baseline | **Best keep (iter 38)** |
|--------|---------:|------------------------:|
| **holdout_net_pnl** | $1,178.51 | **$2,699.73** |
| holdout % of $10k | +11.79% | **+27.00%** |
| holdout max DD % of capital | 10.27% | **7.83%** |
| holdout reward / trading / fees | $2,172 / −$983 / $10 | $1,455 / $1,251 / $7 |
| holdout fills | 2,412 | 1,456 |
| **train_net_pnl** | −$96.68 (−0.97%) | **$556.04 (+5.56%)** |
| train max DD % of capital | 16.29% | 19.05% |
| soft_reject (holdout DD>25%) | false | **false** |

## Autoresearch

| Item | Value |
|------|------:|
| Iters | **40** (+ baseline eval) |
| Kept / no-improve / soft-reject | **6 / 26 / 8** |
| Best holdout_net_pnl / % of $10k | **$2,699.73 / +27.00%** |
| Best holdout max DD | 7.83% of capital |

**Best params**

```
spread_frac          = 0.30361660934315987
size_mult            = 4.703308838637967
skew_bps_per_share   = 0.086961148768161
inv_soft_cap         = 516.4965284986445
reward_spread_boost  = 0.17184274218966544
```

Keep path: $1,178 → $1,787 → $1,824 → $2,039 → $2,073 → $2,536 → **$2,700**.
Larger `size_mult` with a slightly tighter `spread_frac` and milder `reward_spread_boost` improved holdout without crossing the 25% DD soft-reject.

Logged in `results/experiments.jsonl` (phase 3 marker `continuous_search_start`).

## Overnight hardening (adverse selection)

Local swarm owns the 14-axis hyperparam search on a fixed ~12-day sample.
This pass only added **structural** defenses to `strategy.py` and iterated
them with `scripts/eval_sample.py` (cached parquet; **no HF download**).

Defenses (all `cfg.get` so autoresearch can still patch them):

| Knob | Tuned default | Role |
|------|--------------:|------|
| `cancel_move` | **0.015** | Pull both sides on the bar where \|Δmid\| ≥ 1.5¢; requote next bar. Shock (≥ 2×) also starts a pause. |
| `pause_secs` | **900** | After an inferred fill, quote only the reducing side for 15 min (3 five-min bars). |
| `near_mid_size_frac` / `near_mid_half` | **0.90 / 0.02** | Mild size cut when half-spread ≤ 2¢. Aggressive 0.55 was just a global size haircut and cost reward. |
| `portfolio_inv_cap` | **8000** | Stop adding when Σ\|net\| across names is large. 2500 was too tight. |
| `cash_reserve_frac` | **0.12** | Do not bid away the last 12% of starting capital. |
| per-market caps | `inv_soft_cap=516`, `max_abs_inv=800` | Unchanged from iter-38 keep. |

### 12-day sample (2026-07-30 → 08-10, same split the swarm uses)

| Metric | Iter-38 keep | Hardened (defaults) | Hardened (tuned) |
|--------|-------------:|--------------------:|-----------------:|
| holdout_net_pnl | $835.11 | $1,100.77 | **$1,600.80** |
| holdout max DD | 3.33% | 0.61% | **1.59%** |
| holdout trading / reward | −$293 / $1,129 | +$462 / $639 | **+$580 / $1,022** |
| train_net_pnl | $1,013 | $2,289 | **$3,717** |

Sweep note: **cancel-on-move is the load-bearing defense** (`cancel_move=1` dropped sample holdout to $758). Hard shrink (0.35) and a 2500 portfolio cap both hurt. `scripts/eval_sample.py --sweep` reproduces the one-at-a-time grid.

### Full 96-day / 79-market `evaluate.py` (one confirmation run)

| Metric | Iter-38 keep | **Hardened + tuned** |
|--------|-------------:|---------------------:|
| **holdout_net_pnl** | $2,699.73 | **$4,674.63 (+46.75%)** |
| holdout max DD % of capital | 7.83% | **7.00%** |
| holdout reward / trading / fees | $1,455 / $1,251 / $7 | **$2,241 / $2,441 / $7** |
| holdout fills | 1,456 | **1,056** |
| **train_net_pnl** | $556.04 | **$3,882.14 (+38.82%)** |
| train max DD % of capital | 19.05% | **9.26%** |
| soft_reject | false | **false** |

Fewer fills, better trading PnL, and *more* reward (quotes stay up when the book is quiet; they leave when mid jumps). Holdout cash ends +$750 vs −$12 on the iter-38 keep.

Raw JSON: `results/hardened_defenses_metrics.json`.

**Tuned params (on top of iter 38)**

```
cancel_move          = 0.015
pause_secs           = 900
near_mid_size_frac   = 0.90
near_mid_half        = 0.02
portfolio_inv_cap    = 8000
cash_reserve_frac    = 0.12
```

## Honest limitations

1. Continuous archive days ≠ a live CLOB. No latency, cancels, or resolution.
2. Jun 12–17 is a **real hole**. Inventory is not marked across that gap except as concatenated timestamps.
3. `2026-08-10` is a ~41-minute stub.
4. Reward params are **current Gamma**, held constant. A $7.2k/day schedule applied to May–Aug 2026 is not historically verified.
5. Slim does **not** store full L2 JSON. Competition is BBO tightness **floored** at exogenous `min_size * 30` so we do not invent 50–80% reward shares.
6. Evaluate uses **5-minute** last-prints (`--bar-minutes 5`). Slim remains 1-min. Reward `samples_per_day` is inferred (288).
7. **+$4,675 holdout (+46.75%) is a model number, not live LP expectancy.** Cancel-on-move on 5-min last-prints is a coarse proxy for live cancels. Not live-trading ready.
8. Overnight work did **not** re-download HF days. Local already has ~60 slim days; this VM reused the existing 96-day cache.
