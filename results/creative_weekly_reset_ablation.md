# Creative weekly-reset ablation (ops lever)

Strategy: champion `wave5b_pull24_p46_sf672` under liveish. No strategy change — only deploy policy.

## Headline

| Comparison | Weekly sum | Continuous | Δ (weekly − cont) |
|------------|----------:|-----------:|------------------:|
| Full archive (~83d) | **2754.16** | **547.23** | **2206.93** |
| 60d gate window | **2037.32** | **861.11** | **1176.20** |
| 90d continuous (ref) | (full weekly 2754.16) | **547.23** | — |

Independent **$10k** capital reset each 7-day chunk. Continuous = one book across the window.

## Interpretation

- If weekly sum >> continuous: path-dependent inventory bleed dominates; **restart book weekly** is a creative ops lever.
- If weekly ≈ continuous: toxicity is within-week; structural flatten modes matter more than resets.

## Week detail (full archive)

| week | start | end | n_days | net_pnl | dd% |
|-----:|-------|-----|-------:|--------:|----:|
| 0 | 2026-05-14 | 2026-05-20 | 7 | 85.44 | 0.62 |
| 1 | 2026-05-21 | 2026-05-27 | 7 | 174.60 | 0.81 |
| 2 | 2026-05-28 | 2026-06-03 | 7 | 276.98 | 0.33 |
| 3 | 2026-06-04 | 2026-06-10 | 7 | 131.16 | 0.50 |
| 4 | 2026-06-11 | 2026-06-23 | 7 | 204.10 | 0.28 |
| 5 | 2026-06-24 | 2026-06-30 | 7 | 203.99 | 0.08 |
| 6 | 2026-07-01 | 2026-07-07 | 7 | 500.13 | 0.16 |
| 7 | 2026-07-08 | 2026-07-14 | 7 | 255.20 | 0.32 |
| 8 | 2026-07-15 | 2026-07-21 | 7 | 54.81 | 0.57 |
| 9 | 2026-07-22 | 2026-07-28 | 7 | 315.99 | 0.36 |
| 10 | 2026-07-29 | 2026-08-04 | 7 | 314.71 | 0.18 |
| 11 | 2026-08-05 | 2026-08-10 | 6 | 237.05 | 0.38 |

Artifact: `results/creative_weekly_reset_ablation.json`
