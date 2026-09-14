# Overnight digest — Polymarket LP commander


> **LIVE HANDOFF (2026-09-13T23:33:04Z):** champion = `creative_df_max8_pool110` (sample +611.05 / 30d +1676.34 / 60d +2512.14 / 90d +2137.37). Wave3 no promote (ovn_reduce 30d miss −$78 / 60d pass). Wave4 overnight-30d-recovery running (pid 217752).


Updated: 2026-09-13T23:33:04Z (commander; champion creative_df_max8_pool110; wave3 done; wave4 launched)

## Mission
User away ~12h. Commander actively fixes structural losses, then runs 14-axis autoresearch on a 12-day sample; promotes winners to 30/60d.

## Root cause (fixed in defensive v2)
Trading/inventory losses exceeded rewards on continuous data (adverse selection + inventory bleed). More markets made it worse.

## Current champion (UNCHANGED)
- **Strategy:** **hybrid_spread_size**
- **Paths:** `research/champions/strategy_hybrid_spread_size.py`, `research/champions/strategy_current_best.py`, root `strategy.py` synced
- **12-day sample:** **+$1086.47** (max DD **1.05%**)
- **30d:** **+$1938.76** (DD 0.86%)
- **60d:** **+$1581.22** (DD 2.28%)
- **Knobs:** size_by_reward_pool champion + `spread_frac=0.6676` + `size_mult=1.291`; inv_soft=35 / hard=100
- **NEW GATE:** beat hybrid **30d 1938.76 AND 60d 1581.22**. Sample-only beats are not enough. Do not promote weaker free_explore variants.

## Sample days
2026-05-14, 05-20, 05-25, 05-31, 06-06, 06-11, 06-23, 06-28, 07-04, 07-10, 07-15, 07-21

## Swarm
14 axes + hybrid parent free_explore (`axis-from-hybrid`, seed 77, 60 iters). Leaderboard: `research/leaderboard.json`.

## Data
63 continuous slim days cached (May14→Jul21). Mega-download stopped. **Do not download more data.**

## Swarm progress
- Time: 2026-09-13T05:27:31Z
- Champion sample: **$1086.47** (`hybrid-spread-size`) — **still current champion**
- axis-from-hybrid sample best: **$1183.60** (2 keeps, not soft-reject) — **window gate FAIL**

## Rejected — axis-from-hybrid (free_explore seed 77, from hybrid parent)

Parent: `research/champions/strategy_hybrid_spread_size.py` only. Inventory floors held (soft 35 ≥ 20, hard 150 ≥ 80).

| Window | Candidate | Hybrid champion | Delta | Soft-reject |
|--------|-----------|-----------------|-------|-------------|
| **sample** | **+1183.60** | +1086.47 | **+97.13** | false (DD 1.53%) |
| **30d** | +1877.75 | **+1938.76** | **-61.01** | false (DD 0.65%) |
| **60d** | +1412.36 | **+1581.22** | **-168.86** | false (DD 2.46%) |

Keeps: iter 22 (max_abs_inv=200, pull_size_mult=0.658 → sample +1091.98); iter 60 (max_abs_inv=150, skew=0.210, pull_size_mult=0.288, inv_pause_ticks=16 → sample +1183.60).

**NEW GATE fail** (must beat 30d 1938.76 AND 60d 1581.22). Not promoted. Champion files untouched.

Artifact: `results/promotion_axis_from_hybrid.json`

## Previously rejected (do not restore)
- `from_champion_free_explore`: sample +892 / 30d +1246 / 60d +1222 — weaker than hybrid
- `free_explore_v2` / `free_explore_v2_capsafe`: sample +981 / 30d +1231 / 60d +1413 — weaker than hybrid

## Prior promotion — hybrid_spread_size (current champion)

| Window | Calendar | Days present | Net PnL | Reward | Trading | Fills | Max DD% |
|--------|----------|--------------|---------|--------|---------|-------|---------|
| **30d** | 2026-06-22 → 2026-07-21 | 30 / 30 | **+1938.76** | +1320.11 | +618.65 | 101 | 0.8598 |
| **60d** | 2026-05-23 → 2026-07-21 | 54 / 60 | **+1581.22** | +1344.17 | +237.05 | 495 | 2.2786 |

Artifact: `results/promotion_hybrid_spread_size.json`

## Prior — size_by_reward_pool
30d +731.41 / 60d +982.39. Artifact: `results/promotion_size_by_reward_pool.json`

## Prior — defensive v2
30d +365.45 / 60d +539.95. Artifact: `results/promotion_defensive_v2.json`


## Full-available window prep — 2026-09-13T06:22:52Z

- Inventory: **63** slim days **2026-05-14 → 2026-07-21** (gap Jun12–17). No local Jul22→Aug10 caches; **no download**.
- Day list: `research/window_90d_days.txt` (+ alias `window_full_available_days.txt`)
- Coverage: `research/data_coverage.md`
- Scripts: `scripts/eval_full_available.py`, `scripts/watch_promote_full_eval.py`

### pool150 on FULL available continuous window

