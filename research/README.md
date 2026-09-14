# Research swarm harness

Overnight Karpathy-style **axis swarm** over a **12-day** slim sample.

## Why a sample?

Full continuous window is slow and currently **net-negative** (trading losses >
rewards). Agents mutate `strategy.py` copies on a fast 12-day sample, then
promote winners with `eval_window.py` to 30/60 days.

## Layout

| Path | Role |
|------|------|
| `COMMANDER.md` | Root-cause brief + launch rules |
| `shared_findings.json` | Cross-agent memory (file-locked updates) |
| `sample_days.txt` | Exactly 12 evenly spaced slim days |
| `sample_manifest.json` | Capital, metric, soft-reject policy |
| `axes.json` | ≥14 named mutation axes |
| `baseline_sample_metrics.json` | Defensive baseline on sample |
| `leaderboard.json` | Best per agent + global best |
| `agents/<id>/` | Isolated strategy copy + experiments |

## Data

- Sample prices: `data/research_sample_prices.parquet` (built by `scripts/build_research_sample.py`)
- Markets: `data/markets.json`
- Slim days: `data/slim_days/*.parquet` (continuous prepare may still be running — **do not kill**)

## Primary metric

`sample_net_pnl` — **full run on the 12-day sample** (no holdout split).

Soft-reject: `max_dd_pct > 25` (% of $10k capital). Soft-rejects are **never kept**.

## Defensive baseline

`strategy.py` defaults already encode the known fix direction:
tight inventory, small size, wide spreads, cancel/pause on adverse mids, **top5** markets.

## Agent loop

```bash
python scripts/run_axis_autoresearch.py \
  --axis widen_spread --iters 40 --agent-id wide-01 --seed 7
```

Each iter: axis mutation → `eval_sample.py` → keep if `sample_net_pnl` improves
and not soft-reject, else revert. Logs `agents/<id>/experiments.jsonl`.
Hard-stops if best PnL still **< -200** after **15** iters.

## Promotion

```bash
python scripts/eval_window.py --days-file research/promo_30d.txt
python scripts/eval_window.py --days a,b,c
```
