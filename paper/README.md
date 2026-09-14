# Paper live LP trader (simulate only)

Polls **public** Polymarket CLOB books for reward markets, runs the frozen champion
`Strategy.quote` each cycle, and **paper-fills** when mid crosses resting quotes.
Tracks cash / inventory / equity / estimated LP rewards.

**Never places real CLOB orders. Never uses private keys or API credentials.**

## Champion

- Label: `creative_wave5_fr_w20_t3_b30`
- Source: `strategy.py` / `research/champions/strategy_current_best.py`
- Defaults: day_flatten, max_net=8, pool≥110, overnight_quiet reduce_only UTC 0–3,
  fill_rate_window=20 / threshold=3 / brake=30
- Merged liveish strategy cfg: `near_mid_size_mult=0.5`, `near_mid_dist=0.02`,
  `portfolio_inv_cap=400`, `cancel_move=0.02`

## Fill model (honest paper)

- Quote latency: 1 poll cycle (quotes apply next cycle)
- Mid path-cross vs resting bid/ask; partial fill `max_fill_frac=0.40`
- Light adverse boost from recent mid delta
- Rewards: `sim.rewards.sample_reward_usd` on resting quote scores (~scaled by poll rate)

## Run

```bash
cd /workspace/polymarket-lp-autoresearch
mkdir -p results/paper
nohup .venv/bin/python -u paper/run_paper.py \
  --capital 10000 --poll-sec 15 \
  --status-path results/paper/status.json \
  --fills-csv results/paper/fills.csv \
  --equity-csv results/paper/equity.csv \
  --pid-file results/paper/paper.pid \
  > results/paper/run.log 2>&1 &
```

Market list is refreshed at start and hourly into `data/markets_live.json`
(open markets with `daily_reward_pool >= 110`, ended markets skipped).

## Outputs

| Path | Meaning |
|------|---------|
| `results/paper/status.json` | Latest cycle status (equity, fills, positions) |
| `results/paper/fills.csv` | Paper fill ledger |
| `results/paper/equity.csv` | Equity time series |
| `results/paper/run.log` | stdout/stderr |
| `results/paper/paper.pid` | PID while running |
| `data/markets_live.json` | Live reward-market allowlist |

## Stop

```bash
kill $(cat results/paper/paper.pid)   # graceful SIGTERM
# or: pkill -f paper/run_paper.py
```

## Safety

- Read-only HTTP to `clob.polymarket.com` and `gamma-api.polymarket.com`
- No order posting endpoints, no wallet / private key usage
