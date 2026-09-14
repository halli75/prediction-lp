# Creative wave3 findings

Started: 2026-09-13T22:19:18.145996+00:00
Finished: 2026-09-13T23:33:04.035428+00:00
Champion parent: creative_df_max8_pool110
Gates: sample>611.05 / 30d>1676.34 / 60d>2512.14 (liveish)
Promoted: False

## Modes

- session_flatten
- inventory_age_flatten
- overnight_quiet
- carry_budget
- toxic_market_day_ban
- day_flatten_harvest_gate

## Sample sweep (liveish)

| id | sample | dd% | fills | notes |
|----|-------:|----:|------:|-------|
| ovn_reduce | 783.97 | 0.4511 | 478 |  |
| ovn_reduce_0_8 | 774.69 | 0.3456 | 422 |  |
| sess12_ovn | 671.47 | 0.6728 | 506 |  |
| dfgate | 611.05 | 0.592 | 601 | window skipped (champ clone) |
| dfgate_vol01 | 611.05 | 0.592 | 601 | window skipped (champ clone) |
| dfgate_pool110 | 611.05 | 0.592 | 601 | window skipped (champ clone) |
| sess12 | 441.38 | 1.0291 | 692 |  |
| sess12_max8 | 441.38 | 1.0291 | 692 |  |
| sess8 | 355.87 | 1.8319 | 806 |  |
| ovn_sz03 | 342.98 | 1.0619 | 572 |  |
| age240 | 284.78 | 2.6023 | 1159 |  |
| sess12_max3 | 268.98 | 2.5042 | 1012 |  |
| age120 | 171.59 | 3.513 | 1223 |  |
| sess12_age120 | 171.06 | 3.5114 | 1223 |  |
| ovn_ban2 | 148.92 | 4.9529 | 1178 |  |
| ban3p0 | 135.91 | 3.17 | 1186 |  |
| ban1p5 | -71.74 | 5.2316 | 1281 | sample-red |
| ban2p0 | -72.94 | 5.2376 | 1281 | sample-red |
| ban2_age120 | -106.32 | 5.4595 | 1442 | sample-red |
| age60 | -106.98 | 5.8821 | 1372 | sample-red |
| carry120 | -135.95 | 2.7174 | 780 | sample-red |
| carry80 | -136.88 | 3.8798 | 824 | sample-red |
| carry80_dfgate | -136.88 | 3.8798 | 824 | sample-red |
| age120_carry80 | -177.07 | 3.4527 | 669 | sample-red |
| carry50 | -337.68 | 3.7639 | 810 | sample-red |

## Window evals

| id | sample | 30d | 60d | beats |
|----|-------:|----:|----:|:-----:|
| ovn_reduce | 783.97 | 1598.6235 | 2540.89 | False |
| ovn_reduce_0_8 | 774.69 | 1558.6521 | 2400.2149 | False |
| sess12_ovn | 671.47 | 1599.2658 | 2538.0933 | False |
| dfgate* | 611.05 | skipped | skipped | False |

## Notes
- **No promote.** Overnight quiet is the structural near-miss: sample and 60d improve, 30d regresses ~$77–118 vs gate.
- Best near-miss: `ovn_reduce` sample +783.97 / 30d **1598.62** (−77.7 vs 1676.34) / 60d **2540.89** (+28.7 vs 2512.14).
- `sess12_ovn` same shape: 30d 1599.27 / 60d 2538.09.
- `ovn_reduce_0_8` (quiet until 08:00) worse on both windows.
- Dead on sample: carry_budget, age60, tox bans <3¢.
- Commander stopped dfgate* window clones and launched wave4 overnight-30d-recovery.
