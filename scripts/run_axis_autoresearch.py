#!/usr/bin/env python3
"""
Karpathy-style axis autoresearch loop (isolated agent dir).

- Copies strategy.py into research/agents/<agent-id>/
- Each iter: axis-specific mutation → eval_sample → keep if sample_net_pnl
  improves AND not soft-reject, else revert
- Hard-stop if best sample_net_pnl < -200 after 15 iters
- Never keeps soft-rejected strategies
- Updates research/leaderboard.json + shared_findings.json (file locks)
"""

from __future__ import annotations

import argparse
import fcntl
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
AGENTS = RESEARCH / "agents"
LEADERBOARD = RESEARCH / "leaderboard.json"
FINDINGS = RESEARCH / "shared_findings.json"
AXES_PATH = RESEARCH / "axes.json"
PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)

HARD_STOP_ITERS = 15
HARD_STOP_PNL = -200.0


def locked_json_update(path: Path, mutator) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}\n")
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip() or "{}"
            data = json.loads(raw)
            data = mutator(data) or data
            f.seek(0)
            f.truncate()
            f.write(json.dumps(data, indent=2, default=str) + "\n")
            f.flush()
            return data
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def patch_float_default(text: str, name: str, value: float) -> str:
    # Single-line: self.name = float(cfg.get("name", 1.0))
    pattern = rf'(self\.{name}\s*=\s*float\(cfg\.get\("{name}",\s*)([-+eE0-9.]+)(\)\))'
    text2, n = re.subn(pattern, rf"\g<1>{float(value)}\g<3>", text, count=1)
    if n == 0:
        # Multiline: self.name = float(\n    cfg.get("name", 1.0)\n)
        pattern_ml = (
            rf'(self\.{name}\s*=\s*float\(\s*\n\s*cfg\.get\("{name}",\s*)'
            rf'([-+eE0-9.]+)(\)\s*\n\s*\))'
        )
        repl = "self.%s = float(cfg.get(\"%s\", %s))" % (name, name, float(value))
        text2, n = re.subn(pattern_ml, repl, text, count=1)
    if n == 0:
        pattern2 = rf'(self\.{name}\s*=\s*float\(cfg\.get\("{name}",\s*)([^)]+)(\)\))'
        text2, n = re.subn(pattern2, rf"\g<1>{float(value)}\g<3>", text, count=1)
        if n == 0:
            raise RuntimeError(f"could not patch float {name}")
    return text2


def patch_bool_default(text: str, name: str, value: bool) -> str:
    pattern = rf'(self\.{name}\s*=\s*bool\(cfg\.get\("{name}",\s*)(True|False)(\)\))'
    text2, n = re.subn(pattern, rf"\g<1>{value}\g<3>", text, count=1)
    if n == 0:
        raise RuntimeError(f"could not patch bool {name}")
    return text2



def read_float_default(text: str, name: str, fallback: float) -> float:
    m = re.search(
        rf'self\.{name}\s*=\s*float\(cfg\.get\("{name}",\s*([-+eE0-9.]+)\)\)', text
    )
    if not m:
        return fallback
    return float(m.group(1))


def patch_int_default(text: str, name: str, value: int) -> str:
    pattern = rf'(self\.{name}\s*=\s*int\(cfg\.get\("{name}",\s*)(\d+)(\)\))'
    text2, n = re.subn(pattern, rf"\g<1>{int(value)}\g<3>", text, count=1)
    if n == 0:
        raise RuntimeError(f"could not patch int {name}")
    return text2


def patch_allowlist_mode(text: str, mode: str | None) -> str:
    # self.market_allowlist_mode = cfg.get("market_allowlist_mode", None)
    pattern = r'(self\.market_allowlist_mode\s*=\s*cfg\.get\("market_allowlist_mode",\s*)([^)]+)(\))'
    if mode is None:
        repl = r"\g<1>None\g<3>"
    else:
        repl = rf'\g<1>"{mode}"\g<3>'
    text2, n = re.subn(pattern, repl, text, count=1)
    if n == 0:
        raise RuntimeError("could not patch market_allowlist_mode")
    return text2