| Metric | Value |
|--------|------:|
| n_days | 63 |
| range | 2026-05-14 → 2026-07-21 |
| **net_pnl** | **1592.0468** |
| reward_pnl | 1720.7728 |
| trading_pnl | -128.726 |
| n_fills | 995 |
| max_dd_pct | 2.9435 |
| soft_reject | False |
| elapsed_sec | 185.583 |

Artifact: `results/eval_full_available_pool150.json`

Extend past Jul21 only after a champion beats pool150 on 30d+60d gates (~39.5 GB raw / ~2.5 GB peak day-at-a-time / ~15–25 min prepare).

## Market combos

Updated: 2026-09-13T20:05:40Z (commander digest; champion wave5b; wave10 done; wave11 launched)

**Best set: `pool_ge_100`** (50 markets, pool floor 100). Beats both pool150 window gates. `strategy_current_best.py` **not** overwritten.

| Rank | Set | n | Sample net | Reward | Trading | Fills | DD% | 30d | 60d |
|-----:|-----|--:|-----------:|-------:|--------:|------:|----:|----:|----:|
| 1 | **pool_ge_100** | 50 | **+1673.11** | +291.74 | +1381.37 | 384 | 1.28 | **+2734.01** | **+2604.43** |
| 2 | pool_ge_150 (champ) | 27 | +1197.56 | +255.65 | +941.91 | 295 | 1.18 | +2083.31 | +1913.93 |
| 3 | pool_ge_200 | 23 | +1086.47 | +242.03 | +844.44 | 175 | 1.05 | +1938.76 | +1581.22 |
| 4 | pool_ge_50 | 65 | +989.61 | +312.85 | +676.76 | 475 | 3.51 | — | — |
| 5 | top15 | 15 | +844.96 | +213.85 | +631.11 | 144 | 0.79 | — | — |
| 6 | top10 | 10 | +675.69 | +189.37 | +486.32 | 135 | 0.78 | — | — |
| 7 | seed_fed_iran | 9 | +570.46 | +116.51 | +453.95 | 160 | 0.71 | — | — |
| 8 | top8 | 8 | +553.88 | +164.38 | +389.49 | 117 | 0.69 | — | — |
| 9 | diverse_top | 20 | +460.71 | +143.96 | +316.75 | 112 | 0.97 | — | — |
| 10 | top5 | 5 | +378.55 | +134.42 | +244.13 | 61 | 0.69 | — | — |
| 11 | top3 | 3 | +304.78 | +102.10 | +202.69 | 29 | 0.65 | — | — |

### Window gate (top sample winner)

| Window | pool_ge_100 | pool150 gate | Delta | Soft-reject |
|--------|------------:|-------------:|------:|:-----------:|
| **sample** | **+1673.11** | +1197.56 | **+475.55** | false (DD 1.28%) |
| **30d** | **+2734.01** | +2083.31 | **+650.70** | false (DD 1.22%) |
| **60d** | **+2604.43** | +1913.93 | **+690.50** | false (DD 3.03%) |

**Takeaway:** on these knobs, the 100–149 pool band is net-positive. Tight top-N / seed Fed-Iran / diverse-theme sets all lost to broader high-pool thresholds. Expanding all the way to pool>=50 *hurt* vs pool>=100 (inventory bleed). Quality still beats “quote everything,” but the champion floor of 150 is stricter than this sample/window evidence supports.

Artifacts: `results/market_combo_leaderboard.json`, `results/promotion_market_set_pool_ge_100.json`, `research/market_sets/CURRENT_BEST_SET.md`.


## PROMOTED — pool100 (20260913T062330Z)

Market-combo win: `min_daily_reward_pool` **150 → 100** (50 markets). Quoting knobs unchanged.

| Window | Net PnL | vs pool150 | Max DD% |
|--------|--------:|-----------:|--------:|
| sample | **+1673.11** | +475.55 | 1.28 |
| 30d | **+2734.01** | +650.70 | 1.22 |
| 60d | **+2604.43** | +690.50 | 3.03 |

Champion files synced. New gate above. Artifacts: `results/promotion_market_set_pool_ge_100.json`, `research/market_sets/CURRENT_BEST_SET.md`.


## Full-available eval — pool100 champion — 2026-09-13T06:27:34Z

Commander gate now **pool100** (30d **2734.01** / 60d **2604.43**). Evaluated current `strategy.py` (`min_daily_reward_pool=100`).

| Champion | n_days | range | **net_pnl** | reward | trading | fills | max_dd% | soft_reject | elapsed_s |
|----------|-------:|-------|------------:|-------:|--------:|------:|--------:|:-----------:|----------:|
| pool150 (hist) | 63 | 2026-05-14→2026-07-21 | **1592.0468** | 1720.7728 | -128.726 | 995 | 2.9435 | False | 185.583 |
| **pool100 (current)** | 63 | 2026-05-14→2026-07-21 | **2304.9872** | 1936.0165 | 368.9707 | 1464 | 2.9548 | False | 153.272 |

- Delta full-window vs pool150: **+712.9404**
- Artifacts: `results/eval_full_available_pool100.json`, `results/eval_full_available_pool150.json`
- Coverage: `research/data_coverage.md`; day list: `research/window_90d_days.txt` (63 days; no Jul22→Aug10 download)


