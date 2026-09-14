# Promotion gate (authoritative)

**Current champion:** `creative_df_max8_pool110` (creative wave2 over day_boundary_flatten)
Files: `research/champions/strategy_creative_wave2_df_max8_pool110.py` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave2 2026-09-13T22:16:27.616311+00:00 under **LIVEISH Aug10** gates. Prior day_boundary_flatten liveish: sample 651.39 / 30d 1431.56 / 60d 1979.75.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **611.05** | false |
| **30d** | **1676.34** | false |
| **60d** | **2512.14** | false |

**To replace champion:** both **liveish-30d > 1676.34** AND **liveish-60d > 2512.14** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >611.05. Inventory: soft ≤35 ≥20; hard ≤100.

Creative overlay: `{"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0}`

Artifact: `results/promotion_creative_df_max8_pool110.json`
