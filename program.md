# Program: Polymarket LP Market-Making Autoresearch

## Goal
Maximize **holdout net PnL** for a Polymarket-only liquidity-providing (LP) market-making strategy
with $10,000 starting capital, subject to drawdown constraints.

## Fixed interface
- `prepare.py` — downloads/caches historical mid prices (+ optional trades). **Do not edit.**
- `evaluate.py` — runs train/holdout backtest and prints JSON metrics. **Do not edit.**
- `strategy.py` — **EDIT THIS**. Quoting / inventory / reward-aware logic.

## Metric
Primary: `holdout_net_pnl` (USD), including trading PnL + LP reward income − fees.

Soft reject (discard experiment even if PnL improves):
- `holdout_max_drawdown_pct` > 25% of starting capital (i.e. DD > $2,500 on $10k)

Secondary diagnostics (logged, not optimized directly):
- `holdout_reward_pnl`, `holdout_trading_pnl`, `holdout_fees`, fill count, inventory RMS

## Strategy contract
`strategy.py` must expose:

```python
class Strategy:
    def __init__(self, config: dict | None = None): ...
    def quote(self, state: dict) -> dict:
        """
        state keys (per market tick):
          ts, market_id, mid, best_bid, best_ask (may equal mid±tick if synthetic),
          inv_yes, inv_no, cash, capital0, rewards_min_size, rewards_max_spread,
          daily_reward_pool, competition_q
        returns:
          {
            "bid_price": float | None,   # YES bid
            "ask_price": float | None,   # YES ask
            "bid_size": float,           # shares
            "ask_size": float,
          }
        """
```

## Search instructions (for the autoresearch agent)
1. Read `strategy.py` and recent `results/experiments.jsonl`.
2. Propose a small, focused change (spread, skew, size, reward targeting, inventory caps).
3. Edit only `strategy.py`.
4. Run `python evaluate.py` and parse JSON metrics.
5. If holdout_net_pnl improves AND max DD ≤ 25%: `git add strategy.py && git commit -m "..."`.
   Else: `git checkout -- strategy.py`.
6. Append one JSON line to `results/experiments.jsonl`.
7. Repeat.

## Constraints
- Polymarket only (no Kalshi).
- Do not download multi-GB datasets.
- Keep changes reversible via git.


## Data regime
Continuous HuggingFace `orderbook_1min` L2 (May14–Aug10, allowlist top reward markets). See README / `data/manifest.json`.
Do not download the TB raw `orderbook` stream. During search, do not re-run full prepare.
