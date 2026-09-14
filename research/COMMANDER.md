# COMMANDER — Overnight Plan

## Root cause (established — do not rediscover)

Continuous multi-day backtests **lose money because trading/inventory losses exceed LP rewards**.

Mechanism:
- Adverse selection on fills (mid moves through resting quotes).
- Multi-day **inventory bleed**: net YES/NO positions accumulate and mark against us.
- Sparse-day profits were **misleading** (inventory not stressed across day boundaries).
- Quoting **more markets** increased loss surface: more inventory slots, more adverse fills, rewards did not keep up.

### A/B evidence (known)

| Universe | Net PnL | Reward | Trading |
|----------|---------|--------|---------|
| Seed-ish set | ~**-$454** | +2338 | **-2792** |
| All markets | ~**-$2226** | +1888 | **-4114** |

Interpretation: rewards are real but **trading losses dominate**; expanding the book worsens the gap.

Related files: `results/ablation_seed_vs_all.json`, `results/continuous_baseline_metrics.json`.

## Fix principles (defensive v2 baseline in `strategy.py`)

1. **Cap inventory hard** — soft/hard caps ~35 / ~100 (vs v1 ~349 / ~800).
2. **Shrink size** — `size_mult ≈ 1.05` (near `rewards_min_size`).
3. **Widen spreads** — high `spread_frac` (~0.82) so fills are rarer; stay inside reward band.
4. **Stronger skew** — unload inventory, do not accumulate.
5. **Mid-move cancel/widen** — if mid jumps ≥2¢ widen; ≥4¢ cancel both sides (strategy-internal state).
6. **Add-side pause** — after inventory grows, pause the adding side for several ticks.
7. **Pool allowlist** — default `enforce_pool_allowlist=True`, `min_daily_reward_pool=400` (high-pool only); low-pool haircut if disabled.
8. **Skip extreme tails** — do not force two-sided near 0/1 unless flattening inventory.
9. **Cash guard** — stand down if cash < 12% of capital0.

Prefer **strategy-only** fixes. Engine state keys already include `daily_reward_pool`, inventory, cash, mids, reward band params.

## Overnight goals

1. Keep **defensive v2** as the swarm baseline (`strategy.py`).
2. Fast loop on **12-day research sample** (`research/sample_days.txt` → `data/research_sample_prices.parquet`).
3. Swarm agents mutate **one lever / axis at a time** (`research/axes.json`); read `research/shared_findings.json` first.
4. Primary metric on sample: **`sample_net_pnl`** (full sample, no holdout split). Soft-reject if max DD > 25% of capital.
5. Secondary: `|trading_pnl| < reward_pnl`; inventory max |net| controlled.
6. Prefer **fewer, higher-pool markets** over broader quoting.
7. Do **not** kill `prepare.py --continuous`; do not download more HF data during search.
8. Promote sample winners to 30d/60d via `scripts/eval_window.py`.
9. Commander (not workers) owns spawning the agent swarm.
10. Hard-stop an axis if best `sample_net_pnl` stays **< -200** after **15** iters.

## Launch one axis (commander)

```bash
cd /workspace/polymarket-lp-autoresearch && source .venv/bin/activate
python scripts/build_research_sample.py   # once (already done)
python scripts/eval_sample.py             # defensive baseline (~+$380 on sample)
python scripts/run_axis_autoresearch.py \
  --axis inventory_hard_cap --iters 40 --agent-id invcap-01 --seed 1
```

Hard-stop: best `sample_net_pnl` < -200 after 15 iters. Never keep soft_reject.
Shared memory: `research/shared_findings.json` + `research/leaderboard.json`.

## Success criteria

- Sample net PnL **≥ 0** (stretch); at least beat commander A/B seed (~-$454) with lower inventory drag.
- Trading PnL magnitude **below** reward income on continuous/sample windows.
- No cash≈0 death spirals; soft-reject strategies discarded.
