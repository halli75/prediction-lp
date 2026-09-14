# Creative Wave 1 Findings

Updated: 2026-09-13T21:12:20.036571+00:00

Champion compared: `wave5b_pull24_p46_sf672` liveish gates sample **528.47** / 30d **496.98** / 60d **861.11**.

## Modes implemented
1. force_flatten
2. day_boundary_flatten
3. toxicity_blackout
4. dynamic_top_k
5. harvest_or_flatten
6. weekly_reset ablation (ops, no strategy change)

Strategy fork: `research/creative/strategy_creative_base.py` (champion file untouched).
Agenda: `research/CREATIVE_AGENDA.md`.

## Sample sweep (liveish)

| id | sample | dd% | soft | vs wave5b sample |
|----|-------:|----:|:----:|-----------------:|
| **day_boundary_flatten** | **651.39** | 0.48 | False | **+122.92** |
| tox_blackout_40_1p5 | 527.08 | 0.34 | False | -1.39 |
| tox_blackout_60_1p0 | 492.20 | 0.57 | False | -36.27 |
| harvest_plus_tox | 328.24 | 0.78 | False | |
| dynamic_top_k_12 | 270.96 | 0.30 | False | |
| harvest_or_flatten | 262.16 | 0.84 | False | |
| force_day_tox | 254.25 | 1.85 | False | |
| dynamic_top_k_8 | 229.01 | 0.30 | False | |
| dynamic_top_k_5 | 198.58 | 0.27 | False | |
| force_plus_tox | 172.57 | 2.03 | False | |
| topk8_harvest | 170.47 | 1.14 | False | |
| force_flatten_default | 90.73 | 4.58 | False | |
| harvest_day_flatten | 87.65 | 2.79 | False | |
| day_flatten_max2 | 54.29 | 4.25 | False | |
| force_flatten_trig033 | -192.26 | 3.82 | False | |

## Window evals (serious candidates)

| id | sample | 30d | 60d | beats both gates |
|----|-------:|----:|----:|:----------------:|
| **day_boundary_flatten** | **651.39** | **1431.56** | **1979.75** | **YES** |
| tox_blackout_40_1p5 | 527.08 | 485.96 | 840.20 | no (both below) |
| tox_blackout_60_1p0 | 492.20 | 477.21 | 574.59 | no (both below) |

wave5b ref: sample 528.47 / 30d 496.98 / 60d 861.11

## Promote: **YES** — `creative_day_boundary_flatten`

- Files: `research/champions/strategy_creative_day_boundary_flatten.py` = `strategy_current_best.py` = root `strategy.py` (self-contained bake)
- Overlay: `day_flatten=True`, `day_flatten_max_net=5`
- Verified promoted sample re-eval: **651.39**
- Artifact: `results/promotion_creative_day_boundary_flatten.json`
- Gate doc updated: `research/PROMOTION_GATE.md`
- Inventory policy unchanged (soft 35 / hard 100); flatten is reduce-only / never adds past hard

## Weekly-reset ablation (wave5b, liveish, independent $10k / 7d)

| Comparison | Weekly sum | Continuous | Δ |
|------------|----------:|-----------:|--:|
| Full ~83d | **2754.16** | **547.23** | **+2206.93** |
| 60d gate | **2037.32** | **861.11** | **+1176.20** |

**Headline:** restarting the book weekly crushes continuous — multi-week inventory path-dependence is the bleed. Complements day_boundary_flatten (intra-strategy UTC flatten) as an ops lever.

Artifacts: `results/creative_weekly_reset_ablation.json` + `.md`

## Interpretation
- Paying to exit early via force_flatten alone **hurts** (overtrading / adverse fills).
- **UTC day-boundary flatten** is the structural win: kills multi-day carry while preserving reward harvest within-day.
- Tox blackout ≈ champion on sample but loses on 30/60.
- dynamic_top_k / harvest_or_flatten under-deploy rewards on sample.
- Wave11 left running (untouched).
