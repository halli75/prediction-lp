#!/usr/bin/env python3
"""Watch wave5 axis agents; if liveish sample beats gate, run Aug10 30d+60d and promote on dual beat."""
from __future__ import annotations

import json, os, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "results/swarm_wave5_status.json"
PY = str(ROOT / ".venv/bin/python")
CHAMP_SAMPLE = 528.35
CHAMP_30 = 473.85
CHAMP_60 = 723.72
DAYS_30 = "research/window_30d_liveish_gate_days.txt"
DAYS_60 = "research/window_60d_liveish_gate_days.txt"
POLL = 90
MAX_WALL = 95 * 60  # ~95 min then exit (hunts may continue)


def run_json(cmd, timeout=1800):
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {"error": "nonzero_exit", "code": r.returncode, "stderr": (r.stderr or "")[-1500:]}
    out = (r.stdout or "").strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        i = out.rfind("{")
        return json.loads(out[i:]) if i >= 0 else {"error": "no_json", "stdout": out[-1000:]}


def load_status():
    if not STATUS.exists():
        return {}
    return json.loads(STATUS.read_text())


def save_status(st):
    st["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    STATUS.write_text(json.dumps(st, indent=2, default=str) + "\n")


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def check_inv_caps(strat_path: Path) -> bool:
    text = strat_path.read_text()
    import re
    soft_m = re.search(r'inv_soft_cap",\s*([0-9.]+)', text)
    hard_m = re.search(r'max_abs_inv",\s*([0-9.]+)', text)
    if not soft_m or not hard_m:
        return False
    soft, hard = float(soft_m.group(1)), float(hard_m.group(1))
    return 20.0 <= soft <= 35.0 and hard <= 100.0


def promote(agent_id, strat_best, metrics):
    label = f"wave5_{agent_id.replace('-', '_')}"
    named = ROOT / f"research/champions/strategy_{label}.py"
    shutil.copy2(strat_best, named)
    for dest in [ROOT / "research/champions/strategy_current_best.py", ROOT / "strategy.py"]:
        shutil.copy2(strat_best, dest)
    promo = {
        "job": f"wave5_promotion_{label}",
        "label": label,
        "parent": "pool100",
        "agent_id": agent_id,
        "eval": "liveish",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gate_liveish_aug10": {"sample": CHAMP_SAMPLE, "30d": CHAMP_30, "60d": CHAMP_60},
        "windows_liveish": metrics,
        "note": "Dual liveish window beat via wave5 promote watcher",
    }
    (ROOT / f"results/promotion_{label}.json").write_text(json.dumps(promo, indent=2, default=str))
    gate = ROOT / "research/PROMOTION_GATE.md"
    gate.write_text(
        f"""# Promotion gate (authoritative)

**Current champion:** `{label}` (liveish-validated Aug10 via wave5 `{agent_id}`)
Files: `research/champions/strategy_{label}.py` = `strategy_current_best.py` = root `strategy.py`

| Window (LIVEISH) | Net PnL to beat |
|------------------|----------------:|
| sample | **{metrics['sample']:.2f}** |
| 30d | **{metrics['30d']:.2f}** |
| 60d | **{metrics['60d']:.2f}** |

Prior pool100 Aug10 liveish: sample 528.35 / 30d 473.85 / 60d 723.72

## Rules
1. No optimistic-only promotes.
2. Same `--liveish` flags required.
3. Soft <=35, hard <=100; soft >=20.
"""
    )
    sf = ROOT / "research/shared_findings.json"
    data = json.loads(sf.read_text()) if sf.exists() else {}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["current_champion"] = {"label": label, "eval": "liveish_aug10", "wave": "wave5", "agent_id": agent_id, **metrics}
    findings = data.setdefault("findings", [])
    if isinstance(findings, list):
        findings.append({"ts": data["updated_at"], "agent": agent_id, "event": "promoted_liveish_aug10", "label": label})
        data["findings"] = findings[-200:]
    sf.write_text(json.dumps(data, indent=2, default=str))
    digest = ROOT / "results/overnight_digest.md"
    with open(digest, "a") as f:
        f.write(
            f"\n\n## Wave5 PROMOTION — {label} — {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n\n"
            f"- Agent: `{agent_id}`\n"
            f"- Liveish sample **{metrics['sample']:.2f}** / 30d **{metrics['30d']:.2f}** / 60d **{metrics['60d']:.2f}**\n"
            f"- Beat pool100 Aug10 gates. Champion synced.\n"
        )
    return label


def main():
    t0 = time.time()
    evaluated = set()
    print(f"[wave5-watcher] start gates S>{CHAMP_SAMPLE} 30>{CHAMP_30} 60>{CHAMP_60}", flush=True)
    while time.time() - t0 < MAX_WALL:
        st = load_status()
        agents = st.get("agents", {})
        promotions = st.setdefault("promotions", [])
        candidates = []
        for aid, meta in agents.items():
            if meta.get("kind") == "watcher":
                continue
            agent_dir = ROOT / "research/agents" / aid
            best_m = agent_dir / "best_metrics.json"
            best_s = agent_dir / "strategy_best.py"
            if not best_m.exists() or not best_s.exists():
                # joint hunt uses different artifact
                continue
            try:
                bm = json.loads(best_m.read_text())
            except Exception:
                continue
            pnl = float(bm.get("sample_net_pnl") or -1e18)
            meta["best_sample_net_pnl"] = pnl
            meta["max_dd_pct"] = bm.get("max_dd_pct")
            meta["alive"] = alive(meta.get("pid", -1))
            if pnl > CHAMP_SAMPLE + 0.01 and not bm.get("soft_reject"):
                key = f"{aid}:{pnl:.4f}"
                if key not in evaluated:
                    candidates.append((aid, pnl, best_s, best_m, bm, key))
        # also check joint hunt best
        joint = ROOT / "results/window_aware_hunt_wave5_joint.json"
        if joint.exists():
            try:
                jd = json.loads(joint.read_text())
                st["joint_summary"] = jd.get("wave5_joint_summary") or jd.get("best_vs_pool100_liveish_aug10")
                if jd.get("promoted_liveish_aug10"):
                    promotions.append({"source": "joint", "trial": jd.get("promoted_trial"), "ts": datetime.now(timezone.utc).isoformat()})
            except Exception:
                pass

        for aid, pnl, best_s, best_m, bm, key in candidates:
            print(f"[wave5-watcher] candidate {aid} sample={pnl:.2f} -> window eval", flush=True)
            if not check_inv_caps(best_s):
                print(f"  skip: inv caps out of gate bounds", flush=True)
                evaluated.add(key)
                st.setdefault("skipped_inv_caps", []).append({"agent": aid, "sample": pnl})
                save_status(st)
                continue
            # Ensure strategy.py not overwritten until promote — eval via --strategy-module
            w30 = run_json([PY, "scripts/eval_window.py", "--liveish", "--days-file", DAYS_30, "--strategy-module", str(best_s)], 1800)
            w60 = run_json([PY, "scripts/eval_window.py", "--liveish", "--days-file", DAYS_60, "--strategy-module", str(best_s)], 1800)
            evaluated.add(key)
            rec = {
                "agent": aid, "sample": pnl,
                "net_30d": w30.get("window_net_pnl"), "net_60d": w60.get("window_net_pnl"),
                "soft_30d": w30.get("soft_reject"), "soft_60d": w60.get("soft_reject"),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            st.setdefault("window_evals", []).append(rec)
            print(f"  30d={rec['net_30d']} 60d={rec['net_60d']}", flush=True)
            try:
                n30 = float(w30["window_net_pnl"]); n60 = float(w60["window_net_pnl"])
            except Exception:
                save_status(st); continue
            if (
                pnl > CHAMP_SAMPLE and n30 > CHAMP_30 and n60 > CHAMP_60
                and not w30.get("soft_reject") and not w60.get("soft_reject")
                and not bm.get("soft_reject")
            ):
                label = promote(aid, best_s, {"sample": pnl, "30d": n30, "60d": n60})
                promotions.append({"label": label, "agent": aid, "metrics": {"sample": pnl, "30d": n30, "60d": n60}})
                st["promoted"] = True
                print(f"  *** PROMOTED {label} ***", flush=True)
            save_status(st)

        # refresh alive flags
        for aid, meta in agents.items():
            if "pid" in meta:
                meta["alive"] = alive(meta["pid"])
        alive_n = sum(1 for a, m in agents.items() if m.get("kind") != "watcher" and m.get("alive"))
        st["alive_count"] = alive_n
        save_status(st)
        if alive_n == 0 and time.time() - t0 > 120:
            # wait a bit more for late writes
            print("[wave5-watcher] all hunters done", flush=True)
            break
        time.sleep(POLL)

    st = load_status()
    st["watcher_finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_status(st)
    print("[wave5-watcher] exit", flush=True)


if __name__ == "__main__":
    main()
