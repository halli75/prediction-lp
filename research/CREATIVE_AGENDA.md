# Creative Agenda — Wave 1 (structural, not knob decimals)

**Context:** Champion `wave5b_pull24_p46_sf672` (liveish sample 528.47 / 30d 496.98 / 60d 861.11).
Knob-tuning waves 6–11 plateaued. Root cause: **toxic inventory bleed** with only ~$200–400 of $10k typically deployed; more size/markets historically hurt under liveish.

**Thesis:** Idle capital is a symptom, not the free lunch. Toxicity on carried inventory destroys edge when we try to “deploy more.” Creative bets attack *structure* of inventory lifecycle and market selection — not `spread_frac` decimals.

Strategy is quote-only (no aggressive market orders). Flatten = quote reducing side tighter/larger.

## Bets

| # | Mode | Why | Idle capital vs toxicity |
|---|------|-----|--------------------------|
| 1 | **force_flatten** | Soft-cap alone is too late; pay to exit earlier when \|net\| ≥ soft×trigger | Toxicity: cut carry before adverse mid moves compound |
| 2 | **day_boundary_flatten** | Multi-day carry is the bleed; force near-flat at UTC day change | Toxicity: deny overnight adverse selection |
| 3 | **toxicity_blackout** | After inventory grows, mid move against us → stand down both sides | Toxicity: stronger than add-side pause |
| 4 | **dynamic_top_k** | Only quote top-K reward pools per UTC day (keep pool floor) | Idle: concentrate scarce quotes on fattest pools |
| 5 | **harvest_or_flatten** | \|net\|<2 harvest two-sided; else never add | Toxicity: minimize multi-day carry; harvest rewards when flat |
| 6 | **weekly_reset ablation** | Ops lever: independent $10k weekly books vs continuous | Idle/ops: does restart beat continuous path-dependence? |

## Gates (same `--liveish`)
Promote only if liveish **30d > 496.98** AND **60d > 861.11**, soft_reject false, max_dd_pct<25.
Sample preferred >528.47. Inventory soft ≤35 ≥20, hard ≤100 (flatten modes may tighten reduce-side earlier but never add past hard).

## Non-goals
- More `spread_frac` / `size_mult` micro-sweeps
- Aggressive (crossing) orders
- HF data downloads

## Artifacts
- Strategy: `research/creative/strategy_creative_base.py`
- Status: `results/swarm_creative_wave1_status.json`
- Findings: `results/creative_wave1_findings.md`
- Weekly ablation: `results/creative_weekly_reset_ablation.json` (+ `.md`)
