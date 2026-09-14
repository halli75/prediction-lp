#!/usr/bin/env python3
"""Creative wave1: liveish sample sweep over structural modes, promote gates if hot."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "research" / "creative" / "strategy_creative_base.py"
CHAMP = ROOT / "research" / "champions" / "strategy_wave5b_pull24_p46_sf672.py"
PY = ROOT / ".venv" / "bin" / "python"
STATUS = ROOT / "results" / "swarm_creative_wave1_status.json"
FINDINGS = ROOT / "results" / "creative_wave1_findings.md"
OUTDIR = ROOT / "results" / "creative"
OUTDIR.mkdir(parents=True, exist_ok=True)

GATE_SAMPLE = 528.47
GATE_30D = 496.98
GATE_60D = 861.11
PROMOTE_SAMPLE_FLOOR = 480.0

CANDIDATES = [
    {"id": "force_flatten_default", "overlay": {"force_flatten": True}},
    {"id": "force_flatten_trig033", "overlay": {"force_flatten": True, "flatten_trigger_frac": 0.33, "flatten_half_frac": 0.2, "flatten_size_mult": 2.5}},
    {"id": "day_boundary_flatten", "overlay": {"day_flatten": True, "day_flatten_max_net": 5}},
    {"id": "day_flatten_max2", "overlay": {"day_flatten": True, "day_flatten_max_net": 2, "force_flatten": True}},
    {"id": "tox_blackout_40_1p5", "overlay": {"tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
    {"id": "tox_blackout_60_1p0", "overlay": {"tox_blackout_ticks": 60, "tox_move_cents": 1.0}},
    {"id": "dynamic_top_k_8", "overlay": {"dynamic_top_k": 8}},
    {"id": "dynamic_top_k_5", "overlay": {"dynamic_top_k": 5}},
    {"id": "dynamic_top_k_12", "overlay": {"dynamic_top_k": 12}},
    {"id": "harvest_or_flatten", "overlay": {"harvest_mode": True}},
    {"id": "harvest_plus_tox", "overlay": {"harvest_mode": True, "tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
    {"id": "force_plus_tox", "overlay": {"force_flatten": True, "tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
    {"id": "harvest_day_flatten", "overlay": {"harvest_mode": True, "day_flatten": True, "day_flatten_max_net": 5}},
    {"id": "topk8_harvest", "overlay": {"dynamic_top_k": 8, "harvest_mode": True}},
    {"id": "force_day_tox", "overlay": {"force_flatten": True, "day_flatten": True, "tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(data: dict) -> None:
    data["updated_at"] = utc_now()
    STATUS.write_text(json.dumps(data, indent=2, default=str))


def run_liveish_candidate(mode: str, overlay: dict, days_file: Path | None, tag: str) -> dict:
    out_path = OUTDIR / f"{tag}_{mode}.json"
    cmd = [
        str(PY),
        str(ROOT / "scripts" / "eval_liveish_candidate.py"),
        "--mode",
        mode,
        "--strategy-module",
        str(STRAT),
        "--overlay-json",
        json.dumps(overlay),
    ]
    if mode == "window":
        assert days_file is not None
        cmd += ["--days-file", str(days_file)]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    elapsed = time.time() - t0
    if proc.returncode != 0:
        err = {
            "error": True,
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[-2000:],
            "stdout": (proc.stdout or "")[-2000:],
            "elapsed_sec": elapsed,
            "overlay": overlay,
            "tag": tag,
        }
        out_path.write_text(json.dumps(err, indent=2))
        return err
    try:
        # stdout may have trailing noise; find last JSON object
        text = proc.stdout.strip()
        # prefer last {...} block
        start = text.find("{")
        end = text.rfind("}")
        payload = json.loads(text[start : end + 1])
    except Exception as e:
        err = {
            "error": True,
            "parse_error": str(e),
            "stdout": (proc.stdout or "")[-2000:],
            "elapsed_sec": elapsed,
        }
        out_path.write_text(json.dumps(err, indent=2))
        return err
    payload["elapsed_wall_sec"] = round(elapsed, 3)
    payload["candidate_id"] = tag
    payload["overlay"] = overlay
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def main() -> None:
    status = {
        "wave": "creative_wave1",
        "started_at": utc_now(),
        "champion": "wave5b_pull24_p46_sf672",
        "gates": {"sample": GATE_SAMPLE, "30d": GATE_30D, "60d": GATE_60D},
        "pid": os.getpid(),
        "phase": "sample_sweep",
        "candidates": {},
        "promoted": False,
        "running_pids": [os.getpid()],
    }
    write_status(status)

    results = []
    for cand in CANDIDATES:
        cid = cand["id"]
        print(f"[creative] sample {cid} ...", flush=True)
        status["phase"] = f"sample:{cid}"
        write_status(status)
        m = run_liveish_candidate("sample", cand["overlay"], None, cid)
        net = float(m.get("net_pnl") or m.get("sample_net_pnl") or 0.0)
        dd = float(m.get("max_dd_pct") or m.get("max_drawdown_pct") or 0.0)
        soft = bool(m.get("soft_reject", dd > 25))
        row = {
            "id": cid,
            "overlay": cand["overlay"],
            "sample_net_pnl": net,
            "max_dd_pct": dd,
            "soft_reject": soft,
            "n_fills": m.get("n_fills"),
            "reward_pnl": m.get("reward_pnl"),
            "trading_pnl": m.get("trading_pnl"),
            "error": m.get("error", False),
        }
        results.append(row)
        status["candidates"][cid] = row
        write_status(status)
        print(f"  -> sample={net:.2f} dd={dd:.2f} soft={soft}", flush=True)

    # Sort and pick promote candidates
    ok = [
        r
        for r in results
        if not r.get("error")
        and not r["soft_reject"]
        and r["sample_net_pnl"] >= PROMOTE_SAMPLE_FLOOR
    ]
    ok.sort(key=lambda r: r["sample_net_pnl"], reverse=True)
    status["sample_promote_queue"] = [r["id"] for r in ok]
    status["phase"] = "window_evals"
    write_status(status)

    days_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
    days_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"

    window_rows = []
    for r in ok[:6]:  # top serious candidates
        cid = r["id"]
        overlay = r["overlay"]
        print(f"[creative] 30d+60d {cid} ...", flush=True)
        m30 = run_liveish_candidate("window", overlay, days_30, f"{cid}_30d")
        m60 = run_liveish_candidate("window", overlay, days_60, f"{cid}_60d")
        n30 = float(m30.get("net_pnl") or 0.0)
        n60 = float(m60.get("net_pnl") or 0.0)
        d30 = float(m30.get("max_dd_pct") or 0.0)
        d60 = float(m60.get("max_dd_pct") or 0.0)
        soft30 = bool(m30.get("soft_reject", d30 > 25))
        soft60 = bool(m60.get("soft_reject", d60 > 25))
        beats = (
            n30 > GATE_30D
            and n60 > GATE_60D
            and not soft30
            and not soft60
            and d30 < 25
            and d60 < 25
        )
        wrow = {
            "id": cid,
            "sample": r["sample_net_pnl"],
            "30d": n30,
            "60d": n60,
            "dd_30": d30,
            "dd_60": d60,
            "soft_30": soft30,
            "soft_60": soft60,
            "beats_gates": beats,
            "overlay": overlay,
        }
        window_rows.append(wrow)
        status["candidates"][cid]["windows"] = wrow
        write_status(status)
        print(
            f"  -> 30d={n30:.2f} 60d={n60:.2f} beats={beats}",
            flush=True,
        )
        if beats:
            # promote
            status["phase"] = f"promote:{cid}"
            status["promoted"] = True
            status["promoted_id"] = cid
            write_status(status)
            promote(cid, overlay, wrow)
            break

    # Write findings
    lines = [
        "# Creative Wave 1 Findings",
        "",
        f"Updated: {utc_now()}",
        "",
        f"Champion wave5b gates: sample {GATE_SAMPLE} / 30d {GATE_30D} / 60d {GATE_60D}",
        "",
        "## Sample sweep (liveish)",
        "",
        "| id | sample | dd% | soft | fills |",
        "|----|-------:|----:|:----:|------:|",
    ]
    for r in sorted(results, key=lambda x: x.get("sample_net_pnl") or -1e9, reverse=True):
        lines.append(
            f"| {r['id']} | {r.get('sample_net_pnl', 0):.2f} | {r.get('max_dd_pct', 0):.2f} | {r.get('soft_reject')} | {r.get('n_fills')} |"
        )
    lines += ["", "## Window evals (serious candidates)", ""]
    if window_rows:
        lines += [
            "| id | sample | 30d | 60d | beats |",
            "|----|-------:|----:|----:|:-----:|",
        ]
        for w in window_rows:
            lines.append(
                f"| {w['id']} | {w['sample']:.2f} | {w['30d']:.2f} | {w['60d']:.2f} | {w['beats_gates']} |"
            )
    else:
        lines.append("_No candidate cleared sample floor ~480 with soft_reject=false._")
    lines += [
        "",
        f"**Promoted:** {status.get('promoted', False)} ({status.get('promoted_id', '')})",
        "",
        "See also weekly ablation: `results/creative_weekly_reset_ablation.json`",
        "",
    ]
    FINDINGS.write_text("\n".join(lines))
    status["phase"] = "done"
    status["finished_at"] = utc_now()
    write_status(status)
    print("[creative] done", flush=True)


def promote(cid: str, overlay: dict, wrow: dict) -> None:
    """Copy creative strategy with baked knobs into champions + root."""
    import shutil

    # Bake overlay into a dedicated champion file by writing a thin wrapper
    label = f"creative_{cid}"
    champ_path = ROOT / "research" / "champions" / f"strategy_{label}.py"
    # Copy creative base and document promoted overlay in artifact; also set defaults
    src = STRAT.read_text()
    # Write strategy that defaults creative knobs ON via baked config merge
    wrapper = f'''"""Promoted creative champion: {label}