## Market combos wave2 — 2026-09-13T06:30:04Z

Refine around **pool100** champion (gate sample 1673.11 / 30d 2734.01 / 60d 2604.43). Frozen quoting knobs. No HF download.

**Result: pool100 still best.** No set beat sample gate → no 30d/60d → **no promotion**.

| Rank | Set | n | Sample | Δ vs gate | DD% |
|-----:|-----|--:|-------:|----------:|----:|
| 1 | **pool_ge_100** | 50 | **+1673.11** | 0 | 1.28 |
| 2 | pool_ge_110 | 40 | +1433.78 | −239 | 1.32 |
| 3 | pool_ge_100_ex_emmys | 39 | +1337.65 | −335 | 1.28 |
| 4 | pool_ge_120 | 35 | +1320.88 | −352 | 1.33 |
| 5 | pool_ge_125 | 33 | +1300.63 | −372 | 1.11 |
| 6 | pool_ge_140 | 29 | +1215.63 | −457 | 1.12 |
| 7 | pool_ge_150 | 27 | +1197.56 | −476 | 1.18 |
| 8 | pool_ge_130 | 31 | +1196.49 | −477 | 1.12 |
| 9 | pool_ge_90 | 54 | +1065.90 | −607 | 3.40 |
| 10 | pool_ge_80 | 65 | +989.61 | −684 | 3.51 |
| 11 | pool_100_to_199 | 27 | +586.15 | −1087 | 0.51 |

**Takeaway:** floor 100 is a local optimum. Raising strips profitable 100–109 names; lowering reintroduces inventory bleed; excluding Emmys or >=200 megapools both destroy sample PnL (megapools especially).

Artifacts: `results/market_combo_leaderboard_wave2.json`, `research/market_sets/CURRENT_BEST_SET.md`. Gate unchanged in `research/PROMOTION_GATE.md`.

## PROMOTION 20260913T063448Z
- Agent `wave3-cancel_on_mid_move` axis `cancel_on_mid_move`
- sample 1755.64 / 30d 2767.11 / 60d 3038.91
- beat gate 30d>2734.01 and 60d>2604.43
- champion files synced to `strategy_wave2_cancel_on_mid_move_20260913T063448Z.py`


## Full-available eval (auto) — 2026-09-13T06:37:30Z

- **wave2_cancel_on_mid_move_20260913T063448Z** full-available (70d 2026-05-14→2026-07-28): net_pnl=**2501.8012**, reward=2231.9941, trading=269.8071, fills=1625, max_dd%=2.9806, soft_reject=False
- Artifact: `results/eval_full_available_wave2_cancel_on_mid_move_20260913T063448Z.json` (from `promotion_wave2_cancel_on_mid_move_20260913T063448Z.json`)


## Full-available eval (auto) — 2026-09-13T06:41:54Z

- **pool100_mid_move_hard_cancel_cents_2p5** full-available (73d 2026-05-14→2026-07-31): net_pnl=**3117.6511**, reward=2532.2484, trading=585.4026, fills=1819, max_dd%=2.8773, soft_reject=False
- Artifact: `results/eval_full_available_pool100_mid_move_hard_cancel_cents_2p5.json` (from `promotion_pool100_mid_move_hard_cancel_cents_2p5.json`)

## LIVEISH GATE UPDATE 2026-09-13T06:42Z
- Optimistic promote `wave2_cancel_on_mid_move_20260913T063448Z` **VOID** (no liveish 30d+60d).
- Champion restored to official **pool100** (cancel 2.0 / hard 4.0 / widen 1.6 / pool 100).
- Liveish pool100 reference: sample **+528.35**, 30d **+432.94** (from `results/liveish_vs_baseline.json`).
- Re-scoring wave3 winners with `scripts/eval_* --liveish`; promote only if liveish 30d+60d beat pool100.


## Full-available eval (auto) — 2026-09-13T06:45:28Z

- **keep_mid_move_hard_cancel_cents_3p0** full-available (73d 2026-05-14→2026-07-31): net_pnl=**2724.8572**, reward=2295.9883, trading=428.8689, fills=1528, max_dd%=2.9548, soft_reject=False
- Artifact: `results/eval_full_available_keep_mid_move_hard_cancel_cents_3p0.json` (from `promotion_keep_mid_move_hard_cancel_cents_3p0.json`)

## LIVEISH 60d measured 2026-09-13
- pool100 liveish 60d = **423.35** (results/liveish_pool100_60d.json)
- Liveish gates now: sample 528.35 / 30d 432.94 / 60d 423.35
- Wave3 optimistic winners liveish sample: cancel 358, skew 333, free 405, pull 444, pause 527, near/shrink 528 (tie). **None beat gate.**
- Wave4b: liveish-criterion search on cancel/pull/pause/inventory (+shrink/near delayed).


## LIVEISH pool100 re-score on Aug10 windows — 2026-09-13T07:19:36Z

Re-scored current pool100 champion (`strategy.py`) with `scripts/eval_window.py --liveish` on the rebuilt day lists ending **2026-08-10**. One window at a time; no giant prices.parquet; `strategy_current_best` **not** overwritten.

