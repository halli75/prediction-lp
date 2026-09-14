# Continuous L2 baseline (partial → expanding)

- **Mode**: continuous HF `orderbook_1min` day-at-a-time
- **Allowlist**: 65 YES tokens from `data/top_reward_markets.json`
- **Days in this eval**: 1160168 price rows; see manifest
- **Primary holdout_net_pnl**: **1532.04**
- holdout_reward_pnl: 619.1238
- holdout_trading_pnl: 912.915
- holdout_max_drawdown_pct: 2.8683
- soft_reject: False
- train_net_pnl: -1964.1534
- Generated: 2026-09-13T04:35:36.745825+00:00

Note: only ~36/65 allowlist assets appear in early May–Jun books; more markets appear later in the window.
