# Phase 3 report — continuous May–Aug window + top-reward universe

This is **continuous-within-archive**, not live trading.

## Coverage (what actually ran)

| Item | Value |
|------|--------|
| Mode | `continuous_day_l2` |
| Date range | **2026-05-01 00:00 UTC → 2026-08-10 00:40 UTC** |
| n_days | **96** archive days (every UTC day except Jun 12–17) |
| Known gap | Jun 12–17 (6 days missing in HF `orderbook_1min`) |
| n_markets | **79** YES tokens (80 requested; 1 UFC name had 0 L2 rows and was dropped) |
| n_price_rows | 2,014,670 (5-min last-print of 1-min slim books) |
| Slim cache | 96 × 1-min days, **24.7 MB** total |
| Raw on disk | **1 day at a time**, then deleted with the HF cache (~138GB transient download) |
| Capital | $10,000 |
| Split | time 75/25 on concatenated timestamps |

`scripts/discover_reward_markets.py` ranked Gamma `clobRewards.rewardsDailyRate` for names listed before 2026-08-10. Combined daily pool on the 79 names that appear in the books: **~$7.3k/day at current Gamma rates** (held constant; historical rates may have differed).

## Baseline (`strategy.py` after the earlier sparse-day keeps)

| Metric | Train | Holdout |
|--------|------:|--------:|
| **Net PnL** | **−$96.68** | **+$1,178.51** |
| % of $10k | −0.97% | **+11.79%** |
| Max DD (% of capital) | 16.29% | 10.27% |
| Reward PnL | (see JSON) | $2,171.75 |
| Trading PnL | (see JSON) | −$982.76 |
| Fees (1 bp) | — | $10.48 |
| Fills | 2,807 | 2,412 |
| Soft reject (DD>25%) | — | **false** |

Primary metric: **`holdout_net_pnl = 1178.5084`**.

Train loses a little on trading while holdout still prints — the late window is quieter and reward income covers inventory marks. **Do not read 11.8% as live LP expectancy.**

## Autoresearch (filled after the 40-iter run)

| Item | Value |
|------|------:|
| Iters | pending |
| Kept / discarded | pending |
| Best holdout_net_pnl / % of $10k | pending |
| Best holdout max DD | pending |
| Best params | pending |

## Honest limitations

1. Continuous archive days ≠ a live CLOB. No latency, cancels, or resolution.
2. Jun 12–17 is a **real hole**. Inventory is not marked across that gap except as concatenated timestamps.
3. `2026-08-10` is a ~41-minute stub.
4. Reward params are **current Gamma**, held constant.
5. Slim does **not** store full L2 JSON. Competition is BBO tightness **floored** at the old exogenous `min_size * 30` Q so we do not invent 50–80% reward shares.
6. Evaluate uses **5-minute** last-prints (`--bar-minutes 5`). Slim remains 1-min. Reward `samples_per_day` is inferred (288).
7. **Not live-trading ready.**