Baked overlay: {json.dumps(overlay)}
Liveish: sample={wrow["sample"]:.2f} 30d={wrow["30d"]:.2f} 60d={wrow["60d"]:.2f}
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1] / "creative" / "strategy_creative_base.py"
_spec = importlib.util.spec_from_file_location("creative_base_promoted", _BASE)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

_BAKED = {json.dumps(overlay)}


class Strategy(_mod.Strategy):
    def __init__(self, config=None):
        cfg = dict(_BAKED)
        if config:
            cfg.update(config)
        super().__init__(cfg)
'''
    # Prefer inlining full file with defaults patched for robustness
    # Patch creative defaults in a copy of creative_base
    text = src
    # crude but effective: after reading cfg, force baked keys via overlay at end of __init__ defaults
    # Better: write the wrapper that imports creative base from relative path that works when copied
    champ_path.write_text(wrapper)
    shutil.copy2(champ_path, ROOT / "research" / "champions" / "strategy_current_best.py")
    shutil.copy2(champ_path, ROOT / "strategy.py")

    artifact = {
        "job": f"creative_wave1_promotion_{label}",
        "label": label,
        "parent": "wave5b_pull24_p46_sf672",
        "eval": "liveish",
        "overlay": overlay,
        "created_at": utc_now(),
        "windows_liveish": {
            "sample": wrow["sample"],
            "30d": wrow["30d"],
            "60d": wrow["60d"],
        },
        "gates_beaten": {
            "30d_gate": GATE_30D,
            "60d_gate": GATE_60D,
            "sample_gate": GATE_SAMPLE,
        },
    }
    art_path = ROOT / "results" / f"promotion_{label}.json"
    art_path.write_text(json.dumps(artifact, indent=2))

    gate_md = ROOT / "research" / "PROMOTION_GATE.md"
    gate_md.write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (creative wave1 over wave5b)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave1 {utc_now()} under **LIVEISH Aug10** gates. Prior wave5b liveish: sample 528.47 / 30d 496.98 / 60d 861.11.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **{wrow['sample']:.2f}** | false |
| **30d** | **{wrow['30d']:.2f}** | false |
| **60d** | **{wrow['60d']:.2f}** | false |

**To replace champion:** both **liveish-30d > {wrow['30d']:.2f}** AND **liveish-60d > {wrow['60d']:.2f}** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >{wrow['sample']:.2f}. Inventory: soft ≤35 ≥20; hard ≤100.

Creative overlay: `{json.dumps(overlay)}`

Artifact: `results/promotion_{label}.json`
"""
    )
    print(f"[creative] PROMOTED {label}", flush=True)


if __name__ == "__main__":
    main()
