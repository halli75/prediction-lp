# creative_df_max8_pool110 liveish 90d

| Window | df_max8_pool110 | day_boundary_flatten | wave5b | Δ vs day_flatten | Δ vs wave5b |
|--------|----------------:|---------------------:|-------:|-----------------:|------------:|
| 90d (May14→Aug10, 83d) | **2137.37** | 1074.61 | 547.23 | **+1062.76** | **+1590.14** |
| sample | 611.05 | 651.39 | 528.47 | -40.34 | +82.58 |
| 30d | 1676.34 | 1431.56 | 496.98 | +244.78 | +1179.36 |
| 60d | 2512.14 | 1979.75 | 861.11 | +532.39 | +1651.03 |

soft_reject=False, max_dd_pct=3.2874, n_fills=4195, reward=3616.5535, trading=-1479.1789.

Overlay: `{"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110}` on `strategy_current_best.py`.
Same `--liveish` flags as promotion. Artifact: `results/creative_df_max8_pool110_liveish_90d.json`

**Takeaway:** 90d roughly **doubles** prior day_flatten champion (+1063) and ~**4x** wave5b (+1590), with lower max DD (3.2874% vs day_flatten 7.29%). Sample is slightly under prior day_flatten sample but windows dominate.
