#!/usr/bin/env python3
"""Creative wave5: early-bleed hunt on champion ovn_e3.

Fix May/early-June inventory bleed without sacrificing 30d/60d edge.
Promote only if liveish 30d>1703.17 AND 60d>2710.25 AND 90d>2109.
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
STATUS = ROOT / "results" / "swarm_creative_wave5_status.json"
FINDINGS = ROOT / "results" / "creative_wave5_findings.md"
OUTDIR = ROOT / "results" / "creative"
OUTDIR.mkdir(parents=True, exist_ok=True)

GATE_SAMPLE = 726.73
GATE_30D = 1703.17
GATE_60D = 2710.25
GATE_90D = 2089.00
PROMOTE_90D = GATE_90D + 20.0  # clearly better by >$20
SAMPLE_ADVANCE_FLOOR = 650.0
MAX_DD = 25.0

PARENT = {
    "day_flatten": True,
    "day_flatten_max_net": 8,
    "min_daily_reward_pool": 110.0,
    "overnight_quiet": True,
    "overnight_mode": "reduce_only",
    "overnight_end_hour": 3,
}

def P(**kw):
    return {**PARENT, **kw}

CANDIDATES = [
    # A) inv_age_flatten (milder ages first — age120 crushed sample in smoke)
    {"id": "age30", "overlay": P(max_inv_age_ticks=30)},
    {"id": "age60", "overlay": P(max_inv_age_ticks=60)},
    {"id": "age120", "overlay": P(max_inv_age_ticks=120)},
    {"id": "age240", "overlay": P(max_inv_age_ticks=240)},
    {"id": "age480", "overlay": P(max_inv_age_ticks=480)},
    # B) warm_start — calendar until date (targets May bleed; no-op on later 30d/60d)
    {"id": "wcal_jun01_sz05_net3", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.5, warm_max_net=3
    )},
    {"id": "wcal_jun01_sz05_net5", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.5, warm_max_net=5
    )},
    {"id": "wcal_jun01_sz07_net5", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.7, warm_max_net=5
    )},
    {"id": "wcal_jun15_sz05_net5", "overlay": P(
        warm_start=True, warm_until_date="2026-06-15", warm_size_frac=0.5, warm_max_net=5
    )},
    {"id": "wcal_jun15_sz07_net3", "overlay": P(
        warm_start=True, warm_until_date="2026-06-15", warm_size_frac=0.7, warm_max_net=3
    )},
    # B2) relative warm_days (as specified; may shrink early days of every window)
    {"id": "warm7_sz07_net5", "overlay": P(warm_start=True, warm_days=7, warm_size_frac=0.7, warm_max_net=5)},
    {"id": "warm14_sz05_net5", "overlay": P(warm_start=True, warm_days=14, warm_size_frac=0.5, warm_max_net=5)},
    # C) fill_rate_brake
    {"id": "fr_w15_t2_b20", "overlay": P(fill_rate_window=15, fill_rate_threshold=2, fill_rate_brake_ticks=20)},
    {"id": "fr_w20_t3_b30", "overlay": P(fill_rate_window=20, fill_rate_threshold=3, fill_rate_brake_ticks=30)},
    {"id": "fr_w40_t4_b60", "overlay": P(fill_rate_window=40, fill_rate_threshold=4, fill_rate_brake_ticks=60)},
    {"id": "fr_w20_t3_b30_sz07", "overlay": P(
        fill_rate_window=20, fill_rate_threshold=3, fill_rate_brake_ticks=30, fill_rate_size_frac=0.7
    )},
    # D) daily_trading_stop
    {"id": "dts40", "overlay": P(daily_trading_stop=40)},
    {"id": "dts80", "overlay": P(daily_trading_stop=80)},
    {"id": "dts120", "overlay": P(daily_trading_stop=120)},
    {"id": "dts160", "overlay": P(daily_trading_stop=160)},
    {"id": "dts80_empty", "overlay": P(daily_trading_stop=80, daily_stop_mode="empty")},
    {"id": "dts120_empty", "overlay": P(daily_trading_stop=120, daily_stop_mode="empty")},
    # E) combos — calendar warm + inv_age (prime early-bleed thesis)
    {"id": "wcal_jun01_age240", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.7, warm_max_net=5,
        max_inv_age_ticks=240
    )},
    {"id": "wcal_jun01_age480", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.5, warm_max_net=5,
        max_inv_age_ticks=480
    )},
    {"id": "wcal_jun15_age240", "overlay": P(
        warm_start=True, warm_until_date="2026-06-15", warm_size_frac=0.7, warm_max_net=5,
        max_inv_age_ticks=240
    )},
    {"id": "age240_dts80", "overlay": P(max_inv_age_ticks=240, daily_trading_stop=80)},
    {"id": "age480_fr_w20", "overlay": P(
        max_inv_age_ticks=480, fill_rate_window=20, fill_rate_threshold=3, fill_rate_brake_ticks=30
    )},
    {"id": "wcal_jun01_age240_fr", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.7, warm_max_net=5,
        max_inv_age_ticks=240, fill_rate_window=20, fill_rate_threshold=3, fill_rate_brake_ticks=30
    )},
    {"id": "wcal_jun01_age240_dts80", "overlay": P(
        warm_start=True, warm_until_date="2026-06-01", warm_size_frac=0.7, warm_max_net=5,
        max_inv_age_ticks=240, daily_trading_stop=80
    )},
]

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_status(data: dict) -> None:
    data["updated_at"] = utc_now()
    STATUS.write_text(json.dumps(data, indent=2, default=str))


def run_liveish_candidate(mode: str, overlay: dict, days_file: Path | None, tag: str) -> dict:
    out_path = OUTDIR / f"wave5_{tag}_{mode}.json"
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


def _sub_default(text: str, key: str, value_repr: str) -> str:
    """Replace cfg.get("key", DEFAULT) default value."""
    # bool True/False
    pat_bool = rf'({key}",\s*)(True|False)(\))'
    if re.search(pat_bool, text):
        return re.sub(pat_bool, rf'\g<1>{value_repr}\g<3>', text, count=1)
    pat = rf'({key}",\s*)([^)\n]+)(\))'
    return re.sub(pat, rf'\g<1>{value_repr}\g<3>', text, count=1)


def promote(cid: str, overlay: dict, sample: float, n30: float, n60: float, n90: float) -> None:
    text = STRAT.read_text()
    # Bake parent + new mode defaults into promoted champion
    text = re.sub(
        r'day_flatten",\s*False\)',
        'day_flatten", True))  # PROMOTED creative default',
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
    if "min_daily_reward_pool" in overlay:
        text = re.sub(
            r'min_daily_reward_pool",\s*[\d.]+',
            f'min_daily_reward_pool", {float(overlay["min_daily_reward_pool"])}',
            text,
            count=1,
        )
    if overlay.get("overnight_quiet") is True:
        text = re.sub(r'overnight_quiet",\s*False\)', 'overnight_quiet", True)', text, count=1)
    if "overnight_end_hour" in overlay:
        text = re.sub(
            r'overnight_end_hour",\s*[^)\n]+',
            f'overnight_end_hour", {repr(overlay["overnight_end_hour"])}',
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
    # WAVE5 knobs → defaults
    for key, cast in [
        ("max_inv_age_ticks", int),
        ("warm_start", bool),
        ("warm_days", int),
        ("warm_size_frac", float),
        ("warm_max_net", float),
        ("warm_until_date", str),
        ("fill_rate_window", int),
        ("fill_rate_threshold", int),
        ("fill_rate_brake_ticks", int),
        ("fill_rate_size_frac", float),
        ("daily_trading_stop", float),
    ]:
        if key not in overlay:
            continue
        val = cast(overlay[key])
        if isinstance(val, bool):
            rep = "True" if val else "False"
            text = re.sub(rf'{key}",\s*(True|False)\)', f'{key}", {rep})', text, count=1)
        else:
            text = re.sub(rf'{key}",\s*[^)\n]+', f'{key}", {repr(val)}', text, count=1)
    if overlay.get("daily_stop_mode"):
        text = re.sub(
            r'daily_stop_mode",\s*"[^"]+"',
            f'daily_stop_mode", "{overlay["daily_stop_mode"]}"',
            text,
            count=1,
        )
    if overlay.get("inv_age_flatten") is True:
        text = re.sub(r'inv_age_flatten",\s*False\)', 'inv_age_flatten", True)', text, count=1)

    header = (
        f'"""Promoted creative champion: creative_wave5_{cid}\n\n'
        f"Fork of creative_wave4_ovn_e3 + WAVE5 early-bleed overlay {json.dumps(overlay)}.\n"
        f"Liveish: sample {sample:.2f} / 30d {n30:.2f} / 60d {n60:.2f} / 90d {n90:.2f}.\n"
        f'"""\n'
    )
    if text.startswith('"""'):
        end = text.find('"""', 3)
        if end != -1:
            text = text[end + 3 :].lstrip("\n")
    text = header + text

    new_name = f"strategy_creative_wave5_{cid}.py"
    dest = ROOT / "research" / "champions" / new_name
    dest.write_text(text)
    shutil.copy2(dest, ROOT / "research" / "champions" / "strategy_current_best.py")
    shutil.copy2(dest, ROOT / "strategy.py")
    shutil.copy2(dest, ROOT / "research" / "champions" / f"strategy_creative_{cid}.py")

    art = {
        "job": f"creative_wave5_promotion_{cid}",
        "label": f"creative_wave5_{cid}",
        "parent": "creative_wave4_ovn_e3",
        "eval": "liveish",
        "overlay": overlay,
        "created_at": utc_now(),
        "windows_liveish": {"sample": sample, "30d": n30, "60d": n60, "90d": n90},
        "gates_beaten": {
            "30d_gate": GATE_30D,
            "60d_gate": GATE_60D,
            "90d_gate_promote": PROMOTE_90D,
            "sample_gate": GATE_SAMPLE,
        },
    }
    (ROOT / "results" / f"promotion_creative_wave5_{cid}.json").write_text(json.dumps(art, indent=2))

    (ROOT / "research" / "PROMOTION_GATE.md").write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `creative_wave5_{cid}` (creative wave5 early-bleed over ovn_e3)
