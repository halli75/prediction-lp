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

Starting `strategy.py` was the last sparse-day keep. Numbers below are on the **continuous 79×96 cache**.

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

## Honest limitations

1. Continuous archive days ≠ a live CLOB. No latency, cancels, or resolution.
2. Jun 12–17 is a **real hole**. Inventory is not marked across that gap except as concatenated timestamps.
3. `2026-08-10` is a ~41-minute stub.
4. Reward params are **current Gamma**, held constant. A $7.2k/day schedule applied to May–Aug 2026 is not historically verified.
5. Slim does **not** store full L2 JSON. Competition is BBO tightness **floored** at exogenous `min_size * 30` so we do not invent 50–80% reward shares.
6. Evaluate uses **5-minute** last-prints (`--bar-minutes 5`). Slim remains 1-min. Reward `samples_per_day` is inferred (288).
7. **+27% holdout is a model number, not live LP expectancy. Not live-trading ready.**
