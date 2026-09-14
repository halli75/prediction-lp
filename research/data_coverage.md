# Data coverage inventory

Updated: 2026-09-13 (executor: expand-backtest prep; **no HF mega-download**)

## Local slim_days (authoritative)

| Item | Value |
|------|--------|
| Path | `data/slim_days/*.parquet` |
| **n_days cached** | **63** |
| Date range | **2026-05-14 → 2026-07-21** |
| Calendar span | 69 days (inclusive) |
| Archive gap (missing in HF) | **2026-06-12 … 2026-06-17** (6 days) — not on disk, not downloadable |
| Slim size | ~329 MB total (~5.5 MB/day avg) |
| Markets / allowlist | 65 markets via `data/top_reward_markets.json` / `data/markets.json` |
| Source config | HF `Joseph3222/polymarket-orderbook` / `orderbook_1min` |
| Manifest | `data/manifest.json` — mode `continuous_l2_partial`, **63/83** target days |
| Stop reason | `commander_override_stop_mega_prepare` after 2026-07-21 |

### Gaps inside May14→Jul21

Only the known HF archive hole:

- 2026-06-12, 2026-06-13, 2026-06-14, 2026-06-15, 2026-06-16, 2026-06-17

All other calendar days in range are present as slim parquet.

### Continuous segments (calendar)

| Segment | Days present | Notes |
|---------|-------------:|-------|
| 2026-05-14 → 2026-06-11 | 29 | continuous |
| 2026-06-12 → 2026-06-17 | 0 | archive gap |
| 2026-06-18 → 2026-07-21 | 34 | continuous |
| **All available (skip gap)** | **63** | furthest honest local window |

Promotion windows already in use skip the gap the same way (`window_30d` = 30 days, `window_60d` = 54 of 60 calendar days ending Jul21).

## Search for days after 2026-07-21 (local only)

Searched without downloading:

| Location | Result |
|----------|--------|
| `data/slim_days/` | none after 2026-07-21 |
| `data/raw_hf/` | empty except empty HF cache markers (raw deleted after filter) |
| `data/*.parquet` | assembled May14→Jul21 only |
| `/workspace` other trees | no Jul22–Aug10 slim/raw day caches |
| `~/.cache/huggingface` | none for post-Jul21 days |
| Cloud-agent transcript claim | sparse/continuous work mentioned Aug10 as **archive end**; local continuous prepare **stopped** at Jul21 |

**Conclusion:** No incremental Jul22→Aug10 days exist locally. Cloud “through Aug 10” refers to archive endpoint / another branch’s sparse samples (e.g. single day 2026-08-06 / 08-10), **not** a local continuous slim cache here. **Do not download** until a champion improvement justifies resume.

## Pending remote days (metadata only; not downloaded)

Target remaining for full May14→Aug10 continuous (skip Jun12–17): **20 days**

`2026-07-22` … `2026-08-10`

| Estimate | Value |
|----------|--------|
| Raw HF total (API sizes) | **~39.5 GB** |
| Peak disk if day-at-a-time + delete raw | **~2.5 GB** transient (largest day ~2.53 GB) + slim growth |
| Extra slim after filter | **~110 MB** (~5.5 MB × 20) |
| Wall time prepare (from May–Jul logs ~20–30s/day download + filter) | **~15–25 min** for 20 days |
| Full-window eval vs current 60d (~54d / ~66s) | ~63d ≈ **75–90s**; full 83d ≈ **~2 min** |

Resume command (only when authorized):

```bash
python prepare.py --continuous --resume --max-days 5   # incremental batches
```

## Day lists for promotion

| File | n_days | Range | Role |
|------|-------:|-------|------|
| `research/sample_days.txt` | 12 | sparse sample | fast hunt |
| `research/window_30d_days.txt` | 30 | 2026-07-12 → 2026-08-10 | gate |
| `research/window_60d_days.txt` | 54 | 2026-06-18 → 2026-08-10 | gate |
| **`research/window_90d_days.txt`** | **83** | **2026-05-14 → 2026-08-10** | **full available continuous** |
| `research/window_full_available_days.txt` | 83 | same | alias + comment header |

When (and only when) algo improves past pool150 on 30d+60d gates, promote evals should also run on `window_90d_days.txt` / full-available via `scripts/eval_full_available.py`.

## Disk

~113G free on box. Extending is feasible **incrementally**, but commander order stands: no mega HF download unless needed after a real improvement.

## Full-available baselines

Evaluated on `research/window_90d_days.txt` (83 days, May14→Aug10, skip Jun12–17). Expand complete.

| Label | strategy | net_pnl | reward | trading | fills | max_dd% | artifact |
|-------|----------|--------:|-------:|--------:|------:|--------:|----------|
| pool150 | `research/champions/strategy_pool150.py` | 1592.0468 | 1720.7728 | -128.726 | 995 | 2.9435 | `results/eval_full_available_pool150.json` |
| **pool100 (current champ)** | `strategy.py` | **2304.9872** | 1936.0165 | 368.9707 | 1464 | 2.9548 | `results/eval_full_available_pool100.json` |

Gate to beat (PROMOTION_GATE): 30d **2734.01** / 60d **2604.43**. Extend Jul22→Aug10 only after further improvement (~39.5 GB raw / ~2.5 GB peak day-at-a-time).


## Expand progress (final) — 2026-09-13T07:03:53Z

**Slim cache complete: 83/83 days** (2026-05-14 → 2026-08-10, skip Jun12–17).
Prepare final `prices.parquet` assemble OOM-killed twice under concurrent load; **slim_days are complete** and window evals read slim directly (no need for global prices.parquet).

Day lists via `scripts/rebuild_window_days.py`:

| File | n_days | Range | Role |
|------|-------:|-------|------|
| `research/window_30d_days.txt` | 30 | 2026-07-12 → 2026-08-10 | gate |
| `research/window_60d_days.txt` | 54 | 2026-06-18 → 2026-08-10 | gate |
| `research/window_90d_days.txt` | **83** | **2026-05-14 → 2026-08-10** | full available |
| `research/window_full_available_days.txt` | 83 | same | alias + comment header |

Note: Aug10 archive file is tiny (~0.12GB / 2547 slim rows) — partial day, still included.

### pool100 on expanded windows

Strategy: `research/champions/strategy_pool100.py`
Artifacts: `results/pool100_expand_summary.json`, `results/pool100_expand_evals/`, `results/eval_full_available_pool100.json`

| Window | n_days | net_pnl | reward | trading | max_dd% | fills | soft_reject |
|--------|-------:|--------:|-------:|--------:|--------:|------:|:-----------:|
| 30d | 30 | **3192.42** | 1451.76 | 1740.66 | 1.21 | 307 | False |
| 60d | 54 | **3634.59** | 2456.80 | 1177.79 | 1.59 | 485 | False |
| 90d/full | 83 | **3171.57** | 2607.02 | 564.55 | 2.95 | 1605 | False |

Prior (pre-expand, ended Jul21): 30d 2734.01 / 60d 2604.43 / full63 2304.99.
