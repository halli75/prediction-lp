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

from sim.fills import OpenQuote, fills_from_mid_path
from sim.rewards import QuoteScoreInput, order_score, q_min_for_quotes
from strategy import Strategy
from prepare import DEFAULT_DAYS, YES_TOKENS, _sanitize_days


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
            "daily_reward_pool": 100,
            "competition_q": 200,
        }
    )
    assert q["bid_price"] is not None and q["ask_price"] is not None
    assert q["bid_price"] < 0.5 < q["ask_price"]
    assert q["bid_size"] >= 10


def test_mid_path_penetration_partial_fill():
    q = OpenQuote(0.49, 0.51, 100.0, 100.0)
    # 1¢ through the bid — should not take the full 100
    fills = fills_from_mid_path(q, 0.50, 0.48)
    assert len(fills) == 1
    assert fills[0].side == "buy_yes"
    assert 25.0 <= fills[0].size < 100.0


def test_mid_path_no_cross():
    q = OpenQuote(0.48, 0.52, 100.0, 100.0)
    assert fills_from_mid_path(q, 0.50, 0.50) == []


def test_sparse_days_respect_archive_window():
    assert min(DEFAULT_DAYS) >= "2026-02-22"
    assert max(DEFAULT_DAYS) <= "2026-08-10"
    gap = {f"2026-06-{d:02d}" for d in range(12, 18)}
    assert not (set(DEFAULT_DAYS) & gap)
    assert 8 <= len(DEFAULT_DAYS) <= 16
    # sanitizer drops the known gap and out-of-range dates
    cleaned = _sanitize_days(["2026-02-01", "2026-06-14", "2026-05-14", "2026-09-01"])
    assert cleaned == ["2026-05-14"]


def test_token_universe_phase2_size():
    assert 15 <= len(YES_TOKENS) <= 25
    # phase-1 seeds still present
    assert "iran" in {v["slug_key"] for v in YES_TOKENS.values()}
    assert "fed_0" in {v["slug_key"] for v in YES_TOKENS.values()}


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
