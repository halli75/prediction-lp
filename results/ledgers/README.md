# Trade ledgers (champion `df_max8_pool110`)

These CSVs come from a **liveish** backtest of `research/champions/strategy_current_best.py`
with overlay `day_flatten=true`, `day_flatten_max_net=8`, `min_daily_reward_pool=110`
(via `LIVEISH_STRATEGY_CFG` + `liveish_engine_config`).

**`*_fills.csv`** — one row per engine fill. `action_plain` says whether our resting bid was hit
(Bought YES) or ask was lifted (Sold YES). `edge_vs_mid_cents` is how many cents better than mid
we got at fill time. Inventory and cash columns are post-fill.

**`*_round_trips.csv`** — FIFO-matched buys and sells per market. Closed rows have
`exit_reason=opposite_fill`. Leftover inventory at the end of the window is marked to the last mid
(`status=open_at_end`, `exit_reason=eod_mark`). `gross_pnl_usd` is share PnL only (excludes LP rewards).

**`*_summary.json`** — net/reward/trading PnL from the engine metrics, fill counts (should match
`n_fills`), and top markets by activity / abs round-trip PnL. Prefer engine `net_pnl` as the
checksum (~2137.37 on the 90d window).
