# Phase 2 report — market/day expansion + more autoresearch

**Status:** harness expanded; full sparse-day cache + 30-iter search numbers are filled in after `prepare.py` / `evaluate.py` / `run_autoresearch.py` complete on this branch.

This is still **sparse-day sampling**, not continuous L2, and **not live-trading ready**.

## What changed vs phase 1

| Item | Phase 1 | Phase 2 |
|------|---------|---------|
| Sparse days | 5 (May 14 → Aug 6) | 11 (Feb 22 → Aug 10) |
| Outcome tokens | 7 | 22 curated (Gamma high-`rewardsDailyRate` + depth) |
| Calendar span | ~3 months | ~6 months (archive window) |
| Autoresearch | 3 iters, 1 keep (~$244 holdout) | target 30 iters, keep/discard on `holdout_net_pnl` |
| Sim | mid-cross 100% fill, 0 fee | penetration fills + look-ahead adverse boost + 1 bp maker fee |
| Disk | delete raw day files | also delete HF hub cache; ~10GB download+cache budget |

Days: `2026-02-22, 2026-03-08, 2026-03-29, 2026-04-05, 2026-04-12, 2026-05-14, 2026-06-01, 2026-06-18, 2026-06-25, 2026-07-20, 2026-08-10`.

Skipped Jun 12–17 (missing in archive). Replaced the 2.5GB `2026-08-06` file with archive-end `2026-08-10` so more earlier days fit under 10GB.

## Markets (requested universe)

Phase-1 seed: Fed Sep 2026 (5 outcomes), US invade Iran before 2027, Trump out before 2027.

Phase-2 additions (Gamma, high daily reward + volume/liquidity, listed before the archive end): Israel PM (Eizenkot, Netanyahu), Brazil 2026 (Flávio, Lula), France 2027 (Le Pen, Philippe), Antonelli F1, Kane Ballon d'Or, Fed-cuts-in-2026 (0 and 1 cut), US confirm aliens, Vance GOP 2028, Putin out, Iranian regime fall, China/Taiwan.

Tokens with **zero** rows in the sampled days are dropped from `data/markets.json` (no free reward ticks).

## Results (to be filled)

| Metric | Phase-1 best | Phase-2 new baseline | Phase-2 best keep |
|--------|-------------:|---------------------:|------------------:|
| holdout_net_pnl | $243.94 | TBD | TBD |
| holdout max DD % of capital | 0.77% | TBD | TBD |
| soft_reject | false | TBD | TBD |
| n_markets / n_days / n_price_rows | 7 / 5 / 46,783 | TBD | — |
| kept / discarded iters | 1 / 2 | — | TBD |

See `results/baseline_metrics.json` and `results/experiments.jsonl` after the run.

## Honest limitations

- Concatenated sparse minutes ≠ a continuous book. Inventory is **not** marked over the weeks between sample days.
- Current Gamma reward params are held constant; 2026-02 rates may have differed.
- 1 bp maker fee is a friction stand-in, not a venue fee schedule.
- Adverse selection is a 5-minute mid look-ahead size boost, not a flow-toxicity model.
- Do not treat holdout PnL as expected live LP income.
