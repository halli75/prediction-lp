# Creative Agenda — Wave 3 (structural modes beyond max_net)

**Context:** Champion `creative_df_max8_pool110` (`day_flatten=true`, `day_flatten_max_net=8`, `min_daily_reward_pool=110`).
Liveish gates: sample **611.05** / 30d **1676.34** / 60d **2512.14** (wave2 promote over day_boundary_flatten).

Wave2 promoted `df_max8_pool110`. Near-miss: `df_max10` (30d 1427.06 under prior gate). Prior day_flatten 90d was +1074.61.

**Mandate:** KEEP iterating creative structural changes on top of NEW champion defaults. Do not stop.

## Thesis
Day-boundary flatten + mild max_net loosen (8) + pool110 ridge cut bleed while harvesting better pools.
Wave3 attacks *intra-day* and *portfolio* inventory lifecycle on top of that base.

## Bets (all on top of df_max8_pool110 defaults)

| # | Mode | Knobs | Why |
|---|------|-------|-----|
| A | **session_flatten** | `session_hours` 8/12, `session_flatten_max_net` | Flatten at UTC 00+12 (or every 8h) until |net|≤max |
| B | **inventory_age_flatten** | `max_inv_age_ticks` 60/120/240 | If |net| away from ~0 too long → reduce-only tight |
| C | **overnight_quiet** | hours [0,6), mode reduce_only | size_mult=0.3 | Harvest daytime; quiet overnight risk |
| D | **carry_budget** | `carry_budget_shares` 50/80/120 | Portfolio abs inv over budget → force reduce |
| E | **toxic_market_day_ban** | `tox_day_ban_cents` 1.5/2.0/3.0 | Adverse mid vs hold → ban market rest of UTC day |
| F | **day_flatten_harvest_gate** | `df_gate_vol`, `df_gate_min_pool` | After day-flatten clears, require quiet vol or pool before two-sided |

## Gates (same `--liveish`) — RETARGETED after wave2 promote
Promote ONLY if liveish **30d > 1676.34** AND **60d > 2512.14**, soft_reject false, max_dd_pct<25.
Sample preferred >611.05. Inventory soft ≤35 ≥20, hard ≤100.

## Prior wave3 note (old base, informational)
First pass used day_flatten max_net=5 base; overnight_quiet sample-hot (788/731) but windows failed prior gates
(ovn_reduce 1441/1978 — 60d ~$1.5 under old 1979.75). Relaunched on new champion base+gates.
See `results/creative_wave3_preretarget_findings.md`.

## Artifacts
- Strategy: `research/creative/strategy_creative_base.py` (WAVE3 modes 6–11)
- Hunt: `scripts/creative_wave3_hunt.py`
- Status: `results/swarm_creative_wave3_status.json`
- Findings: `results/creative_wave3_findings.md`
- Agenda: `research/CREATIVE_AGENDA_WAVE3.md`