| Window | Days | Range | **Liveish net** | vs old liveish | Optimistic | Max DD% |
|--------|-----:|-------|----------------:|---------------:|-------------:|--------:|
| 30d | 30 | Jul12→Aug10 | **+473.85** | old +432.94 | +3192.42 | 0.41 |
| 60d | 54 | Jun18→Aug10 | **+723.72** | old +423.35 | +3634.59 | 0.43 |
| 90d | 83 | May14→Aug10 | **+669.01** | (new) | +3171.57 | 0.62 |

All `soft_reject=false`. 90d trading_pnl slightly red (−59) while rewards +728.

**NEW LIVEISH GATE for promotions:** 30d **>473.85** AND 60d **>723.72** (same `--liveish` flags). Optimistic numbers stay labeled separately and are not sufficient. Sample liveish still **528.35** (old 12d set).

Artifact: `results/liveish_pool100_aug10_30_60_90.json`. Gate: `research/PROMOTION_GATE.md`.


## Commander check — 2026-09-13T07:56:30Z

**Champion unchanged: pool100** (liveish Aug10 gates 30d **473.85** / 60d **723.72** / 90d **669.01**; sample liveish **528.35**).

### Swarm status
- **Wave4b** (liveish search, 6 axes) **finished**. Best: `inventory_hard_cap` liveish sample **529.82** (+1.47 vs 528.35). Others tied at baseline. **No promotion** (need liveish 30d+60d on Aug10 windows).
- Wave3 optimistic winners still fail liveish sample (cancel_mid **358**, etc.).
- Optimistic `mid_move_hard_cancel_2.5` remains **VOID** as champion; `strategy.py` == pool100.

### Commander actions this run
1. Synced `window_*_liveish_gate_days.txt` to Aug10 ranges (were still on old Jul21/Aug02 lists while PROMOTION_GATE already Aug10).
2. Patched `scripts/window_aware_hunt_liveish.py` gates to **473.85 / 723.72** (was promoting against stale 432.94 / 423.35).
3. Updated `research/LIVEISH_GATE_WINDOWS.md` + `shared_findings.json` champion/broadcast.
4. Restarted liveish window-aware hunt from pool100 parent on corrected gates.
5. Left `watch_promote_full_eval` running. Continuous prepare stays **stopped** (83 days cached).

### Open issues
- Liveish search not yet beating Aug10 60d gate (**723.72** is much harder than old **423.35**).
- No deeply red axes; defensive baseline sample still **+$380**.
- User ping: not needed (no new global best / no promotion / swarm not stalled >2h — hunt active after gate fix).

### Best algorithm for handoff
- **pool100**: `min_daily_reward_pool=100`, spread_frac≈0.6676, size_mult≈1.291, inv soft/hard 35/100.
- Liveish: 30d +473.85 / 60d +723.72 / 90d +669.01. Optimistic expand: 30d +3192 / 60d +3635 / 90d +3172.

## Window-aware hunt (liveish Aug10) — 2026-09-13T09:06:55Z

Agent: `window-aware-hunt`. Parent: pool100 (`strategy_parent_liveish.py`). **No promotion.**

**Gate used:** liveish sample **>528.35** / 30d **>473.85** / 60d **>723.72** (Aug10 day lists). Optimistic-only wins ignored.

| Metric | Value |
|--------|------:|
| Tries (aug10 phase) | 15 |
| Window evals | 8 |
| Promotions | 0 |
| Beat both liveish windows | False |
| Elapsed sec | 3981.3 |

**Best trial (closest, still not a beat):** `max_abs_inv=80.0`  
sample 528.3479 (Δ -0.0021) / 30d 473.852 (Δ 0.002) / 60d 723.718 (Δ -0.002)

Notable near-misses / patterns under liveish:
- Tighter `mid_move_hard_cancel` and smaller `size_mult` **hurt sample** badly (liveish).
- `spread_frac=0.69` beat liveish 30d (+45.86) but **lost 60d hard** (−237).
- `pull_size_mult` 0.3–0.4: sample slightly below gate; 60d mixed.
- Tighter `portfolio_inv_cap` (250–300) crushed sample under liveish.
- `cancel_move=0.015` (tighter than harness 2¢) sample 494.64 < gate.
- No candidate beat **both** Aug10 liveish 30d and 60d.

Artifact: `results/window_aware_hunt.json` (phase `liveish_aug10_from_pool100`). Champion remains **pool100**.


## Wave5b PROMOTION — wave5b_pull24_p46_sf672 — 2026-09-13T10:17:24Z

- Knobs: `[('inv_pause_ticks', 24), ('pull_size_mult', 0.464), ('spread_frac', 0.672)]`
- Liveish sample **528.47** / 30d **496.98** / 60d **861.11**
- Beat pool100 Aug10 gates. Champion synced.


## Wave5/5b PROMOTION CONFIRMED — 2026-09-13T10:32:34Z

**New champion:** `wave5b_pull24_p46_sf672` (parent pool100)

