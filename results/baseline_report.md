# Baseline report — Polymarket LP autoresearch (phase 2)

Generated from a real `evaluate.py` run on the prepared sparse-day L2 cache
after expanding the market universe and sample days. **Not comparable 1:1**
to the phase-1 $244 holdout (different days, tokens, fill model, and a 1 bp fee).

This is **sparse-day sampling**, not continuous L2, and **not live-trading ready**.

## Data

| Field | Value |
|-------|--------|
| Mode | `sparse_day_l2` (NOT continuous L2) |
| Source | HuggingFace `Joseph3222/polymarket-orderbook` / `orderbook_1min` |
| Sparse days | **2026-02-22, 2026-03-08, 2026-03-29, 2026-04-05, 2026-04-12, 2026-05-14, 2026-06-01, 2026-06-18, 2026-06-25, 2026-07-20, 2026-08-10** |
| Calendar span | 2026-02-22 → 2026-08-10 00:41 UTC (11 sampled days; Jun 12–17 missing) |
| Price rows | 266,936 (1-min YES mids + BBO + L2-derived competition) |
| Markets | **22** YES tokens (all requested tokens had ≥1 row) |
| Cache size | slim days ≈ 36 MB; raw HF day files + hub cache deleted after each filter |
| Train / holdout rows | 234,616 / 32,320 (time split 75/25 on concatenated timestamps) |

`2026-08-10` is a short archive-end file (~892 minutes) — included for coverage, not as a full day.

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
| eizenkot_pm | Gadi Eizenkot next PM of Israel | $298 | 100 | 5.5 |
| flavio_br | Flávio Bolsonaro wins Brazil 2026 | $253 | 100 | 5.5 |
| lula_br | Lula wins Brazil 2026 | $247 | 100 | 5.5 |
| lepen_fr | Marine Le Pen wins France 2027 | $242 | 100 | 5.5 |
| antonelli_f1 | Kimi Antonelli 2026 F1 champion | $200 | 100 | 4.5 |
| philippe_fr | Édouard Philippe wins France 2027 | $186 | 100 | 5.5 |
| netanyahu_pm | Netanyahu next PM of Israel | $172 | 100 | 5.5 |
| kane_ballon | Harry Kane 2026 Ballon d'Or | $131 | 50 | 4.5 |
| no_fed_cuts | No Fed rate cuts in 2026 | $116 | 50 | 4.5 |
| aliens | US confirms aliens exist before 2027 | $100 | 200 | 3.5 |
| vance_gop | J.D. Vance 2028 GOP nominee | $79 | 20 | 4.5 |
| putin_out | Putin out as President by 2026-12-31 | $70 | 200 | 3.5 |
| iran_regime | Iranian regime falls before 2027 | $70 | 200 | 3.5 |
| one_fed_cut | 1 Fed rate cut in 2026 | $66 | 50 | 4.5 |
| china_taiwan | China invades Taiwan by end of 2026 | $50 | 200 | 3.5 |

Reward params are **current Gamma fields held constant**; historical daily rates may have differed.

## Capital & split

- Start capital: **$10,000**
- Split: time-based **75% train / 25% holdout** on concatenated sparse timestamps
  (cut falls after 2026-06-25; holdout is mostly 2026-07-20 + the short 2026-08-10 stub)
- Soft-reject threshold: holdout max DD **> 25%** of capital

## Baseline metrics (`strategy.py` defaults after phase-1 keep)

| Metric | Train | Holdout |
|--------|------:|--------:|
| **Net PnL** | **+$1,429.66** | **+$424.34** |
| End equity | $11,429.66 | $10,424.34 |
| Max DD ($ / % of capital) | $591.47 / 5.91% | $13.28 / 0.13% |
| Reward PnL | $2,639.38 | $52.19 |
| Trading PnL | −$1,206.67 | $372.29 |
| Fees (1 bp maker) | $3.05 | $0.14 |
| Fills | 383 | 31 |
| Soft reject | — | **false** |

Primary metric for autoresearch: **`holdout_net_pnl = 424.3449`**.

Train trading PnL is negative while reward income is large — expected once mid-path fills are penetration-scaled and adversely boosted. Holdout still prints on a quieter late-sample window; **do not read this as live LP expectancy**.

Raw JSON: `results/baseline_metrics.json`. Phase-2 writeup: `results/phase2_report.md`.

## How to reproduce

```bash
source .venv/bin/activate
python prepare.py          # or --quick for 2 days only
python evaluate.py
python scripts/run_autoresearch.py -n 30
```

## Limitations (read this)

1. **Sparse days ≠ continuous replay.** Gaps between sample days (weeks) are not modeled as continuous inventory risk; timestamps are concatenated chronologically.
2. **No claim of full Feb–Aug L2.** Archives start 2026-02-22 and end 2026-08-10; Jun 12–17 missing; we sampled 11 days only. `2026-08-10` is a stub (~41 minutes).
3. **Reward schedule is approximate** (current Gamma constants).
4. **Fills** use mid-path crossing of resting quotes, size-scaled by how far mid went through the quote, plus a 5-minute look-ahead adverse boost. Trade tape is empty on this HF path.
5. **Competition** from observed L2 depth within max spread, with a tightness bump when BBO is 1–2¢.
6. Maker fee = **1 bp** of notional (friction stand-in, not a venue schedule). Rebate = 0.
7. **Not live-trading ready.**
