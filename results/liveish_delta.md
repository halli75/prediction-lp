# Liveish vs baseline

Strategy: `/workspace/polymarket-lp-autoresearch/strategy.py`
Elapsed: 374.112s

Liveish engine flags:
```
{
  "quote_latency_rows": 1,
  "max_fill_frac": 0.4,
  "adverse_mid_cross_strength": 6.0,
  "fill_persist_rows": 1,
  "portfolio_inv_cap": 400.0,
  "adverse_lookback_min": 5,
  "use_trades": false
}
```

| Window | Baseline net | Liveish net | Δ | Baseline DD% | Liveish DD% | Liveish fills |
|--------|-------------:|------------:|--:|-------------:|------------:|--------------:|
| sample | 1673.11 | 528.35 | -1144.76 | 1.28 | 0.31 | 221 |
| 30d | 2734.01 | 432.94 | -2301.07 | 1.22 | 0.47 | 118 |

## Vs champion optimistic gate (pool100)

| Window | Optimistic gate | Baseline (this run) | Liveish | Liveish − gate |
|--------|----------------:|--------------------:|--------:|---------------:|
| sample | 1673.11 | 1673.11 | 528.35 | -1144.76 |
| 30d | 2734.01 | 2734.01 | 432.94 | -2301.07 |

## Read

- Liveish should usually show **lower** net PnL and/or fewer optimistic fills than baseline.
- Report deltas vs **both** optimistic baseline (same run) and the pool100 optimistic gate.
- Use liveish numbers for actionable overnight decisions; optimistic gate remains in PROMOTION_GATE.md.
- Do not promote over pool100 unless liveish-30d **and** liveish-60d both beat pool100 under the same flags.

## Candidate hunt (liveish sample)

Swept spread/size/skew/inv/pause variants under the same liveish flags.

| Result | Value |
|--------|------:|
| pool100 liveish sample | 528.35 |
| pool100 liveish 30d | 432.94 |
| Best sample tweak (`skew_bps_per_share` 0.45) | 528.65 (+0.31) |
| Saved `strategy_liveish_candidate.py` | no |

No candidate improved liveish **30d**. Did **not** overwrite `strategy_current_best`
(requires both liveish-30d and liveish-60d > pool100 under the same flags).

60d liveish not measured in this run (other agents holding 60d/90d windows in RAM).
Optimistic 60d gate remains 2604.43.
