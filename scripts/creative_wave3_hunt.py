#!/usr/bin/env python3
"""Creative wave3: structural modes beyond day_flatten max_net tweaks.

Parent champion: creative_df_max8_pool110 (day_flatten=True, day_flatten_max_net=8, min_daily_reward_pool=110).
Promote only if liveish 30d > 1676.34 AND 60d > 2512.14 (same --liveish).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "research" / "creative" / "strategy_creative_base.py"
PY = ROOT / ".venv" / "bin" / "python"
STATUS = ROOT / "results" / "swarm_creative_wave3_status.json"
FINDINGS = ROOT / "results" / "creative_wave3_findings.md"
OUTDIR = ROOT / "results" / "creative"
OUTDIR.mkdir(parents=True, exist_ok=True)

GATE_SAMPLE = 611.05
GATE_30D = 1676.34
GATE_60D = 2512.14
PROMOTE_SAMPLE_FLOOR = 600.0

BASE = {"day_flatten": True, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0}

CANDIDATES = [
    # A) session_flatten
    {"id": "sess12", "overlay": {**BASE, "session_flatten": True, "session_hours": 12}},
    {"id": "sess8", "overlay": {**BASE, "session_flatten": True, "session_hours": 8}},
    {"id": "sess12_max3", "overlay": {**BASE, "session_flatten": True, "session_hours": 12, "session_flatten_max_net": 3}},
    {"id": "sess12_max8", "overlay": {**BASE, "session_flatten": True, "session_hours": 12, "session_flatten_max_net": 8}},
    # B) inventory_age_flatten
    {"id": "age60", "overlay": {**BASE, "max_inv_age_ticks": 60}},
    {"id": "age120", "overlay": {**BASE, "max_inv_age_ticks": 120}},
    {"id": "age240", "overlay": {**BASE, "max_inv_age_ticks": 240}},
    # C) overnight_quiet
    {"id": "ovn_reduce", "overlay": {**BASE, "overnight_quiet": True, "overnight_mode": "reduce_only"}},
    {"id": "ovn_sz03", "overlay": {**BASE, "overnight_quiet": True, "overnight_mode": "size_mult", "overnight_size_mult": 0.3}},
    {"id": "ovn_reduce_0_8", "overlay": {**BASE, "overnight_quiet": True, "overnight_mode": "reduce_only", "overnight_end_hour": 8}},
    # D) carry_budget
    {"id": "carry50", "overlay": {**BASE, "carry_budget_shares": 50}},
    {"id": "carry80", "overlay": {**BASE, "carry_budget_shares": 80}},
    {"id": "carry120", "overlay": {**BASE, "carry_budget_shares": 120}},
    # E) toxic_market_day_ban
    {"id": "ban1p5", "overlay": {**BASE, "tox_day_ban_cents": 1.5}},
    {"id": "ban2p0", "overlay": {**BASE, "tox_day_ban_cents": 2.0}},
    {"id": "ban3p0", "overlay": {**BASE, "tox_day_ban_cents": 3.0}},
    # F) day_flatten + mild harvest gate
    {"id": "dfgate", "overlay": {**BASE, "day_flatten_harvest_gate": True}},
    {"id": "dfgate_vol01", "overlay": {**BASE, "day_flatten_harvest_gate": True, "df_gate_vol": 0.01}},
    {"id": "dfgate_pool110", "overlay": {**BASE, "day_flatten_harvest_gate": True, "df_gate_min_pool": 110.0}},
    # Combos
    {"id": "sess12_ovn", "overlay": {**BASE, "session_flatten": True, "session_hours": 12, "overnight_quiet": True, "overnight_mode": "reduce_only"}},
    {"id": "age120_carry80", "overlay": {**BASE, "max_inv_age_ticks": 120, "carry_budget_shares": 80}},
    {"id": "ovn_ban2", "overlay": {**BASE, "overnight_quiet": True, "overnight_mode": "reduce_only", "tox_day_ban_cents": 2.0}},
    {"id": "sess12_age120", "overlay": {**BASE, "session_flatten": True, "session_hours": 12, "max_inv_age_ticks": 120}},
    {"id": "carry80_dfgate", "overlay": {**BASE, "carry_budget_shares": 80, "day_flatten_harvest_gate": True}},
    {"id": "ban2_age120", "overlay": {**BASE, "tox_day_ban_cents": 2.0, "max_inv_age_ticks": 120}},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(data: dict) -> None:
    data["updated_at"] = utc_now()
    STATUS.write_text(json.dumps(data, indent=2, default=str))


def run_liveish_candidate(mode: str, overlay: dict, days_file: Path | None, tag: str) -> dict:
    out_path = OUTDIR / f"wave3_{tag}_{mode}.json"
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
    # Bake creative_base + overlay defaults into champion copy
    text = STRAT.read_text()
    # Ensure day_flatten defaults True like champion
    text = re.sub(
        r'day_flatten",\s*False\)',
        'day_flatten", True)  # PROMOTED creative default',
        text,
        count=1,
    )
    if "day_flatten_max_net" in overlay:
        text = re.sub(
            r'day_flatten_max_net",\s*[\d.]+',
            f'day_flatten_max_net", {float(overlay["day_flatten_max_net"])}',
            text,
            count=1,
        )
    # Enable promoted mode flags as defaults where bool True / numeric >0
    bool_keys = [
        "session_flatten",
        "overnight_quiet",
        "day_flatten_harvest_gate",
    ]
    for k in bool_keys:
        if overlay.get(k) is True:
            text = re.sub(
                rf'{k}",\s*False\)',
                f'{k}", True)',
                text,
                count=1,
            )
    num_defaults = {
        "session_hours": "session_hours",
        "session_flatten_max_net": "session_flatten_max_net",
        "max_inv_age_ticks": "max_inv_age_ticks",
        "overnight_size_mult": "overnight_size_mult",
        "overnight_end_hour": "overnight_end_hour",
        "carry_budget_shares": "carry_budget_shares",
        "tox_day_ban_cents": "tox_day_ban_cents",
        "df_gate_vol": "df_gate_vol",
        "df_gate_min_pool": "df_gate_min_pool",
    }
    for key, cfg_key in num_defaults.items():
        if key in overlay:
            # patch cfg.get("key", DEFAULT)
            text = re.sub(
                rf'{cfg_key}",\s*[^)]+',
                f'{cfg_key}", {repr(overlay[key])}',
                text,
                count=1,
            )
    if overlay.get("overnight_mode"):
        text = re.sub(
            r'overnight_mode",\s*"[^"]+"',
            f'overnight_mode", "{overlay["overnight_mode"]}"',
            text,
            count=1,
        )

    header = (
        f'"""Promoted creative champion: creative_wave3_{cid}\n\n'
        f"Fork of creative_day_boundary_flatten + WAVE3 overlay {json.dumps(overlay)}.\n"
        f"Liveish: sample {sample:.2f} / 30d {n30:.2f} / 60d {n60:.2f}.\n"
        f'"""\n'
    )
    # strip old module docstring
    if text.startswith('"""'):
        end = text.find('"""', 3)
        if end != -1:
            text = text[end + 3 :].lstrip("\n")
    text = header + text

    new_name = f"strategy_creative_wave3_{cid}.py"
    dest = ROOT / "research" / "champions" / new_name
    dest.write_text(text)
    shutil.copy2(dest, ROOT / "research" / "champions" / "strategy_current_best.py")
    shutil.copy2(dest, ROOT / "strategy.py")
    shutil.copy2(dest, ROOT / "research" / "champions" / f"strategy_creative_{cid}.py")

    art = {
        "job": f"creative_wave3_promotion_{cid}",
        "label": f"creative_wave3_{cid}",
        "parent": "creative_df_max8_pool110",
        "eval": "liveish",
        "overlay": overlay,
        "created_at": utc_now(),
        "windows_liveish": {"sample": sample, "30d": n30, "60d": n60},
        "gates_beaten": {"30d_gate": GATE_30D, "60d_gate": GATE_60D, "sample_gate": GATE_SAMPLE},
    }
    (ROOT / "results" / f"promotion_creative_wave3_{cid}.json").write_text(json.dumps(art, indent=2))

    gate_md = ROOT / "research" / "PROMOTION_GATE.md"
    gate_md.write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `creative_wave3_{cid}` (creative wave3 over df_max8_pool110)