| Knob | Value |
|------|------:|
| min_daily_reward_pool | 100 |
| spread_frac | **0.672** |
| size_mult | 1.291 |
| inv_soft / hard | 35 / 100 |
| inv_pause_ticks | **24** |
| pull_size_mult | **0.464** |

| Window (LIVEISH Aug10) | New | pool100 | Delta |
|------------------------|----:|--------:|------:|
| sample | **528.47** | 528.35 | +0.12 |
| 30d | **496.98** | 473.85 | **+23.13** |
| 60d | **861.11** | 723.72 | **+137.39** |

Independent verify: 30d=496.9795 soft=False / 60d=861.1133 soft=False — beats_pool100=True.

Bridge insight: pull24/p0.46 alone = +60d/−30d; mild spread 0.68 = +30d/−60d; **0.672 + pull24/0.464 bridges both**.

Artifacts: `results/promotion_wave5b_pull24_p46_sf672.json`, `results/swarm_wave5_status.json`, `research/PROMOTION_GATE.md`.


## Wave5 liveish hunt — 2026-09-13T10:38:57Z

**Champion unchanged: pool100** (Aug10 liveish gates 30d **473.85** / 60d **723.72** / sample **528.35**).

### Swarm
- 6 axes + joint hunt + promote watcher launched under `--liveish`.
- Wave5b bridge hunt (spread↔pull complementarity) followed.
- **Promotions: 0** (no dual liveish window beat).

### Closest signals
| Candidate | Sample | 30d | 60d | Note |
|-----------|-------:|----:|----:|------|
| pull24 / pull≈0.46 | 543.59 | 404.89 (−69) | **837.38 (+114)** | helps 60d, hurts 30d |
| spread0.68+pull0.4+pause10 | **558.38** | **586.98 (+113)** | 643.78 (−80) | helps 30d, hurts 60d |
| max_abs_inv=90 | ~528.35 | ~473.85 | ~723.72 | tie |
| free_explore best | 532.35 | 409.14 | 612.47 | fails both |

### Artifacts
- `results/swarm_wave5_status.json`
- `results/window_aware_hunt_wave5_joint.json`
- `results/window_aware_hunt_wave5b_bridge.json`


## Commander check — 2026-09-13T11:03:34Z

**Champion: `wave5b_pull24_p46_sf672`** (pool100 parent + pause24 / pull0.464 / spread0.672). Liveish Aug10 gates: sample **528.47** / 30d **496.98** / 60d **861.11**.

### What changed since last digest routine (07:52Z)
- Wave5b bridge hunt **PROMOTED** at 10:17Z (verified 10:31Z): liveish 30d **+23** / 60d **+137** vs pool100.
- Prior digest section at 10:38Z incorrectly said "champion unchanged / promotions 0" — **ignore that**; files + `PROMOTION_GATE.md` confirm wave5b.

### Swarm status
- Wave5 axes: finished (best sample liveish ~532 free_explore; pull axis helped 60d but hurt 30d alone).
- Stale `liveish_joint_hunt.py` (pool100 parent, old gates 473.85/723.72) **killed** mid try 26/28 — risk of promoting against obsolete gates / overwriting wave5b.
- Gate scripts retargeted to wave5b (`liveish_joint_hunt.py`, `window_aware_hunt_liveish.py`, `shared_findings.json`).
- **Wave6 launched** from wave5b parent under new gates:
  - joint: `scripts/window_aware_hunt_wave6_from_wave5b.py` (pid live)
  - axes `--liveish`: pull_size, pause_after_fill, free_explore, widen_spread
- `watch_promote_full_eval` still running. Continuous prepare stays **stopped**.

### Open issues
- Harder gate (60d **861**) — wave6 must beat both windows under identical `--liveish`.
- Leaderboard still polluted with optimistic wave3 sample PnLs; authoritative gate is liveish Aug10 only.
- No deeply red axes; defensive baseline sample still **+$380**.

### Best algorithm for handoff
- **wave5b_pull24_p46_sf672**: pool≥100, spread_frac=0.672, size_mult=1.291, inv soft/hard 35/100, inv_pause_ticks=24, pull_size_mult=0.464.
- Liveish Aug10: sample +528.47 / 30d +496.98 / 60d +861.11.

### User ping
- **YES** — profitable liveish 30d+60d promotion vs pool100 (first since overnight start).


## Liveish joint hunt (compensating pairs) — 2026-09-13T11:55:56.345325+00:00

Parent pool100. 36 trials, 19 window evals, 0 both-windows-positive vs pool100, promoted=False.

Best min-window-delta vs pool100: `spread_0p675` mut=`{"spread_frac": 0.675}` sample=514.5056 d30=7.019 d60=-14.3567.
Did not overwrite wave5b unless both windows also beat 496.98/861.11.
Artifact: `results/liveish_joint_hunt.json`.


## Wave6 widen_spread REJECT — 2026-09-13T12:05:24Z

Independent liveish re-eval of `research/agents/wave6-widen_spread/strategy_best.py`
(params `spread_frac≈0.664`, `min_half_spread=0.025`).

| Window | Candidate | Gate (wave5b) | Delta | Soft-reject |
|--------|----------:|--------------:|------:|:-----------:|
| sample | **544.03** | 528.47 | **+15.56** | false |
| **30d** | **403.29** | 496.98 | **-93.69** | false |
| **60d** | **835.96** | 861.11 | **-25.15** | false |

