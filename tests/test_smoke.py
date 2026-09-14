"""Smoke tests with fixtures — no network."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.rewards import QuoteScoreInput, order_score, q_min_for_quotes
from strategy import Strategy


def test_order_score_quadratic():
    s = order_score(3.0, 1.0, 100.0)
    assert abs(s - ((2 / 3) ** 2) * 100) < 1e-9
    assert order_score(3.0, 3.0, 100.0) == 0.0
    assert order_score(3.0, -0.1, 100.0) == 0.0


def test_q_min_two_sided_vs_single():
    two = q_min_for_quotes(
        QuoteScoreInput(0.5, 0.48, 0.52, 100, 100, 5.0, 10)
    )
    one = q_min_for_quotes(
        QuoteScoreInput(0.5, 0.48, None, 100, 0, 5.0, 10)
    )
    assert two > one > 0


def test_q_min_tails_require_two_sided():
    q = q_min_for_quotes(QuoteScoreInput(0.05, 0.03, None, 100, 0, 5.0, 10))
    assert q == 0.0


def test_strategy_quotes_inside_band():
    s = Strategy()
    q = s.quote(
        {
            "ts": 0,
            "market_id": "m1",
            "mid": 0.5,
            "best_bid": 0.49,
            "best_ask": 0.51,
            "inv_yes": 0,
            "inv_no": 0,
            "cash": 10_000,
            "capital0": 10_000,
            "rewards_min_size": 10,
            "rewards_max_spread": 5.0,
            "daily_reward_pool": 500,
            "competition_q": 200,
        }
    )
    assert q["bid_price"] is not None and q["ask_price"] is not None
    assert q["bid_price"] < 0.5 < q["ask_price"]
    assert q["bid_size"] >= 10


def test_evaluate_fixture():
    py = ROOT / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    cp = subprocess.run(
        [str(py), str(ROOT / "evaluate.py"), "--fixture"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, cp.stderr
    m = json.loads(cp.stdout)
    assert "holdout_net_pnl" in m
    assert m["n_markets"] == 2
