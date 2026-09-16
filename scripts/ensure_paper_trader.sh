#!/usr/bin/env bash
set -euo pipefail
cd /workspace/polymarket-lp-autoresearch
PID_FILE=results/paper/paper.pid
mkdir -p results/paper
alive=0
if [[ -f "$PID_FILE" ]]; then
  pid=$(cat "$PID_FILE" || true)
  if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
    if ps -p "$pid" -o args= | grep -q 'run_paper.py'; then alive=1; fi
  fi
fi
if [[ "$alive" -eq 1 ]]; then
  echo "ALIVE pid=$(cat "$PID_FILE")"
  exit 0
fi
nohup .venv/bin/python -u paper/run_paper.py --capital 10000 --poll-sec 15 --resume --portfolio-inv-cap 800 \
  --status-path results/paper/status.json \
  --fills-csv results/paper/fills.csv \
  --equity-csv results/paper/equity.csv \
  --pid-file results/paper/paper.pid >> results/paper/run.log 2>&1 &
echo "RESTARTED pid=$!"
