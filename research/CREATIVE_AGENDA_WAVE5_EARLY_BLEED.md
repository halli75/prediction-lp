# Creative Agenda — Wave 5 (early-bleed hunt)

**Context:** Champion `creative_wave4_ovn_e3` (day_flatten + max_net8 + pool110 + overnight_quiet reduce_only end=3).
Liveish: sample **+726.73** / 30d **1703.17** / 60d **2710.25** / 90d **+2089.00** (dd 3.16%).
Prior df_max8_pool110 90d was **+2137** — 90d includes May/early-June continuous path bleed via leftover inventory / adverse fills; 60d (Jun→Aug) looks stronger.

**Mandate:** Fix early bleed WHILE maintaining (or not sacrificing) 30d/60d profits.
Overnight swarm digest is **PAUSED** — do NOT relaunch broad waves. Only this focused hunt.

## Parent overlay (always)
```json
{"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110,
 "overnight_quiet": true, "overnight_mode": "reduce_only", "overnight_end_hour": 3}
```

## Bets
| # | Mode | Knobs |
|---|------|-------|
| A | inv_age_flatten | max_inv_age_ticks 30/60/120/240 |
| B | warm_start | warm_days 7/14 OR warm_until_date 2026-06-01/06-15; size_frac 0.5/0.7; max_net 3/5 |
| C | fill_rate_brake | window 15/20/40; threshold 2/3/4; brake_ticks 20/30/60 |
| D | daily_trading_stop | stop 40/80/120/160; mode reduce_only / empty |
| E | combos | warm+age; age+dts; warm+age+fr |

## Gates (liveish)
- Sample preferred > **726.73**
- Promote **must** beat 30d > **1703.17** AND 60d > **2710.25**
- Then MUST run 90d; promote only if 90d **> 2109** (2089 + $20 clear margin). Near-miss if 30d+60d clear but 90d ≤2109.
- soft_reject=false; max_dd_pct<25; inv soft≤35≥20 hard≤100

## Artifacts
- Hunt: `scripts/creative_wave5_early_bleed_hunt.py`
- Status: `results/swarm_creative_wave5_status.json`
- Findings: `results/creative_wave5_findings.md`
- Modes in: `research/creative/strategy_creative_base.py`
