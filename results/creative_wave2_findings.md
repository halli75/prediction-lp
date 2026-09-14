# Creative wave2 findings

Started: 2026-09-13T20:57:13.740170+00:00
Champion parent: creative_day_boundary_flatten
Gates: sample>651.39 / 30d>1431.56 / 60d>1979.75 (liveish)
Promoted: True → df_max8_pool110

## Sample sweep (liveish)

| id | sample | dd% | fills | notes |
|----|-------:|----:|------:|-------|
| df_max10 | 669.94 | 0.6988 | 622 | |
| df_tox_30_1p0 | 669.19 | 0.4956 | 509 | |
| df_pool95 | 652.64 | 0.4764 | 673 | |
| df_max5_ctrl | 651.39 | 0.4787 | 673 | |
| df_global | 651.39 | 0.4787 | 673 | |
| df_max8 | 617.89 | 0.4897 | 634 | |
| df_pool102 | 614.46 | 0.4849 | 670 | |
| df_max8_pool110 | 611.05 | 0.592 | 601 | |
| df_pool110 | 597.75 | 0.4943 | 633 | |
| df_tox_20_1p5 | 594.77 | 0.5723 | 579 | |
| df_pool105 | 590.67 | 0.4951 | 668 | |
| df_pool120 | 589.39 | 0.4943 | 632 | |
| df_max3_tox40 | 537.70 | 0.7281 | 628 | |
| df_tox_40_1p5 | 495.00 | 1.1701 | 537 | |
| df_max2 | 384.74 | 2.6872 | 1124 | |
| df_max3 | 384.38 | 2.6872 | 1124 | |
| df_tox_60_2p0 | 380.95 | 1.237 | 549 | |
| df_half015_sz25 | 110.32 | 4.719 | 989 | |
| df_agg_trig05 | 68.32 | 2.119 | 904 | |
| df_agg_size3 | -1.88 | 3.6655 | 1124 | |
| df_agg_mild | -57.76 | 4.5851 | 1132 | |
| df_agg_trig033 | -186.07 | 3.8519 | 1218 | |

## Window evals

| id | sample | 30d | 60d | beats |
|----|-------:|----:|----:|:-----:|
| df_max10 | 669.94 | 1427.0554 | 2068.1103 | False |
| df_tox_30_1p0 | 669.19 | 1511.5437 | 1972.5724 | False |
| df_pool95 | 652.64 | 1553.6096 | 2014.9232 | True |
| df_max5_ctrl | 651.39 | 1431.5577 | 1979.7532 | False |
| df_global | 651.39 | 1431.5577 | 1979.7532 | False |
| df_max8 | 617.89 | 1484.8772 | 2186.5116 | True |
| df_pool102 | 614.46 | 1634.8983 | 2431.0702 | True |
| df_max8_pool110 | 611.05 | 1676.3353 | 2512.1413 | True |


## Notes
- Hard promote gates only: liveish 30d>1431.56 AND 60d>1979.75. Sample preference soft.
- Promoted `df_max8_pool110` has sample 611.05 (< prior preferred 651.39) but strongest dual-window (+1676 / +2512).
- Near-misses: `df_max10` 60d+++ but 30d 1427 fail by ~$4.5; `df_tox_30_1p0` 30d+++ but 60d 1972 fail by ~$7.
- Flatten aggressiveness overlays all hurt sample badly.
- 90d on *prior* champion day_boundary_flatten (max_net=5, pool100): **+1074.61** vs wave5b +547.23.

## Near-miss: df_max10 (independent verify)

Fresh liveish re-eval: sample 669.94 / 30d **1427.06** / 60d 2068.11.
30d stayed ~$4.50 under prior gate 1431.56 — **not promoted**. See `results/creative_df_max10_near_miss.md`.

## Promoted: df_max8_pool110

day_flatten_max_net=8 + min_daily_reward_pool=110 → sample 611.05 / 30d 1676.34 / 60d 2512.14.
Also beat: df_pool102 (1634.90/2431.07), df_max8 (1484.88/2186.51), df_pool95 (1553.61/2014.92).
Best by 30d+60d sum: **df_max8_pool110**.
