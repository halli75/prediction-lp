# Baseline report — Polymarket LP autoresearch

Generated from a real `evaluate.py` run on the prepared sparse-day L2 cache.

## Data

| Field | Value |
|-------|--------|
| Mode | `sparse_day_l2` (NOT continuous 90-day L2) |
| Source | HuggingFace `Joseph3222/polymarket-orderbook` / `orderbook_1min` |
| Sparse days | **2026-05-14, 2026-06-01, 2026-06-25, 2026-07-20, 2026-08-06** |
| Calendar span | 2026-05-14 → 2026-08-06 (~3 months of calendar coverage, 5 sampled days) |
| Price rows | 46,783 (1-min YES mids + BBO + L2-derived competition) |
| Markets | 7 (see below) |
| Cache size | slim days ≈ 4.2 MB (full day files deleted after DuckDB filter) |

### Markets

| Key | Question | Daily pool (Gamma current) | min size | max spread ¢ |
|-----|----------|----------------------------|----------|--------------|
| fed_m50 | Fed decrease 50+ bps Sep 2026 | $50 | 50 | 4.5 |
| fed_m25 | Fed decrease 25 bps Sep 2026 | $100 | 200 | 4.5 |
| fed_0 | Fed no change Sep 2026 | $1000 | 200 | 4.5 |
| fed_p25 | Fed increase 25 bps Sep 2026 | $1000 | 200 | 4.5 |
| fed_p50 | Fed increase 50+ bps Sep 2026 | $50 | 200 | 4.5 |
| iran | US invade Iran before 2027 | $400 | 200 | 3.5 |
| trump_out | Trump out as President before 2027 | $1 | 20 | 4.5 |

Reward params are **current Gamma fields held constant**; historical daily rates may have differed.

Event: `fed-decision-in-september-762`.

## Capital & split

- Start capital: **$10,000**
- Split: time-based **75% train / 25% holdout** on concatenated sparse timestamps
- Soft-reject threshold: holdout max DD **> 25%** of capital

## Baseline metrics (`strategy.py` defaults)

| Metric | Train | Holdout |
|--------|------:|--------:|
| **Net PnL** | **+$1,751.50** | **+$223.15** |
| End equity | $11,751.50 | $10,223.15 |
| Max DD ($ / % of capital) | $105 / 1.05% | $19.65 / 0.20% |
| Reward PnL | $1,467.96 | $34.87 |
| Trading PnL | $283.54 | $188.29 |
| Fees | $0 | $0 |
| Fills | 121 | 6 |
| Soft reject | — | **false** |

Primary metric for autoresearch: **`holdout_net_pnl = 223.1549`**.

Raw JSON: `results/baseline_metrics.json`.

## How to reproduce

```bash
source .venv/bin/activate
python prepare.py          # or --quick for 2 days only
python evaluate.py
python scripts/run_autoresearch.py -n 5
```

## Limitations (read this)

1. **Sparse days ≠ continuous replay.** Gaps between sample days (weeks) are not modeled as continuous inventory risk; timestamps are concatenated chronologically.
2. **No claim of full 90-day L2.** Archives end 2026-08-10; Jun 12–17 missing; we sampled 5 days only.
3. **Reward schedule is approximate** (current Gamma constants).
4. **Fills** use mid-path crossing of resting quotes (+ adverse bias when trade tape present; tape empty on this HF path).
5. **Competition** from observed L2 depth within max spread; simplified vs full multi-maker Q normalization.
6. Maker fees ≈ 0 bps by assumption.
