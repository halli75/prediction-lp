# Baseline report — continuous May–Aug 2026 (phase 3)

Generated from a real `evaluate.py` run on the **continuous-within-archive**
`orderbook_1min` cache. **Not comparable** to the phase-1 $244 / phase-2 sparse
$424 figures (different days, tokens, bars, and competition floor).

**Not live-trading ready.**

## Data

| Field | Value |
|-------|--------|
| Mode | `continuous_day_l2` |
| Source | HuggingFace `Joseph3222/polymarket-orderbook` / `orderbook_1min` |
| Window | **2026-05-01 → 2026-08-10** (96 UTC days) |
| Gap | Jun 12–17 missing |
| Price rows | 2,014,670 (5-min last-print; slim is 1-min) |
| Markets | **79** YES tokens (Gamma top-reward allowlist; 1 requested name had no L2) |
| Cache | slim ≈ 24.7 MB; raw day + HF cache deleted after each filter |
| Train / holdout | 1,450,564 / 564,106 rows |

## Capital & split

- Start capital: **$10,000**
- Time-based 75/25 on concatenated timestamps
- Soft-reject: holdout max DD **> 25%** of capital

## Baseline metrics

| Metric | Train | Holdout |
|--------|------:|--------:|
| **Net PnL** | **−$96.68** | **+$1,178.51** |
| % of $10k | −0.97% | **+11.79%** |
| End equity | $9,903.32 | $11,178.51 |
| Max DD (% of capital) | 16.29% | 10.27% |
| Reward PnL | — | $2,171.75 |
| Trading PnL | — | −$982.76 |
| Fees | — | $10.48 |
| Fills | 2,807 | 2,412 |
| Soft reject | — | **false** |

Primary: **`holdout_net_pnl = 1178.5084`**. Raw JSON: `results/baseline_metrics.json`.

## How to reproduce

```bash
python scripts/discover_reward_markets.py --max-tokens 80
python prepare.py --bar-minutes 5
python evaluate.py
python scripts/run_autoresearch.py -n 40
```

## Limitations

Sparse-day claims are retired for this cache: this is **every archive day** in
May–Aug except the known Jun 12–17 hole. It is still not live trading.
Reward rates are current Gamma constants. Competition is BBO + exogenous floor
(no full L2 JSON in slim). Evaluate clock is 5-min.
