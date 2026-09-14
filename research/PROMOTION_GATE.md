# Promotion gate (authoritative)

**Current champion:** `creative_wave4_ovn_e3` (creative wave4 overnight recovery over df_max8_pool110)
Files: `research/champions/strategy_creative_wave4_ovn_e3.py` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave4 2026-09-14T01:10:42.821706+00:00 under **LIVEISH Aug10** gates. Prior creative_df_max8_pool110 liveish: sample 611.05 / 30d 1676.34 / 60d 2512.14.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **726.73** | false |
| **30d** | **1703.17** | false |
| **60d** | **2710.25** | false |

**To replace champion:** both **liveish-30d > 1703.17** AND **liveish-60d > 2710.25** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >726.73. Inventory: soft ≤35 ≥20; hard ≤100.

Creative overlay: `{"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0, "overnight_quiet": true, "overnight_mode": "reduce_only", "overnight_end_hour": 3}`

**Liveish 90d (May14→Aug10, 83d):** **+$2089.00** (dd 3.16%; vs prior df_max8_pool110 90d +$2137).

Artifact: `results/promotion_creative_wave4_ovn_e3.json` / `results/creative_wave4_ovn_e3_liveish_90d.json`
