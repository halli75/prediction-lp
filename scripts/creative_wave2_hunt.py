#!/usr/bin/env python3
"""Creative wave2: hunt day_flatten_max_net + flatten aggressiveness + tox/pool combos.

Parent champion: creative_day_boundary_flatten (day_flatten=True, day_flatten_max_net=5).
Promote only if liveish 30d > 1431.56 AND 60d > 1979.75 (same --liveish).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Champion strategy already defaults day_flatten=True / max_net=5; creative_base still
# defaults day_flatten=False so we always pass explicit overlay.
STRAT = ROOT / "research" / "champions" / "strategy_creative_day_boundary_flatten.py"
PY = ROOT / ".venv" / "bin" / "python"
STATUS = ROOT / "results" / "swarm_creative_wave2_status.json"
FINDINGS = ROOT / "results" / "creative_wave2_findings.md"
OUTDIR = ROOT / "results" / "creative"
OUTDIR.mkdir(parents=True, exist_ok=True)

GATE_SAMPLE = 651.39
GATE_30D = 1431.56
GATE_60D = 1979.75
PROMOTE_SAMPLE_FLOOR = 600.0  # soft preference; hard gates are 30d+60d

BASE = {"day_flatten": True, "day_flatten_max_net": 5}

CANDIDATES = [
    # A) day_flatten_max_net sweep
    {"id": "df_max2", "overlay": {**BASE, "day_flatten_max_net": 2}},
    {"id": "df_max3", "overlay": {**BASE, "day_flatten_max_net": 3}},
    {"id": "df_max5_ctrl", "overlay": {**BASE, "day_flatten_max_net": 5}},
    {"id": "df_max8", "overlay": {**BASE, "day_flatten_max_net": 8}},
    {"id": "df_max10", "overlay": {**BASE, "day_flatten_max_net": 10}},
    # B) flatten aggressiveness (with day_flatten)
    {"id": "df_agg_trig033", "overlay": {**BASE, "force_flatten": True, "flatten_trigger_frac": 0.33, "flatten_half_frac": 0.2, "flatten_size_mult": 2.5}},
    {"id": "df_agg_trig05", "overlay": {**BASE, "force_flatten": True, "flatten_trigger_frac": 0.5, "flatten_half_frac": 0.3, "flatten_size_mult": 1.75}},
    {"id": "df_agg_size3", "overlay": {**BASE, "force_flatten": True, "flatten_size_mult": 3.0, "flatten_half_frac": 0.2}},
    {"id": "df_agg_mild", "overlay": {**BASE, "force_flatten": True, "flatten_trigger_frac": 0.45, "flatten_half_frac": 0.28, "flatten_size_mult": 2.0}},
    {"id": "df_half015_sz25", "overlay": {**BASE, "flatten_half_frac": 0.15, "flatten_size_mult": 2.5}},
    # C) day_flatten + mild tox blackout
    {"id": "df_tox_40_1p5", "overlay": {**BASE, "tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
    {"id": "df_tox_30_1p0", "overlay": {**BASE, "tox_blackout_ticks": 30, "tox_move_cents": 1.0}},
    {"id": "df_tox_60_2p0", "overlay": {**BASE, "tox_blackout_ticks": 60, "tox_move_cents": 2.0}},
    {"id": "df_tox_20_1p5", "overlay": {**BASE, "tox_blackout_ticks": 20, "tox_move_cents": 1.5}},
    # D) day_flatten + pool ridge (min_daily_reward_pool around 100)
    {"id": "df_pool102", "overlay": {**BASE, "min_daily_reward_pool": 102.0}},
    {"id": "df_pool110", "overlay": {**BASE, "min_daily_reward_pool": 110.0}},
    {"id": "df_pool120", "overlay": {**BASE, "min_daily_reward_pool": 120.0}},
    {"id": "df_pool95", "overlay": {**BASE, "min_daily_reward_pool": 95.0}},
    {"id": "df_pool105", "overlay": {**BASE, "min_daily_reward_pool": 105.0}},
    # E) combos that look promising structurally
    {"id": "df_max3_tox40", "overlay": {**BASE, "day_flatten_max_net": 3, "tox_blackout_ticks": 40, "tox_move_cents": 1.5}},
    {"id": "df_max8_pool110", "overlay": {**BASE, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0}},
    {"id": "df_global", "overlay": {**BASE, "day_flatten_global": True}},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(data: dict) -> None:
    data["updated_at"] = utc_now()
    STATUS.write_text(json.dumps(data, indent=2, default=str))


def run_liveish_candidate(mode: str, overlay: dict, days_file: Path | None, tag: str) -> dict:
    out_path = OUTDIR / f"wave2_{tag}_{mode}.json"
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
        text = proc.stdout.strip()
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


def promote(cid: str, overlay: dict, sample: float, n30: float, n60: float) -> None:
    import shutil

    champ_src = STRAT
    # Bake overlay defaults into a new champion copy by writing a thin wrapper note;
    # strategy already accepts cfg — we update defaults by patching a copy.
    text = champ_src.read_text()
    # Ensure day_flatten defaults match overlay
    new_name = f"strategy_creative_wave2_{cid}.py"
    dest = ROOT / "research" / "champions" / new_name
    # Patch default day_flatten_max_net / related if present in overlay
    patched = text
    if "day_flatten_max_net" in overlay:
        import re

        patched = re.sub(
            r'day_flatten_max_net",\s*[\d.]+',
            f'day_flatten_max_net", {float(overlay["day_flatten_max_net"])}',
            patched,
            count=1,
        )
    if overlay.get("min_daily_reward_pool") is not None:
        import re

        patched = re.sub(
            r'min_daily_reward_pool",\s*[\d.]+',
            f'min_daily_reward_pool", {float(overlay["min_daily_reward_pool"])}',
            patched,
            count=1,
        )
    # For non-default flags, keep as cfg-overridable; also write overlay sidecar in promotion json
    dest.write_text(patched)
    shutil.copy2(dest, ROOT / "research" / "champions" / "strategy_current_best.py")
    shutil.copy2(dest, ROOT / "strategy.py")
    shutil.copy2(dest, ROOT / "research" / "champions" / f"strategy_creative_{cid}.py")

    art = {
        "job": f"creative_wave2_promotion_{cid}",
        "label": f"creative_{cid}",
        "parent": "creative_day_boundary_flatten",
        "eval": "liveish",
        "overlay": overlay,
        "created_at": utc_now(),
        "windows_liveish": {"sample": sample, "30d": n30, "60d": n60},
        "gates_beaten": {"30d_gate": GATE_30D, "60d_gate": GATE_60D, "sample_gate": GATE_SAMPLE},
    }
    (ROOT / "results" / f"promotion_creative_{cid}.json").write_text(json.dumps(art, indent=2))

    gate_md = ROOT / "research" / "PROMOTION_GATE.md"
    gate_md.write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `creative_{cid}` (creative wave2 over day_boundary_flatten)
Files: `research/champions/{new_name}` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave2 {utc_now()} under **LIVEISH Aug10** gates. Prior day_boundary_flatten liveish: sample 651.39 / 30d 1431.56 / 60d 1979.75.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **{sample:.2f}** | false |
| **30d** | **{n30:.2f}** | false |
| **60d** | **{n60:.2f}** | false |

**To replace champion:** both **liveish-30d > {n30:.2f}** AND **liveish-60d > {n60:.2f}** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >{sample:.2f}. Inventory: soft ≤35 ≥20; hard ≤100.

Creative overlay: `{json.dumps(overlay)}`

Artifact: `results/promotion_creative_{cid}.json`
"""
    )