def hypothesize(axis: str, text: str, rng: random.Random, it: int) -> tuple[str, dict]:
    """Apply one axis-specific mutation; return (new_text, params)."""
    params: dict = {"axis": axis, "iter": it}

    if axis == "inventory_hard_cap":
        # Liveish gate: soft in [20,35], hard in [80,100]
        hard = rng.choice([80, 90, 100])
        soft = float(rng.choice([20, 25, 30, 35]))
        text = patch_float_default(text, "max_abs_inv", hard)
        text = patch_float_default(text, "inv_soft_cap", soft)
        params.update({"max_abs_inv": hard, "inv_soft_cap": soft})

    elif axis == "widen_spread":
        sf = rng.uniform(0.65, 0.95)
        mhs = rng.choice([0.01, 0.015, 0.02, 0.025])
        text = patch_float_default(text, "spread_frac", sf)
        text = patch_float_default(text, "min_half_spread", mhs)
        params.update({"spread_frac": sf, "min_half_spread": mhs})

    elif axis == "shrink_size":
        sm = rng.uniform(0.75, 1.15)
        lp = rng.uniform(0.25, 0.7)
        text = patch_float_default(text, "size_mult", sm)
        text = patch_float_default(text, "low_pool_size_frac", lp)
        params.update({"size_mult": sm, "low_pool_size_frac": lp})

    elif axis == "skew_aggressive":
        sk = rng.uniform(0.15, 0.60)
        text = patch_float_default(text, "skew_bps_per_share", sk)
        params.update({"skew_bps_per_share": sk})

    elif axis == "cancel_on_mid_move":
        # liveish overlays cancel_move=0.02 (~2¢ soft); hunt hard cancel + widen
        soft_c = float(rng.choice([1.5, 2.0, 2.5, 3.0]))
        hard_c = float(rng.choice([2.5, 3.0, 3.5, 4.0, 5.0, 6.0]))
        if hard_c <= soft_c:
            hard_c = soft_c + 1.0
        widen = rng.uniform(1.1, 2.5)
        text = patch_float_default(text, "mid_move_cancel_cents", soft_c)
        text = patch_float_default(text, "mid_move_hard_cancel_cents", hard_c)
        text = patch_float_default(text, "mid_move_widen_mult", widen)
        params.update(
            {
                "mid_move_cancel_cents": soft_c,
                "mid_move_hard_cancel_cents": hard_c,
                "mid_move_widen_mult": widen,
            }
        )

    elif axis == "top5_reward_markets_only":
        text = patch_allowlist_mode(text, "top5")
        # also keep high pool floor
        text = patch_bool_default(text, "enforce_pool_allowlist", True)
        pool = float(rng.choice([400, 500, 514, 750, 1000]))
        text = patch_float_default(text, "min_daily_reward_pool", pool)
        params.update({"market_allowlist_mode": "top5", "min_daily_reward_pool": pool})

    elif axis == "seed_fed_iran_only":
        text = patch_allowlist_mode(text, "fed_iran")
        soft = float(rng.choice([25, 35, 50, 80]))
        hard = float(rng.choice([80, 100, 150, 200]))
        text = patch_float_default(text, "inv_soft_cap", soft)
        text = patch_float_default(text, "max_abs_inv", hard)
        params.update(
            {
                "market_allowlist_mode": "fed_iran",
                "inv_soft_cap": soft,
                "max_abs_inv": hard,
            }
        )

    elif axis == "pull_size_after_adverse_fill":
        ticks = int(rng.choice([8, 12, 16, 24, 32, 40]))
        pm = rng.uniform(0.2, 0.7)
        text = patch_int_default(text, "inv_pause_ticks", ticks)
        text = patch_float_default(text, "pull_size_mult", pm)
        params.update({"inv_pause_ticks": ticks, "pull_size_mult": pm})

    elif axis == "min_edge_vs_bbo":
        edge = float(rng.choice([0.0, 0.005, 0.01, 0.015, 0.02]))
        text = patch_float_default(text, "min_edge_vs_bbo", edge)
        params.update({"min_edge_vs_bbo": edge})

    elif axis == "size_by_reward_pool":
        text = patch_bool_default(text, "enforce_pool_allowlist", True)
        pool = float(rng.choice([100, 125, 150, 175, 200, 250, 300, 400]))
        lp = rng.uniform(0.25, 0.7)
        text = patch_float_default(text, "min_daily_reward_pool", pool)
        text = patch_float_default(text, "low_pool_size_frac", lp)
        params.update(
            {
                "enforce_pool_allowlist": True,
                "min_daily_reward_pool": pool,
                "low_pool_size_frac": lp,
            }
        )

    elif axis == "pause_after_fill":
        ticks = int(rng.choice([3, 5, 8, 12, 16, 24, 32]))
        text = patch_int_default(text, "inv_pause_ticks", ticks)
        params.update({"inv_pause_ticks": ticks})

    elif axis == "vol_regime_filter":
        vf = float(rng.choice([0.01, 0.02, 0.03, 0.04, 0.05]))
        lb = int(rng.choice([3, 5, 8, 10]))
        text = patch_float_default(text, "vol_filter", vf)
        text = patch_int_default(text, "vol_lookback", lb)
        params.update({"vol_filter": vf, "vol_lookback": lb})

    elif axis == "two_sided_strict":
        val = rng.choice([True, False])
        text = patch_bool_default(text, "two_sided_strict", val)
        skip = rng.choice([True, False])
        text = patch_bool_default(text, "skip_extreme_tails", skip)
        soft = float(rng.choice([25, 35, 50, 80]))
        text = patch_float_default(text, "inv_soft_cap", soft)
        params.update(
            {"two_sided_strict": val, "skip_extreme_tails": skip, "inv_soft_cap": soft}
        )

    elif axis == "near_mid_size":
        nm = rng.uniform(0.4, 1.0)
        nd = float(rng.choice([0.01, 0.015, 0.02, 0.025, 0.03]))
        text = patch_float_default(text, "near_mid_size_mult", nm)
        # near_mid_dist may or may not exist; try/skip
        try:
            text = patch_float_default(text, "near_mid_dist", nd)
            params["near_mid_dist"] = nd
        except Exception:
            pass
        params.update({"near_mid_size_mult": nm})

    elif axis == "min_daily_reward_pool_fine":
        text = patch_bool_default(text, "enforce_pool_allowlist", True)
        pool = float(rng.choice([75, 90, 100, 110, 125, 150, 175]))
        lp = rng.uniform(0.35, 0.75)
        text = patch_float_default(text, "min_daily_reward_pool", pool)
        text = patch_float_default(text, "low_pool_size_frac", lp)
        params.update(
            {
                "enforce_pool_allowlist": True,
                "min_daily_reward_pool": pool,
                "low_pool_size_frac": lp,
            }
        )

    elif axis == "free_explore":
        choices = [
            ("max_abs_inv", float(rng.choice([60, 80, 100, 150, 200]))),
            ("inv_soft_cap", float(rng.choice([20, 30, 35, 50, 70]))),
            ("spread_frac", rng.uniform(0.6, 0.95)),
            ("size_mult", rng.uniform(0.8, 1.3)),
            ("skew_bps_per_share", rng.uniform(0.15, 0.55)),
            ("mid_move_cancel_cents", float(rng.choice([1.0, 2.0, 3.0]))),
            ("mid_move_hard_cancel_cents", float(rng.choice([3.0, 4.0, 6.0]))),
            ("min_daily_reward_pool", float(rng.choice([100, 125, 150, 175, 200, 250, 300]))),
            ("pull_size_mult", rng.uniform(0.25, 0.7)),
            ("near_mid_size_mult", rng.uniform(0.45, 1.0)),
        ]
        k = rng.randint(2, 4)
        for name, val in rng.sample(choices, k=k):
            # Commander floor: do not set inventory caps below soft 20 / hard 80
            if name == "max_abs_inv":
                val = max(80.0, float(val))
            elif name == "inv_soft_cap":
                val = max(20.0, float(val))
            text = patch_float_default(text, name, val)
            params[name] = val
        if rng.random() < 0.35:
            mode = rng.choice(["top5", "fed_iran"])
            text = patch_allowlist_mode(text, mode)
            params["market_allowlist_mode"] = mode
        if rng.random() < 0.25:
            ticks = int(rng.choice([6, 8, 12, 16]))
            text = patch_int_default(text, "inv_pause_ticks", ticks)
            params["inv_pause_ticks"] = ticks

    else:
        raise SystemExit(f"unknown axis: {axis}")

    return text, params


