"""Approximate Polymarket LP reward scoring (docs-aligned)."""

from __future__ import annotations

from dataclasses import dataclass


# Docs: c = 3.0 on all markets; samples ~1/min; min payout $1/day.
C_SINGLE_SIDED = 3.0
MIN_DAILY_PAYOUT = 1.0


def order_score(v_cents: float, spread_cents: float, size: float, b: float = 1.0) -> float:
    """S(v,s) = ((v-s)/v)^2 * b * size  (b absorbed as size multiplier when b=1)."""
    if v_cents <= 0 or size <= 0:
        return 0.0
    if spread_cents < 0 or spread_cents >= v_cents:
        return 0.0
    return ((v_cents - spread_cents) / v_cents) ** 2 * b * size


@dataclass
class QuoteScoreInput:
    mid: float
    bid_price: float | None
    ask_price: float | None
    bid_size: float
    ask_size: float
    max_spread_cents: float  # v in cents (e.g. 3.5)
    min_size: float


def q_min_for_quotes(q: QuoteScoreInput) -> float:
    """
    Two-sided Q scoring using YES book only (NO complement approximated as 1-p).

    For a binary YES token mid m:
      bid on YES at p  <->  ask on NO at (1-p)  (complementary)
    We score Q_one as YES-bid quality and Q_two as YES-ask quality,
    which mirrors the docs' one/two book aggregation for a single level each side.
    """
    mid = q.mid
    v = q.max_spread_cents
    if mid <= 0 or mid >= 1:
        return 0.0

    q_one = 0.0
    q_two = 0.0

    if q.bid_price is not None and q.bid_size >= q.min_size:
        spread_cents = (mid - q.bid_price) * 100.0
        q_one += order_score(v, spread_cents, q.bid_size)

    if q.ask_price is not None and q.ask_size >= q.min_size:
        spread_cents = (q.ask_price - mid) * 100.0
        q_two += order_score(v, spread_cents, q.ask_size)

    if 0.10 <= mid <= 0.90:
        # single-sided allowed at /c
        return max(min(q_one, q_two), max(q_one / C_SINGLE_SIDED, q_two / C_SINGLE_SIDED))
    # tails: must be two-sided
    return min(q_one, q_two)


def reward_share(our_q: float, competition_q: float) -> float:
    """Normalized share given exogenous (or book-derived) competition mass."""
    total = our_q + max(competition_q, 0.0)
    if total <= 0 or our_q <= 0:
        return 0.0
    return our_q / total


def sample_reward_usd(
    our_q: float,
    competition_q: float,
    daily_pool_usd: float,
    samples_per_day: int = 1440,
) -> float:
    """Per-minute sample contribution toward daily pool (equal weight approx)."""
    share = reward_share(our_q, competition_q)
    if samples_per_day <= 0:
        return 0.0
    return share * daily_pool_usd / samples_per_day
