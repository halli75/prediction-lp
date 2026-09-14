# Creative wave5 early-bleed findings

Started: 2026-09-14T03:02:44.900710+00:00
Champion parent: creative_wave4_ovn_e3
Gates: sample>726.73 / 30d>1703.17 / 60d>2710.25 / 90d_promote>2109.0
Promoted: True → fr_w20_t3_b30

## Mandate
Fix May/early-June leftover-inventory bleed without sacrificing 30d/60d.

## Modes implemented
- inv_age_flatten / max_inv_age_ticks (existing WAVE3, exercised)
- warm_start (warm_days, warm_size_frac, warm_max_net, stronger pull/pause)
- fill_rate_brake (sliding window fills → pause add / shrink)
- daily_trading_stop (day MTM < -X → reduce_only or empty)

## Sample sweep (liveish)

| id | sample | dd% | fills | vs champ |
|----|-------:|----:|------:|---------:|
| fr_w20_t3_b30 | 719.43 | 1.0509 | 381 | -7.30 |
| dts120_empty | 713.81 | 0.3739 | 296 | -12.92 |
| fr_w20_t3_b30_sz07 | 690.09 | 1.1387 | 375 | -36.64 |
| fr_w40_t4_b60 | 685.97 | 0.6635 | 468 | -40.76 |
| dts80_empty | 667.55 | 0.5816 | 258 | -59.18 |
| fr_w15_t2_b20 | 664.04 | 1.0585 | 405 | -62.69 |
| wcal_jun01_age240_dts80 | 635.25 | 0.2734 | 387 | -91.48 |
| age240_dts80 | 604.47 | 1.3911 | 540 | -122.26 |
| age480 | 592.62 | 0.8774 | 748 | -134.11 |
| wcal_jun15_sz05_net5 | 579.26 | 0.5358 | 562 | -147.47 |
| wcal_jun15_sz07_net3 | 562.86 | 0.6005 | 580 | -163.87 |
| dts80 | 545.94 | 0.9341 | 295 | -180.79 |
| wcal_jun01_sz05_net5 | 515.45 | 0.6121 | 650 | -211.28 |
| wcal_jun01_sz07_net5 | 515.45 | 0.6121 | 650 | -211.28 |
| wcal_jun01_sz05_net3 | 511.16 | 0.6088 | 654 | -215.57 |
| warm14_sz05_net5 | 498.46 | 1.0006 | 534 | -228.27 |
| age480_fr_w20 | 473.63 | 1.7419 | 836 | -253.10 |
| warm7_sz07_net5 | 411.08 | 1.4922 | 687 | -315.65 |
| wcal_jun15_age240 | 407.58 | 1.9376 | 942 | -319.15 |
| wcal_jun01_age480 | 386.55 | 0.9075 | 870 | -340.18 |
| wcal_jun01_age240_fr | 368.32 | 1.764 | 920 | -358.41 |
| wcal_jun01_age240 | 338.79 | 1.9376 | 1123 | -387.94 |
| age240 | 297.72 | 3.5919 | 1051 | -429.01 |
| dts120 | 283.43 | 3.6256 | 686 | -443.30 |
| dts40 | 273.59 | 3.0929 | 728 | -453.14 |
| dts160 | 267.71 | 2.6463 | 908 | -459.02 |
| age120 | 162.15 | 5.0065 | 1261 | -564.58 |
| age60 | 69.14 | 5.4285 | 1226 | -657.59 |
| age30 | 54.95 | 5.1933 | 1131 | -671.78 |

## Window evals

| id | sample | 30d | 60d | 90d | beats_30_60 | clears_90 |
|----|-------:|----:|----:|----:|:-----------:|:---------:|
| fr_w20_t3_b30 | 719.43 | 1711.3042 | 2737.8836 | 2946.1239 | True | True |
| dts120_empty | 713.81 | 1703.1739 | 2702.8107 | None | False | None |
| fr_w20_t3_b30_sz07 | 690.09 | 1711.3042 | 2841.416 | 2594.3413 | True | True |
| fr_w40_t4_b60 | 685.97 | 1739.4459 | 2651.4818 | None | False | None |
| dts80_empty | 667.55 | 1649.8837 | 2678.5518 | None | False | None |
| fr_w15_t2_b20 | 664.04 | 1570.3235 | 2738.8069 | None | False | None |