Files: `research/champions/{new_name}` = `strategy_current_best.py` = root `strategy.py`

Promoted creative wave5 {utc_now()} under **LIVEISH Aug10** gates.
Prior creative_wave4_ovn_e3 liveish: sample 726.73 / 30d 1703.17 / 60d 2710.25 / 90d 2089.00.

## LIVEISH (authoritative promotion gate)

| Window | **Liveish net (GATE)** | Soft_reject |
|--------|-----------------------:|:-----------:|
| 12d sample | **{sample:.2f}** | false |
| **30d** | **{n30:.2f}** | false |
| **60d** | **{n60:.2f}** | false |
| **90d** | **{n90:.2f}** | false |

**To replace champion:** both **liveish-30d > {n30:.2f}** AND **liveish-60d > {n60:.2f}** under the **same `--liveish` flags**, `soft_reject=false`, `max_dd_pct < 25`, sample preferred >{sample:.2f}. Inventory: soft ≤35 ≥20; hard ≤100. Prefer 90d also improves.

Creative overlay: `{json.dumps(overlay)}`

Artifact: `results/promotion_creative_wave5_{cid}.json`
"""
    )


def dd_ok(m: dict) -> bool:
    dd = m.get("max_dd_pct")
    if dd is None:
        return True
    try:
        return float(dd) < MAX_DD
    except (TypeError, ValueError):
        return True


def main() -> None:
    status = {
        "wave": "creative_wave5_early_bleed",
        "started_at": utc_now(),
        "champion": "creative_wave4_ovn_e3",
        "gates": {
            "sample": GATE_SAMPLE,
            "30d": GATE_30D,
            "60d": GATE_60D,
            "90d": GATE_90D,
            "promote_90d": PROMOTE_90D,
        },
        "parent_overlay": PARENT,
        "pid": os.getpid(),
        "phase": "sample_sweep",
        "candidates": {},
        "promoted": False,
        "near_misses": [],
        "running_pids": [os.getpid()],
        "n_candidates": len(CANDIDATES),
        "mandate": "fix early bleed without sacrificing 30d/60d; 90d must clearly beat 2089",
        "overnight_swarm": "PAUSED — do not relaunch",
    }
    write_status(status)

    rows = []
    for cand in CANDIDATES:
        cid = cand["id"]
        print(f"[wave5] sample {cid} ...", flush=True)
        m = run_liveish_candidate("sample", cand["overlay"], None, cid)
        if m.get("error"):
            row = {"id": cid, "overlay": cand["overlay"], "error": True, "sample_net_pnl": None}
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
        print(f"  -> sample_net={row.get('sample_net_pnl')} dd={row.get('max_dd_pct')}", flush=True)

    ok = [r for r in rows if not r.get("error") and r.get("sample_net_pnl") is not None]
    ok.sort(key=lambda r: r["sample_net_pnl"], reverse=True)
    advance = [
        r
        for r in ok
        if r["sample_net_pnl"] >= SAMPLE_ADVANCE_FLOOR
        and not r.get("soft_reject")
        and dd_ok(r)
    ]
    # Prefer sample > champion; keep top by sample
    advance = (advance or ok[:8])[:12]
    status["advance"] = [r["id"] for r in advance]
    status["phase"] = "window_eval"
    write_status(status)

    days_30 = ROOT / "research" / "window_30d_liveish_gate_days.txt"
    days_60 = ROOT / "research" / "window_60d_liveish_gate_days.txt"
    days_90 = ROOT / "research" / "window_90d_days.txt"
    window_rows = []
    gate_passers = []
    for r in advance:
        cid = r["id"]
        overlay = r["overlay"]
        print(f"[wave5] 30d {cid} ...", flush=True)
        m30 = run_liveish_candidate("window", overlay, days_30, f"{cid}_30d")
        n30 = float(m30.get("net_pnl") or 0.0) if not m30.get("error") else None
        print(f"  -> 30d={n30}", flush=True)
        print(f"[wave5] 60d {cid} ...", flush=True)
        m60 = run_liveish_candidate("window", overlay, days_60, f"{cid}_60d")
        n60 = float(m60.get("net_pnl") or 0.0) if not m60.get("error") else None
        print(f"  -> 60d={n60}", flush=True)
        beats = bool(
            n30 is not None
            and n60 is not None
            and n30 > GATE_30D
            and n60 > GATE_60D
            and not m30.get("soft_reject")
            and not m60.get("soft_reject")
            and dd_ok(m30)
            and dd_ok(m60)
        )
        wrow = {
            "id": cid,
            "overlay": overlay,
            "sample": r["sample_net_pnl"],
            "30d": n30,
            "60d": n60,
            "soft_reject_30": m30.get("soft_reject"),
            "soft_reject_60": m60.get("soft_reject"),
            "beats_30_60": beats,
        }
        window_rows.append(wrow)
        status["candidates"][cid]["30d"] = n30
        status["candidates"][cid]["60d"] = n60
        status["candidates"][cid]["beats_30_60"] = beats
        status["phase"] = f"window_eval:{cid}"
        write_status(status)
        if beats:
            gate_passers.append(wrow)

    # 90d for all gate passers; pick best that clears promote_90d
    best = None
    near_misses = []
    for w in gate_passers:
        cid = w["id"]
        print(f"[wave5] 90d {cid} ...", flush=True)
        m90 = run_liveish_candidate("window", w["overlay"], days_90, f"{cid}_90d")
        n90 = float(m90.get("net_pnl") or 0.0) if not m90.get("error") else None
        print(f"  -> 90d={n90}", flush=True)
        w["90d"] = n90
        w["soft_reject_90"] = m90.get("soft_reject")
        w["max_dd_90"] = m90.get("max_dd_pct")
        status["candidates"][cid]["90d"] = n90
        status["phase"] = f"90d:{cid}"
        write_status(status)
        clears_90 = bool(
            n90 is not None
            and n90 > PROMOTE_90D
            and not m90.get("soft_reject")
            and dd_ok(m90)
        )
        w["clears_90_promote"] = clears_90
        if clears_90:
            if best is None or n90 > best["90d"]:
                best = w
        else:
            near_misses.append(
                {
                    "id": cid,
                    "sample": w["sample"],
                    "30d": w["30d"],
                    "60d": w["60d"],
                    "90d": n90,
                    "reason": f"30d+60d clear but 90d {n90} not > {PROMOTE_90D}",
                }
            )

    status["near_misses"] = near_misses
    promoted = False
    if best is not None:
        print(f"[wave5] PROMOTING {best['id']} 90d={best['90d']}", flush=True)
        promote(
            best["id"],
            best["overlay"],
            best["sample"],
            best["30d"],
            best["60d"],
            best["90d"],
        )
        promoted = True
        status["promoted"] = True
        status["promoted_id"] = best["id"]
        status["promoted_windows"] = best
    else:
        print("[wave5] no promote — none beat 30d+60d+90d margin", flush=True)
        if near_misses:
            print(f"[wave5] near-misses: {[n['id'] for n in near_misses]}", flush=True)

    lines = [
        "# Creative wave5 early-bleed findings",
        "",
        f"Started: {status['started_at']}",
        "Champion parent: creative_wave4_ovn_e3",
        f"Gates: sample>{GATE_SAMPLE} / 30d>{GATE_30D} / 60d>{GATE_60D} / 90d_promote>{PROMOTE_90D}",
        f"Promoted: {promoted}" + (f" → {best['id']}" if best else ""),
        "",
        "## Mandate",
        "Fix May/early-June leftover-inventory bleed without sacrificing 30d/60d.",
        "",
        "## Modes implemented",
        "- inv_age_flatten / max_inv_age_ticks (existing WAVE3, exercised)",
        "- warm_start (warm_days, warm_size_frac, warm_max_net, stronger pull/pause)",
        "- fill_rate_brake (sliding window fills → pause add / shrink)",
        "- daily_trading_stop (day MTM < -X → reduce_only or empty)",
        "",
        "## Sample sweep (liveish)",
        "",
        "| id | sample | dd% | fills | vs champ |",
        "|----|-------:|----:|------:|---------:|",
    ]
    for r in ok:
        vs = (r["sample_net_pnl"] - GATE_SAMPLE) if r["sample_net_pnl"] is not None else None
        lines.append(
            f"| {r['id']} | {r['sample_net_pnl']:.2f} | {r.get('max_dd_pct')} | {r.get('n_fills')} | {vs:+.2f} |"
            if vs is not None
            else f"| {r['id']} | err | | | |"
        )
    lines += [
        "",
        "## Window evals",
        "",
        "| id | sample | 30d | 60d | 90d | beats_30_60 | clears_90 |",
        "|----|-------:|----:|----:|----:|:-----------:|:---------:|",
    ]
    for w in window_rows:
        lines.append(
            f"| {w['id']} | {w['sample']:.2f} | {w['30d']} | {w['60d']} | {w.get('90d')} | {w['beats_30_60']} | {w.get('clears_90_promote')} |"
        )
    if near_misses:
        lines += ["", "## Near-misses (30d+60d clear, 90d short)", ""]
        for n in near_misses:
            lines.append(f"- **{n['id']}**: 30d={n['30d']} 60d={n['60d']} 90d={n['90d']} — {n['reason']}")
    FINDINGS.write_text("\n".join(lines) + "\n")

    status["phase"] = "done"
    status["finished_at"] = utc_now()
    status["window_rows"] = window_rows
    write_status(status)
    print("[wave5] done", flush=True)


if __name__ == "__main__":
    main()