def eval_sample(strategy_path: Path, liveish: bool = False) -> dict:
    cmd = [
        str(PY),
        str(ROOT / "scripts" / "eval_sample.py"),
        "--strategy-module",
        str(strategy_path),
    ]
    if liveish:
        cmd.append("--liveish")
    cp = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            f"eval_sample failed rc={cp.returncode}: {cp.stderr or cp.stdout}"
        )
    # stdout may include non-json noise; find last JSON object
    out = cp.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        start = out.find("{")
        end = out.rfind("}")
        if start >= 0 and end > start:
            return json.loads(out[start : end + 1])
        raise


def update_leaderboard(agent_id: str, axis: str, metrics: dict, strategy_best: Path) -> None:
    def mut(data: dict) -> dict:
        data = data or {}
        agents = data.setdefault("agents", {})
        agents[agent_id] = {
            "axis": axis,
            "sample_net_pnl": metrics.get("sample_net_pnl"),
            "max_dd_pct": metrics.get("max_dd_pct"),
            "reward_pnl": metrics.get("reward_pnl"),
            "trading_pnl": metrics.get("trading_pnl"),
            "n_fills": metrics.get("n_fills"),
            "soft_reject": metrics.get("soft_reject"),
            "strategy_best": str(strategy_best),
            "updated_at": time.time(),
        }
        gb = data.get("global_best")
        pnl = float(metrics.get("sample_net_pnl") or -1e18)
        if gb is None or pnl > float(gb.get("sample_net_pnl") or -1e18):
            if not metrics.get("soft_reject"):
                data["global_best"] = {
                    "agent_id": agent_id,
                    "axis": axis,
                    "sample_net_pnl": pnl,
                    "max_dd_pct": metrics.get("max_dd_pct"),
                    "strategy_best": str(strategy_best),
                    "updated_at": time.time(),
                }
        data["updated_at"] = time.time()
        return data

    locked_json_update(LEADERBOARD, mut)


