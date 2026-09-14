# Creative day_boundary_flatten — liveish / live-parity audit

**Date:** 2026-09-13  
**Champion:** `creative_day_boundary_flatten` (`day_flatten=true`, `day_flatten_max_net=5` on wave5b parent)  
**Verdict:** **PASS** — promoted sample/30d/60d used identical liveish engine + strategy defense flags via `scripts/eval_liveish_candidate.py`. No re-run required for flag mismatch.

## Canonical liveish knobs

### Engine (`sim/engine.py` `LIVEISH_CONFIG`)

| Knob | Value |
|------|------:|
| `quote_latency_rows` | 1 |
| `max_fill_frac` | 0.40 |
| `adverse_mid_cross_strength` | 6.0 |
| `fill_persist_rows` | 1 |
| `portfolio_inv_cap` | 400.0 |
| `adverse_lookback_min` | 5 |
| `use_trades` | False |

Applied by `liveish_engine_config({"capital0": 10000})` in both `eval_liveish.py` and `eval_liveish_candidate.py`.

### Strategy defenses (`scripts/eval_liveish.py` `LIVEISH_STRATEGY_CFG`)

| Knob | Value |
|------|------:|
| `near_mid_size_mult` | 0.5 |
| `near_mid_dist` | 0.02 |
| `portfolio_inv_cap` | 400.0 |
| `cancel_move` | 0.02 |

Merged as `{**LIVEISH_STRATEGY_CFG, **overlay}` in `eval_liveish_candidate.py`.

### Creative overlay (champion)

| Knob | Value |
|------|------:|
| `day_flatten` | true |
| `day_flatten_max_net` | 5 |

## Artifact comparison

| Artifact | Path used | `liveish` | Overlay recorded | Engine cfg in JSON |
|----------|-----------|:---------:|------------------|:------------------:|
| sample | `results/creative/day_boundary_flatten_sample.json` | true | day_flatten + max_net=5 | not serialized (implicit via candidate script) |
| 30d | `results/creative/day_boundary_flatten_30d_window.json` | true | same | same |
| 60d | `results/creative/day_boundary_flatten_60d_window.json` | true | same | same |
| promotion | `results/promotion_creative_day_boundary_flatten.json` | `"eval":"liveish"` | same | n/a |
| docs | `research/LIVE_REALISM.md` | matches LIVEISH_CONFIG + LIVEISH_STRATEGY_CFG | — | — |

**30d / 60d / sample identical flags?** YES — all three came from creative wave1 → `eval_liveish_candidate.py` with the same LIVEISH merge + the same overlay. Gate windows: `window_30d_liveish_gate_days.txt` / `window_60d_liveish_gate_days.txt` (Aug10-ended).

**Wrong/missing liveish flags on promote?** NO. Do not re-run for parity; numbers 651.39 / 1431.56 / 1979.75 are trusted under liveish.

Note: result JSONs omit explicit `engine_cfg` / `strategy_cfg` dumps (only `liveish: true` + overlay). Code path guarantees the knobs above; independent verify (section D) re-runs under the same path.

## Gaps vs true live (honest)

Liveish is stricter than optimistic sim but still **not** full live parity. Remaining gaps:

| Gap | Liveish status | True live |
|-----|----------------|-----------|
| Trade tape / aggressive flow | `use_trades=False` (intentional apples-to-apples) | Live sees aggressive flow; fill timing differs |
| Partial fills | Coarse `max_fill_frac=0.40` constant | Queue position, size ahead, random partials |
| Latency / cancel realism | Fixed `quote_latency_rows=1`; cancels apply after 1 row | Variable RTT, partial cancel acks, stale multi-level book |
| Fill persistence | `fill_persist_rows=1` | Mid can flicker; matching engine timing differs |
| Adverse selection | Heuristic `adverse_mid_cross_strength=6` + lookback | Informed flow / toxicity regimes not in mid path alone |
| Order rejects / rate limits | None | Exchange rejects, nonce gaps, replace storms |
| Fees / gas / reward accrual lag | Rewards on resting quote with latency; no gas | Reward display lag + gas/ops costs |
| Capital / margin | Soft `portfolio_inv_cap=400` | Hard wallet/collateral constraints, multi-bot interaction |
| Day-boundary flatten itself | Quote-only reduce (tighter/larger) | Live flatten may need more aggressive exit / worse fills |

**Bottom line:** Liveish is the correct promotion yardstick *within this repo*; treat absolute PnL as optimistic vs a real deployed bot by the gaps above.