**Decision: REJECT** — need both 30d>496.98 and 60d>861.11. Champion unchanged: `wave5b_pull24_p46_sf672`.

Other wave6 axes (`free_explore`, `pause_after_fill`, `pull_size_after_adverse_fill`): sample tied at 528.47 — no window contenders.
wave6-from-wave5b best_so_far (sf673): sample 529.08 / 30d 498.01 / 60d 860.79 — 60d miss (already in hunt).

Artifacts: `results/promotion_wave6_widen_spread_sf664_mhs025.json`, `results/wave6_widen_reeval/`.


## Wave7 launch — 2026-09-13T12:06:24Z

Champion unchanged: **wave5b_pull24_p46_sf672** (after widen reject).

Launched liveish axes + joint from wave5b:
- joint `wave7-from-wave5b` pid **286866**
- skew_aggressive pid **286738**
- shrink_size pid **286763**
- near_mid_size pid **286789**
- cancel_on_mid_move pid **286814**
- inventory_hard_cap pid **286843**

Left wave6-from-wave5b joint (pid 265360) running.

Status: `results/swarm_wave7_status.json`

## Commander check — 2026-09-13T14:05:50Z

**Champion unchanged: `wave5b_pull24_p46_sf672`** (liveish Aug10 gates sample **528.47** / 30d **496.98** / 60d **861.11**).

### Swarm since last digest (12:06Z wave7 launch)
- **Wave6 joint DONE** (18 tries): best `sf673_pull24_p46` sample **529.08** / 30d **498.01** (+1.03) / 60d **860.79** (−0.32). **No promote.**
- **Wave6 axes DONE** earlier: widen sample **544** but windows miss (30d 403 / 60d 836) — already rejected; others sample-tied.
- **Wave7 axes DONE** (~12:28Z): skew_aggressive best sample **528.78** (+0.31, 2 keeps); shrink / near_mid / cancel_on_mid / inventory_hard_cap all **528.47** tie. **No window contenders.**
- **Wave7 joint** still alive (~try 17/20 at check): best `sf673_pull24_p47` sample 528.36 / 30d **+1.15** / 60d **−0.03**. Repeated pattern: tiny 30d lift, 60d flat-to-red. Left running.
- No deeply red axes (all best sample ≥ +528). Defensive baseline still green. Continuous prepare **STOPPED**.

### Commander actions this run
1. Diagnosed wave6/7 near-miss ridge around `spread_frac≈0.673` + pull≈0.46.
2. Wrote `scripts/window_aware_hunt_wave8_from_wave5b.py` (20 fine ridge / compensating mutations).
3. Launched **wave8** liveish from wave5b parent:
   - joint ridge hunt pid **320310**
   - axes: pull_size (8101), pause_after_fill (8102), free_explore (8103), size_by_reward_pool (8104), min_daily_reward_pool_fine (8105)
4. Updated `results/swarm_wave8_status.json`, `shared_findings.json` broadcast/insights.
5. Did **not** restart mega-download / continuous prepare.

### Open issues
- Dual-window liveish gate still tight; single-knob axes exhausted near champion.
- Leaderboard optimistic entries remain non-authoritative — gate is liveish Aug10 only.
- Wave7+wave8 joints both running (CPU heavy); expect wave7 to finish soon.

### Best algorithm for handoff
- **wave5b_pull24_p46_sf672**: pool≥100, spread_frac=0.672, size_mult=1.291, inv soft/hard 35/100, inv_pause_ticks=24, pull_size_mult=0.464.
- Liveish Aug10: sample +528.47 / 30d +496.98 / 60d +861.11.

### User ping
- **NO** — no new global best, no 30/60d promotion, swarm not stalled (>2h idle). Wave8 just launched; wave7 joint still progressing.


## Commander check — 2026-09-13T17:05:30Z

**Champion unchanged: `wave5b_pull24_p46_sf672`** (liveish Aug10 gates sample **528.47** / 30d **496.98** / 60d **861.11**).

### Wave8 complete (finished ~15:40Z) — no promotion
- **Joint** 20 tries / 12 window evals / 0 promotes. Best by score: `sf672_pull24_p46_skew48` sample **525.61** / 30d **683.96** (+187) / 60d **707.02** (−154). Classic 30d↑/60d↓ — **reject**.
- Ridge near-misses (sf672.8–673.5): sample ~529 / 30d ~+1.0–1.5 / 60d ~−0.13–0.32 — same cliff as wave6/7.
- **Axes** (pull/pause/free/size_by_pool/pool_fine): all best sample **528.47**, 0 keeps.
- Artifact: `results/window_aware_hunt_wave8_from_wave5b.json`

### New measurement — wave5b liveish ~90d
| Metric | Value |
|--------|------:|
| n_days | 83 (May14→Aug10; Jun12–17 gap) |
| **net_pnl** | **+547.23** |
| reward / trading | +634.74 / −87.51 |
| fills / max DD% | 901 / 1.27 |
| soft_reject | false |