def write_findings(agent_id: str, axis: str, event: dict) -> None:
    def mut(data: dict) -> dict:
        data = data or {}
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        findings = data.setdefault("findings", [])
        findings.append(
            {
                "ts": data["updated_at"],
                "agent_id": agent_id,
                "axis": axis,
                **event,
            }
        )
        # keep last 200
        data["findings"] = findings[-200:]
        axis_status = data.setdefault("axis_status", {})
        st = axis_status.setdefault(axis, {})
        st["last_agent"] = agent_id
        st["last_event"] = event.get("event")
        if "best_sample_net_pnl" in event:
            prev = st.get("best_sample_net_pnl")
            if prev is None or float(event["best_sample_net_pnl"]) > float(prev):
                st["best_sample_net_pnl"] = event["best_sample_net_pnl"]
        if event.get("event") == "hard_stop":
            st["hard_stopped"] = True
            st["hard_stop_reason"] = event.get("reason")
        if event.get("event") == "keep":
            gb = data.get("global_best") or {}
            pnl = float(event.get("sample_net_pnl") or -1e18)
            if not gb or pnl > float(gb.get("sample_net_pnl") or -1e18):
                data["global_best"] = {
                    "agent_id": agent_id,
                    "axis": axis,
                    "sample_net_pnl": pnl,
                    "max_dd_pct": event.get("max_dd_pct"),
                }
        return data

    locked_json_update(FINDINGS, mut)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--axis", required=True)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--liveish", action="store_true",
                    help="eval_sample --liveish (live-realism keep criterion)")
    args = ap.parse_args()

    axes_doc = json.loads(AXES_PATH.read_text())
    known = {a["name"] for a in axes_doc.get("axes", [])}
    if args.axis not in known:
        raise SystemExit(f"unknown axis {args.axis}; known={sorted(known)}")

    agent_dir = AGENTS / args.agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    strat_path = agent_dir / "strategy.py"
    best_path = agent_dir / "strategy_best.py"
    exp_log = agent_dir / "experiments.jsonl"
    best_metrics_path = agent_dir / "best_metrics.json"

    # Fresh copy from repo baseline unless resuming with existing copy
    if not strat_path.exists():
        shutil.copy2(ROOT / "strategy.py", strat_path)
    if not best_path.exists():
        shutil.copy2(strat_path, best_path)

    rng = random.Random(args.seed)

    print(
        f"[axis] agent={args.agent_id} axis={args.axis} iters={args.iters} seed={args.seed} liveish={args.liveish}",
        flush=True,
    )
    baseline = eval_sample(strat_path, liveish=args.liveish)
    best_pnl = float(baseline.get("sample_net_pnl") or -1e18)
    best_metrics = baseline
    if baseline.get("soft_reject"):
        print(
            f"[axis] baseline soft-rejected dd={baseline.get('max_dd_pct')}; "
            "PnL tracked but keep rules still forbid soft-reject keeps",
            flush=True,
        )
    else:
        shutil.copy2(strat_path, best_path)
        best_metrics_path.write_text(json.dumps(baseline, indent=2) + "\n")
        update_leaderboard(args.agent_id, args.axis, baseline, best_path)

    with open(exp_log, "a") as f:
        f.write(
            json.dumps(
                {
                    "iter": 0,
                    "kept": not bool(baseline.get("soft_reject")),
                    "params": "baseline",
                    "metrics": baseline,
                    "ts": time.time(),
                }
            )
            + "\n"
        )

    write_findings(
        args.agent_id,
        args.axis,
        {
            "event": "baseline",
            "sample_net_pnl": best_pnl,
            "max_dd_pct": baseline.get("max_dd_pct"),
            "soft_reject": baseline.get("soft_reject"),
        },
    )
    print(
        f"[axis] baseline sample_net_pnl={best_pnl:.4f} soft_reject={baseline.get('soft_reject')} "
        f"elapsed={baseline.get('elapsed_sec')}",
        flush=True,
    )

    kept_count = 0
    for i in range(1, args.iters + 1):
        # hard-stop check before mutating further if we've done enough and still bad
        if i > HARD_STOP_ITERS and best_pnl < HARD_STOP_PNL:
            reason = (
                f"best sample_net_pnl={best_pnl:.2f} < {HARD_STOP_PNL} after "
                f"{HARD_STOP_ITERS}+ iters"
            )
            print(f"[axis] HARD STOP: {reason}", flush=True)
            write_findings(
                args.agent_id,
                args.axis,
                {
                    "event": "hard_stop",
                    "reason": reason,
                    "best_sample_net_pnl": best_pnl,
                    "iters_done": i - 1,
                },
            )
            break

        prev = strat_path.read_text()
        try:
            new_text, params = hypothesize(args.axis, prev, rng, i)
        except Exception as e:
            print(f"  mutate error: {e}", flush=True)
            with open(exp_log, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "iter": i,
                            "kept": False,
                            "error": f"mutate:{e}",
                            "ts": time.time(),
                        }
                    )
                    + "\n"
                )
            continue

        strat_path.write_text(new_text)
        print(f"[axis] iter {i}/{args.iters} try {params}", flush=True)
        try:
            metrics = eval_sample(strat_path, liveish=args.liveish)
        except Exception as e:
            print(f"  eval error: {e}; revert", flush=True)
            strat_path.write_text(prev)
            with open(exp_log, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "iter": i,
                            "kept": False,
                            "params": params,
                            "error": str(e),
                            "ts": time.time(),
                        }
                    )
                    + "\n"
                )
            continue

        pnl = float(metrics.get("sample_net_pnl") or -1e18)
        soft = bool(metrics.get("soft_reject"))
        # NEVER keep soft-reject
        improved = (pnl > best_pnl) and (not soft)
        if improved:
            best_pnl = pnl
            best_metrics = metrics
            kept_count += 1
            shutil.copy2(strat_path, best_path)
            best_metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
            update_leaderboard(args.agent_id, args.axis, metrics, best_path)
            write_findings(
                args.agent_id,
                args.axis,
                {
                    "event": "keep",
                    "iter": i,
                    "params": params,
                    "sample_net_pnl": pnl,
                    "max_dd_pct": metrics.get("max_dd_pct"),
                    "best_sample_net_pnl": best_pnl,
                },
            )
            print(f"  KEEP pnl={pnl:.4f} dd={metrics.get('max_dd_pct')}", flush=True)
            with open(exp_log, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "iter": i,
                            "kept": True,
                            "params": params,
                            "metrics": metrics,
                            "ts": time.time(),
                        }
                    )
                    + "\n"
                )
        else:
            strat_path.write_text(prev)
            reason = "soft_reject" if soft else "no_improve"
            print(
                f"  DISCARD ({reason}) pnl={pnl:.4f} best={best_pnl:.4f}",
                flush=True,
            )
            with open(exp_log, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "iter": i,
                            "kept": False,
                            "reason": reason,
                            "params": params,
                            "metrics": metrics,
                            "ts": time.time(),
                        }
                    )
                    + "\n"
                )

        # also hard-stop exactly at boundary after completing iter 15
        if i == HARD_STOP_ITERS and best_pnl < HARD_STOP_PNL:
            reason = (
                f"best sample_net_pnl={best_pnl:.2f} < {HARD_STOP_PNL} after "
                f"{HARD_STOP_ITERS} iters"
            )
            print(f"[axis] HARD STOP: {reason}", flush=True)
            write_findings(
                args.agent_id,
                args.axis,
                {
                    "event": "hard_stop",
                    "reason": reason,
                    "best_sample_net_pnl": best_pnl,
                    "iters_done": i,
                },
            )
            break

    # restore working copy to best
    if best_path.exists():
        shutil.copy2(best_path, strat_path)
    if best_metrics:
        best_metrics_path.write_text(json.dumps(best_metrics, indent=2) + "\n")
        update_leaderboard(args.agent_id, args.axis, best_metrics, best_path)

    write_findings(
        args.agent_id,
        args.axis,
        {
            "event": "done",
            "best_sample_net_pnl": best_pnl,
            "keeps": kept_count,
            "iters": args.iters,
        },
    )
    print(
        f"[axis] done agent={args.agent_id} best_sample_net_pnl={best_pnl:.4f} keeps={kept_count}",
        flush=True,
    )


if __name__ == "__main__":
    main()