def main() -> None:
    status = {
        "wave": "creative_wave2",
        "started_at": utc_now(),
        "champion": "creative_day_boundary_flatten",
        "gates": {"sample": GATE_SAMPLE, "30d": GATE_30D, "60d": GATE_60D},
        "pid": os.getpid(),
        "phase": "sample_sweep",
        "candidates": {},
        "promoted": False,
        "running_pids": [os.getpid()],
        "n_candidates": len(CANDIDATES),
    }
    write_status(status)

    # --- sample sweep ---
    rows = []
    for cand in CANDIDATES:
        cid = cand["id"]
        print(f"[wave2] sample {cid} ...", flush=True)
        m = run_liveish_candidate("sample", cand["overlay"], None, cid)
        err = bool(m.get("error"))
        net = float(m.get("net_pnl") or m.get("sample_net_pnl") or 0.0) if not err else None
        row = {
            "id": cid,
            "overlay": cand["overlay"],
            "sample_net_pnl": net,
            "max_dd_pct": m.get("max_dd_pct"),
            "soft_reject": m.get("soft_reject"),
            "n_fills": m.get("n_fills"),
            "reward_pnl": m.get("reward_pnl"),
            "trading_pnl": m.get("trading_pnl"),
            "error": err,
        }
        rows.append(row)
        status["candidates"][cid] = row
        status["phase"] = f"sample_sweep:{cid}"
        write_status(status)
        print(f"  -> sample_net={net}", flush=True)

    # rank by sample
    ok = [r for r in rows if not r["error"] and r["sample_net_pnl"] is not None]
    ok.sort(key=lambda r: r["sample_net_pnl"], reverse=True)

    # advance anyone with sample >= floor OR top-5 by sample (always include ctrl)
    advance = []
    seen = set()
    for r in ok:
        if r["sample_net_pnl"] >= PROMOTE_SAMPLE_FLOOR or r["id"] == "df_max5_ctrl":
            advance.append(r)
            seen.add(r["id"])
    for r in ok[:5]:
        if r["id"] not in seen:
            advance.append(r)
            seen.add(r["id"])

    status["phase"] = "window_eval"
    status["advance"] = [r["id"] for r in advance]
    write_status(status)

    days_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
    days_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"
    window_rows = []
    best = None

    for r in advance:
        cid = r["id"]
        overlay = r["overlay"]
        print(f"[wave2] 30d {cid} ...", flush=True)
        m30 = run_liveish_candidate("window", overlay, days_30, f"{cid}_30d")
        n30 = float(m30.get("net_pnl") or 0.0) if not m30.get("error") else None
        print(f"  -> 30d={n30}", flush=True)
        print(f"[wave2] 60d {cid} ...", flush=True)
        m60 = run_liveish_candidate("window", overlay, days_60, f"{cid}_60d")
        n60 = float(m60.get("net_pnl") or 0.0) if not m60.get("error") else None
        print(f"  -> 60d={n60}", flush=True)
        wrow = {
            "id": cid,
            "overlay": overlay,
            "sample": r["sample_net_pnl"],
            "30d": n30,
            "60d": n60,
            "soft_reject_30": m30.get("soft_reject"),
            "soft_reject_60": m60.get("soft_reject"),
            "beats_gates": bool(
                n30 is not None
                and n60 is not None
                and n30 > GATE_30D
                and n60 > GATE_60D
                and not m30.get("soft_reject")
                and not m60.get("soft_reject")
            ),
        }
        window_rows.append(wrow)
        status["candidates"][cid]["30d"] = n30
        status["candidates"][cid]["60d"] = n60
        status["candidates"][cid]["beats_gates"] = wrow["beats_gates"]
        status["phase"] = f"window_eval:{cid}"
        write_status(status)
        if wrow["beats_gates"]:
            if best is None or (n30 + n60) > (best["30d"] + best["60d"]):
                best = wrow

    promoted = False
    if best is not None:
        print(f"[wave2] PROMOTING {best['id']}", flush=True)
        promote(best["id"], best["overlay"], best["sample"], best["30d"], best["60d"])
        promoted = True
        status["promoted"] = True
        status["promoted_id"] = best["id"]
        status["promoted_windows"] = best
    else:
        print("[wave2] no promote — none beat both new gates", flush=True)

    # findings
    lines = [
        "# Creative wave2 findings",
        "",
        f"Started: {status['started_at']}",
        f"Champion parent: creative_day_boundary_flatten",
        f"Gates: sample>{GATE_SAMPLE} / 30d>{GATE_30D} / 60d>{GATE_60D} (liveish)",
        f"Promoted: {promoted}" + (f" → {best['id']}" if best else ""),
        "",
        "## Sample sweep (liveish)",
        "",
        "| id | sample | dd% | fills | notes |",
        "|----|-------:|----:|------:|-------|",
    ]
    for r in ok:
        lines.append(
            f"| {r['id']} | {r['sample_net_pnl']:.2f} | {r.get('max_dd_pct')} | {r.get('n_fills')} | |"
        )
    lines += ["", "## Window evals", ""]
    lines.append("| id | sample | 30d | 60d | beats |")
    lines.append("|----|-------:|----:|----:|:-----:|")
    for w in window_rows:
        lines.append(
            f"| {w['id']} | {w['sample']:.2f} | {w['30d']} | {w['60d']} | {w['beats_gates']} |"
        )
    FINDINGS.write_text("\n".join(lines) + "\n")

    status["phase"] = "done"
    status["finished_at"] = utc_now()
    status["window_rows"] = window_rows
    write_status(status)
    print("[wave2] done", flush=True)


if __name__ == "__main__":
    main()