Artifact: `results/wave5b_liveish_90d.json`. Full window below 60d gate (+861) due to early inventory bleed — known.

### Swarm status this check
- After wave8 finish (~15:40Z) swarm was **idle** (~80 min). Relatives: no deeply red axes; defensive baseline still green on sample.
- Continuous prepare **STOPPED**. No HF download.

### Commander actions this run
1. Recorded wave8 reject + 90d liveish +547.
2. Wrote `scripts/window_aware_hunt_wave9_from_wave5b.py` (20 skew×pull compensating mutations).
3. Launched **wave9** liveish from wave5b:
   - joint pid **23097** (skew mild + stronger pull/pause)
   - axes: skew_aggressive (9101), min_edge_vs_bbo (9102), vol_regime_filter (9103), two_sided_strict (9104), cancel_on_mid_move (9105), near_mid_size (9106)
4. Updated `results/swarm_wave9_status.json`, `shared_findings.json`.
5. Did **not** restart mega-download / continuous prepare.

### Open issues
- Dual-window liveish gate still tight; skew helps 30d but wrecks 60d without compensation.
- Single-knob axes near local optimum on wave5b parent.
- Leaderboard optimistic entries remain non-authoritative.

### Best algorithm for handoff
- **wave5b_pull24_p46_sf672**: pool≥100, spread_frac=0.672, size_mult=1.291, inv soft/hard 35/100, inv_pause_ticks=24, pull_size_mult=0.464.
- Liveish Aug10: sample +528.47 / 30d +496.98 / 60d +861.11 / **90d +547.23**.

### User ping
- **NO** — no new global best, no 30/60d promotion, swarm idle after wave8 was **<2h** before relaunch; wave9 now active.

## Commander check — 2026-09-13T20:05:40Z

**Champion unchanged: `wave5b_pull24_p46_sf672`** (liveish Aug10 gates sample **528.47** / 30d **496.98** / 60d **861.11** / 90d **547.23**).

### Wave10 complete (~19:49Z) — no promotion
- **Joint** 20 tries / 0 promotes. Artifact: `results/window_aware_hunt_wave10_from_wave5b.json`
- Strongest near-miss: `sf672_pool110_pull24` sample **517.97** (−10.5) / 30d **696.59** (+199.6) / 60d **992.52** (+131.4) — windows smash gates but **sample below** hard promote rule (need S>528.47 AND both windows AND ≥$5 combined margin).
- Other ridge/size/cancel/near-mid tries: either sample discard or tiny 30d↑/60d↓ noise.
- **Axes** done ~18:55Z: pull/pause/shrink/inv_hard/size_by_pool tied sample **528.47**; **widen_spread** sample **545.57** (2 keeps, spread_frac≈0.658).
- Independent widen window re-eval: **30d 407.15** (−89.8 vs gate) — **REJECT** (same failure mode as wave6 widen: sample↑ / 30d↓). 60d still running at digest time.

### Swarm status this check
- After wave10 joint finish (~19:49Z) swarm was idle **~12 min** (not >2h).
- No deeply red axes (all best sample ≥ +528). Defensive baseline still green.
- Continuous prepare **STOPPED**. No HF download.

### Commander actions this run
1. Recorded wave10 reject; flagged pool110 as dual-window winner needing sample recovery.
2. Window-reevaled wave10-widen_spread → 30d fail (407).
3. Wrote `scripts/window_aware_hunt_wave11_from_wave5b.py` (20 pool-ridge 102–120 + size/pull/pause/spread compensators).
4. Launched **wave11** liveish from wave5b:
   - joint pid live (pool ridge sample-recovery)
   - axes seeds 11101–11106: free_explore, cancel_on_mid_move, min_edge_vs_bbo, vol_regime_filter, two_sided_strict, near_mid_size
5. Updated `results/swarm_wave11_status.json`, `research/shared_findings.json`.
6. Did **not** restart mega-download / continuous prepare.

### Open issues
- Dual-window liveish gate still tight; pool≥110 helps windows a lot but costs sample ~$10 — wave11 hunting compensators.
- Widen/sample-only lifts keep failing 30d under liveish.
- Leaderboard optimistic entries remain non-authoritative.

### Best algorithm for handoff
- **wave5b_pull24_p46_sf672**: pool≥100, spread_frac=0.672, size_mult=1.291, inv soft/hard 35/100, inv_pause_ticks=24, pull_size_mult=0.464.
- Liveish Aug10: sample +528.47 / 30d +496.98 / 60d +861.11 / **90d +547.23**.

### User ping
- **NO** — no new global best, no 30/60d promotion, swarm idle after wave10 was **≪2h** before relaunch; wave11 now active.

## Commander check — 2026-09-13T23:03:31Z

**Current champion: `creative_df_max8_pool110`** (creative wave2 over day_boundary_flatten).

| Window | Liveish net | Max DD% |
|--------|------------:|--------:|
| sample | **+611.05** | 0.59 |
| **30d** | **+1676.34** | — |
| **60d** | **+2512.14** | — |
| **90d** (83d May14→Aug10) | **+2137.37** | 3.29 |

