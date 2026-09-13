# Phase 3 report — continuous May–Aug window + top-reward universe

**Status:** discovery + continuous prepare pipeline landed; cache/evaluate/autoresearch numbers are filled after the day-by-day download finishes.

This is **continuous-within-archive**, not live trading.

## Setup

| Item | Target |
|------|--------|
| Window | 2026-05-01 → 2026-08-10 UTC |
| Gap | Jun 12–17 (archive missing) |
| Days | 96 archive days (~138GB raw traffic; 1 day on disk at a time) |
| Tokens | 80 YES outcomes (22 seed + 58 Gamma high-`rewardsDailyRate`) |
| Evaluate bars | 5-min last-print (`--bar-minutes 5`); slim stays 1-min |
| Capital | $10,000 |
| Search | ≥40 keep/discard iters on `holdout_net_pnl`; soft-reject DD > 25% |

## Results (pending download)

| Metric | Value |
|--------|------:|
| n_markets | TBD |
| n_days | TBD |
| date range | TBD |
| n_price_rows | TBD |
| train_net_pnl / % of $10k | TBD |
| holdout_net_pnl / % of $10k | TBD |
| holdout max DD % of capital | TBD |
| best params | TBD |
| kept / discarded iters | TBD |

See `results/baseline_metrics.json` and `results/experiments.jsonl`.

## Honest limitations

- Concatenated archive minutes ≠ a live book. The Jun 12–17 hole is real.
- Current Gamma reward params are held constant; 2026-05 rates may have differed.
- 5-min evaluate bars are coarser than the 1-min slim cache.
- **Not live-trading ready.**
