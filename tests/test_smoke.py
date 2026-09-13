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
from prepare import DEFAULT_DAYS, SPARSE_DAYS, YES_TOKENS, _sanitize_days, continuous_days


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


def _state(**kw):
    base = {
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
    base.update(kw)
    return base


def test_strategy_quotes_inside_band():
    s = Strategy()
    q = s.quote(_state())
    assert q["bid_price"] is not None and q["ask_price"] is not None
    assert q["bid_price"] < 0.5 < q["ask_price"]
    assert q["bid_size"] >= 10


def test_cancel_on_move_pulls_both_sides():
    s = Strategy({"cancel_move": 0.02, "pause_secs": 0})
    q0 = s.quote(_state(mid=0.50, ts=0))
    assert q0["bid_price"] is not None and q0["ask_price"] is not None
    q1 = s.quote(_state(mid=0.53, ts=60))
    assert q1["bid_price"] is None and q1["ask_price"] is None
    assert q1["bid_size"] == 0.0 and q1["ask_size"] == 0.0
    # next bar at the new level requotes (one-bar cancel, not cancel-until-settle)
    q2 = s.quote(_state(mid=0.53, ts=120))
    assert q2["bid_price"] is not None and q2["ask_price"] is not None


def test_pause_after_fill_quotes_reducing_side():
    s = Strategy({"pause_secs": 100, "cancel_move": 1.0})
    s.quote(_state(ts=0, inv_yes=0, inv_no=0))
    s.quote(_state(ts=10, inv_yes=20, inv_no=0))  # inferred buy fill
    paused = s.quote(_state(ts=50, inv_yes=20, inv_no=0))
    assert paused["bid_price"] is None and paused["bid_size"] == 0.0
    assert paused["ask_price"] is not None and paused["ask_size"] > 0
    after = s.quote(_state(ts=120, inv_yes=20, inv_no=0))
    assert after["bid_price"] is not None and after["ask_price"] is not None


def test_near_mid_shrinks_size():
    wide = Strategy({"spread_frac": 0.9, "size_mult": 4.0, "near_mid_size_frac": 0.5, "near_mid_half": 0.02, "cancel_move": 1.0, "reward_spread_boost": 0.0})
    tight = Strategy({"spread_frac": 0.2, "size_mult": 4.0, "near_mid_size_frac": 0.5, "near_mid_half": 0.02, "cancel_move": 1.0, "reward_spread_boost": 0.0})
    qw = wide.quote(_state())
    qt = tight.quote(_state())
    assert qw["bid_size"] > qt["bid_size"]
    assert qt["bid_size"] >= 10


def test_inventory_and_portfolio_caps():
    s = Strategy({"inv_soft_cap": 10, "max_abs_inv": 20, "portfolio_inv_cap": 50, "cancel_move": 1.0, "pause_secs": 0})
    soft = s.quote(_state(inv_yes=15, market_id="a"))
    assert soft["bid_price"] is None and soft["ask_price"] is not None
    hard = s.quote(_state(inv_yes=25, market_id="a"))
    assert hard["bid_price"] is None and hard["ask_price"] is not None
    # second name pushes gross |net| over the portfolio cap → no adding
    s.quote(_state(inv_yes=30, market_id="b"))
    port = s.quote(_state(inv_yes=30, market_id="c"))
    assert port["bid_price"] is None


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


def test_continuous_days_may_aug():
    days = continuous_days("2026-05-01", "2026-08-10")
    assert days[0] == "2026-05-01"
    assert days[-1] == "2026-08-10"
    gap = {f"2026-06-{d:02d}" for d in range(12, 18)}
    assert not (set(days) & gap)
    assert len(days) >= 90
    # default prepare window is this continuous set
    assert DEFAULT_DAYS[0] == "2026-05-01"
    assert len(DEFAULT_DAYS) == len(days)
    cleaned = _sanitize_days(["2026-02-01", "2026-06-14", "2026-05-14", "2026-09-01"])
    assert cleaned == ["2026-05-14"]
    assert 8 <= len(SPARSE_DAYS) <= 16


def test_token_universe_seed_size():
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