Overlay: `day_flatten=true`, `day_flatten_max_net=8`, `min_daily_reward_pool=110`.
Artifacts: `results/promotion_creative_df_max8_pool110.json`, `results/creative_df_max8_pool110_liveish_90d.json`, `research/PROMOTION_GATE.md`.

### Since prior digest (20:05Z wave5b era)
- Creative wave1 promoted **day_boundary_flatten** over wave5b (sample 651.39 / 30d 1431.56 / 60d 1979.75 / 90d 1074.61).
- Creative wave2 promoted **df_max8_pool110** (sample 611.05 / 30d 1676.34 / 60d 2512.14 / 90d **2137.37**).
- Wave11 (knob ridge on wave5b) finished earlier with no promote; creative structural search superseded.
- Continuous prepare **STOPPED** (63 slim days May14→Jul21). No HF download.

### Creative wave3 (retargeted on df_max8_pool110)
- Status: `window_eval` (started 2026-09-13T22:19:18.145996+00:00); hunt pid `202372`.
- Gates: sample>611.05 / 30d>1676.34 / 60d>2512.14 (liveish).
- Sample sweep **complete** (25 candidates). Leaders:

| Rank | id | sample | dd% | fills | trading |
|-----:|----|-------:|----:|------:|--------:|
| 1 | `ovn_reduce` | **+783.97** | 0.4511 | 478 | 317.148 |
| 2 | `ovn_reduce_0_8` | **+774.69** | 0.3456 | 422 | 342.903 |
| 3 | `sess12_ovn` | **+671.47** | 0.6728 | 506 | 279.0439 |
| 4 | `dfgate` | **+611.05** | 0.592 | 601 | 194.6159 |
| 5 | `dfgate_vol01` | **+611.05** | 0.592 | 601 | 194.6159 |
| 6 | `dfgate_pool110` | **+611.05** | 0.592 | 601 | 194.6159 |
| 7 | `sess12` | **+441.38** | 1.0291 | 692 | 75.6447 |
| 8 | `sess12_max8` | **+441.38** | 1.0291 | 692 | 75.6447 |

**Advance to windows** (sample ≥ 600): `ovn_reduce`, `ovn_reduce_0_8`, `sess12_ovn`, `dfgate*`.
Sample-red modes (do not keep iterating blindly): `carry_budget` (−135…−338), `age60` (−107), `ban1p5/ban2p0` (~−72).
Pre-retarget note: overnight on *old* max_net=5 base had 60d≈1978 (missed old 1979.75 by ~$1.5); re-eval under new base+gates in flight.

### Commander actions this run
1. Diagnosed: no deeply stuck red axes; swarm healthy; wave3 actively window-evaluating overnight leaders.
2. Synced stale `shared_findings.json` champion/gates from wave5b → **creative_df_max8_pool110**.
3. Left `scripts/creative_wave3_hunt.py` running (auto promote if both windows clear).
4. Did **not** restart mega-download / continuous prepare.
5. Digest updated; window results / promote decision pending end of wave3.

### Open issues
- Wave3 window gates are steep (60d>2512); overnight may again lift sample while missing dual windows.
- `shared_findings` / digest lagged the creative promote until this check.
- Absolute liveish PnL still optimistic vs true live (LIVE_REALISM.md).

### Best algorithm for handoff (until wave3 windows finish)
- **creative_df_max8_pool110**: day_flatten + max_net=8 + pool≥110.
- Liveish: sample +611.05 / 30d +1676.34 / 60d +2512.14 / **90d +2137.37**.

### User ping
- **PENDING windows** — no new promote yet this check; swarm not stalled. Will ping only if wave3 promotes or >2h idle.

## Commander check closeout — 2026-09-13T23:33:04Z

### Creative wave3 COMPLETE — no promote
| id | sample | 30d | 60d | vs gates |
|----|-------:|----:|----:|----------|
| ovn_reduce | **+783.97** | 1598.62 | **2540.89** | 30d −77.7 / 60d **+28.7** |
| sess12_ovn | +671.47 | 1599.27 | **2538.09** | 30d −77.1 / 60d **+25.9** |
| ovn_reduce_0_8 | +774.69 | 1558.65 | 2400.21 | both miss |
| dfgate* | 611.05 | skipped | skipped | champion clones |

Dead sample modes: carry_budget, age60, tox bans <3¢.
Artifacts: `results/creative_wave3_findings.md`, `results/swarm_creative_wave3_status.json`.

### Commander redirect — creative wave4 launched
- Mandate: overnight 30d recovery (shorter quiet window / milder size_mult / pool+max_net ridge).
- Pid: **217752**; status `results/swarm_creative_wave4_status.json`; log `results/creative/wave4_hunt.log`.
- Agenda: `research/CREATIVE_AGENDA_WAVE4.md`.

### Best algorithm for handoff
- **creative_df_max8_pool110**: day_flatten + max_net=8 + pool≥110.
- Liveish: sample +611.05 / 30d +1676.34 / 60d +2512.14 / **90d +2137.37**.

### User ping
- **NO** — no new global best / no 30/60d promotion this cycle. Swarm not stalled (wave4 active). Near-miss overnight noted for next digest if it promotes.

