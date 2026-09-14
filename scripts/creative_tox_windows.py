#!/usr/bin/env python3
import json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PYB = ROOT / ".venv/bin/python"
STRAT = ROOT / "research/creative/strategy_creative_base.py"
OUT = ROOT / "results/creative"
OUT.mkdir(exist_ok=True)
cands = [
  ("tox_blackout_40_1p5", {"tox_blackout_ticks": 40, "tox_move_cents": 1.5}),
  ("tox_blackout_60_1p0", {"tox_blackout_ticks": 60, "tox_move_cents": 1.0}),
]
for cid, ov in cands:
  for label, days in [("30d", "research/window_30d_liveish_gate_days.txt"), ("60d", "research/window_60d_liveish_gate_days.txt")]:
    print(f"eval {cid} {label}", flush=True)
    cmd = [str(PYB), str(ROOT / "scripts/eval_liveish_candidate.py"), "--mode", "window",
           "--strategy-module", str(STRAT), "--overlay-json", json.dumps(ov),
           "--days-file", str(ROOT / days)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    path = OUT / f"{cid}_{label}.json"
    if r.returncode == 0:
      path.write_text(r.stdout)
      print(r.stdout[-400:], flush=True)
    else:
      path.write_text(json.dumps({"error": True, "stderr": (r.stderr or "")[-2000:]}))
      print("ERR", (r.stderr or "")[-400:], flush=True)
print("tox windows done", flush=True)