Files: `research/champions/{new_name}` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave3 {utc_now()} under **LIVEISH Aug10** gates. Prior creative_df_max8_pool110 liveish: sample 611.05 / 30d 1676.34 / 60d 2512.14.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **{sample:.2f}** | false |
| **30d** | **{n30:.2f}** | false |
| **60d** | **{n60:.2f}** | false |

**To replace champion:** both **liveish-30d > {n30:.2f}** AND **liveish-60d > {n60:.2f}** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >{sample:.2f}. Inventory: soft ≤35 ≥20; hard ≤100.

Creative overlay: `{json.dumps(overlay)}`

Artifact: `results/promotion_creative_wave3_{cid}.json`
"""
    )


def main() -> None:
    status = {
        "wave": "creative_wave3",
        "started_at": utc_now(),
        "champion": "creative_df_max8_pool110",
        "gates": {"sample": GATE_SAMPLE, "30d": GATE_30D, "60d": GATE_60D},
        "pid": os.getpid(),
        "phase": "sample_sweep",
        "candidates": {},
        "promoted": False,
        "running_pids": [os.getpid()],
        "n_candidates": len(CANDIDATES),
        "modes": [
            "session_flatten",
            "inventory_age_flatten",
            "overnight_quiet",
            "carry_budget",
            "toxic_market_day_ban",
            "day_flatten_harvest_gate",
        ],
    }
    write_status(status)

    rows = []
    for cand in CANDIDATES:
        cid = cand["id"]
        print(f"[wave3] sample {cid} ...", flush=True)
        m = run_liveish_candidate("sample", cand["overlay"], None, cid)
        if m.get("error"):
            row = {
                "id": cid,
                "overlay": cand["overlay"],
                "error": True,
                "sample_net_pnl": None,
            }
        else:
            row = {
                "id": cid,
                "overlay": cand["overlay"],
                "sample_net_pnl": float(m.get("net_pnl") or 0.0),
                "max_dd_pct": m.get("max_dd_pct"),
                "soft_reject": m.get("soft_reject"),
                "n_fills": m.get("n_fills"),
                "reward_pnl": m.get("reward_pnl"),
                "trading_pnl": m.get("trading_pnl"),
                "error": False,
            }
        rows.append(row)
        status["candidates"][cid] = row
        status["phase"] = f"sample:{cid}"
        write_status(status)
        print(f"  -> sample_net={row.get('sample_net_pnl')}", flush=True)

    ok = [r for r in rows if not r.get("error") and r.get("sample_net_pnl") is not None]
    ok.sort(key=lambda r: r["sample_net_pnl"], reverse=True)
    # Advance top sample candidates that clear soft sample floor (or top 8)
    advance = [r for r in ok if r["sample_net_pnl"] >= PROMOTE_SAMPLE_FLOOR and not r.get("soft_reject")]
    if not advance:
        advance = ok[:8]
    else:
        advance = advance[:10]
    status["advance"] = [r["id"] for r in advance]
    status["phase"] = "window_eval"
    write_status(status)

    days_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
    days_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"
    window_rows = []
    best = None
    for r in advance:
        cid = r["id"]
        overlay = r["overlay"]
        print(f"[wave3] 30d {cid} ...", flush=True)
        m30 = run_liveish_candidate("window", overlay, days_30, f"{cid}_30d")
        n30 = float(m30.get("net_pnl") or 0.0) if not m30.get("error") else None
        print(f"  -> 30d={n30}", flush=True)
        print(f"[wave3] 60d {cid} ...", flush=True)
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
        print(f"[wave3] PROMOTING {best['id']}", flush=True)
        promote(best["id"], best["overlay"], best["sample"], best["30d"], best["60d"])
        promoted = True
        status["promoted"] = True
        status["promoted_id"] = best["id"]
        status["promoted_windows"] = best
    else:
        print("[wave3] no promote — none beat both new gates", flush=True)

    lines = [
        "# Creative wave3 findings",
        "",
        f"Started: {status['started_at']}",
        f"Champion parent: creative_df_max8_pool110",
        f"Gates: sample>{GATE_SAMPLE} / 30d>{GATE_30D} / 60d>{GATE_60D} (liveish)",
        f"Promoted: {promoted}" + (f" → {best['id']}" if best else ""),
        "",
        "## Modes",
        "",
        "- session_flatten",
        "- inventory_age_flatten",
        "- overnight_quiet",
        "- carry_budget",
        "- toxic_market_day_ban",
        "- day_flatten_harvest_gate",
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
    print("[wave3] done", flush=True)


if __name__ == "__main__":
    main()
