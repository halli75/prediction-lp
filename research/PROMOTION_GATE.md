# Promotion gate (authoritative)

**Current champion:** `creative_wave5_fr_w20_t3_b30` (creative wave5 early-bleed over ovn_e3)
Files: `research/champions/strategy_creative_wave5_fr_w20_t3_b30.py` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave5 2026-09-14T04:28:16.102807+00:00 under **LIVEISH Aug10** gates.
Prior creative_wave4_ovn_e3 liveish: sample 726.73 / 30d 1703.17 / 60d 2710.25 / 90d 2089.00.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **719.43** | false |
| **30d** | **1711.30** | false |
| **60d** | **2737.88** | false |
| **90d** | **2946.12** | false |

**To replace champion:** both **liveish-30d > 1711.30** AND **liveish-60d > 2737.88** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >719.43. Inventory: soft ≤35 ≥20; hard ≤100. Prefer 90d also improves.

Creative overlay: `{"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0, "overnight_quiet": true, "overnight_mode": "reduce_only", "overnight_end_hour": 3, "fill_rate_window": 20, "fill_rate_threshold": 3, "fill_rate_brake_ticks": 30}`

Artifact: `results/promotion_creative_wave5_fr_w20_t3_b30.json`
