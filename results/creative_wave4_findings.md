# Creative wave4 findings

Started: 2026-09-13T23:33:04.064028+00:00
Champion parent: creative_df_max8_pool110
Gates: sample>611.05 / 30d>1676.34 / 60d>2512.14 (liveish)
Promoted: True → ovn_e3

## Mandate
Recover overnight 30d (~$78 miss on wave3 ovn_reduce) without losing sample/60d edge.

## Sample sweep (liveish)

| id | sample | dd% | fills | notes |
|----|-------:|----:|------:|-------|
| ovn_pool100 | 832.42 | 0.4387 | 480 | |
| ovn_max10 | 791.22 | 0.4511 | 476 | |
| ovn_pool105 | 785.38 | 0.4496 | 478 | |
| ovn_s0_e6_ctrl | 783.97 | 0.4511 | 478 | |
| ovn_pool108 | 783.97 | 0.4511 | 478 | |
| ovn_max7 | 783.97 | 0.4511 | 478 | |
| ovn_pool115 | 783.55 | 0.4511 | 478 | |
| ovn_max6 | 771.34 | 0.4511 | 480 | |
| ovn_e4_max10 | 737.42 | 0.6604 | 490 | |
| ovn_e3 | 726.73 | 0.5948 | 573 | |
| ovn_e4_pool105 | 724.90 | 0.6603 | 491 | |
| ovn_e4 | 723.45 | 0.6604 | 491 | |
| ovn_e5_max10_p105 | 698.81 | 0.98 | 492 | |
| ovn_e5 | 690.12 | 0.98 | 494 | |
| ovn_s1_e6 | 676.20 | 0.5993 | 627 | |
| ovn_s2_e6 | 607.40 | 0.5283 | 658 | |
| ovn_sz085 | 362.77 | 0.7035 | 478 | |
| ovn_sz05_e4 | 349.28 | 1.041 | 553 | |
| ovn_sz05 | 317.33 | 1.3186 | 599 | |
| ovn_sz07 | 298.31 | 1.0917 | 613 | |
| ovn_sz07_pool105 | 287.06 | 1.1679 | 630 | |

## Window evals

| id | sample | 30d | 60d | beats |
|----|-------:|----:|----:|:-----:|
| ovn_pool100 | 832.42 | 1608.3767 | 1950.243 | False |
| ovn_max10 | 791.22 | 1697.6336 | 2376.7274 | False |
| ovn_pool105 | 785.38 | 1507.7831 | 2431.0237 | False |
| ovn_s0_e6_ctrl | 783.97 | 1598.6235 | 2540.89 | False |
| ovn_pool108 | 783.97 | 1598.6235 | 2540.89 | False |
| ovn_max7 | 783.97 | 1598.6235 | 2481.6107 | False |
| ovn_pool115 | 783.55 | 1504.6347 | 2334.0703 | False |
| ovn_max6 | 771.34 | 1352.9416 | 2284.887 | False |
| ovn_e4_max10 | 737.42 | 1645.4544 | 2471.5548 | False |
| ovn_e3 | 726.73 | 1703.1739 | 2710.2515 | True |
