"""Fill model: mid-cross + optional trade-tape hits with adverse selection."""

from __future__ import annotations

from dataclasses import dataclass


# Approximate Polymarket crypto/fees: makers are typically ~0 bps on the CLOB.
# Optional 1 bp maker fee is a cheap stand-in for residual friction / gas-like
# cost so reward income is not entirely "free". Rebate stays 0 (no maker rebate
# program modeled). Documented in README. Flip both to 0 for the old path.
MAKER_FEE_BPS = 1.0  # maker fee in bps of notional
MAKER_REBATE_BPS = 0.0
TAKER_FEE_BPS = 10.0  # unused for resting quotes; kept for completeness

# Adverse selection: when mid moves against us after a fill, extra mark loss
# is already captured by MTM; we additionally bias fill probability with
# upcoming mid move magnitude (see engine).


@dataclass
class OpenQuote:
    bid_price: float | None
    ask_price: float | None
    bid_size: float
    ask_size: float


@dataclass
class Fill:
    side: str  # "buy_yes" (our bid hit) or "sell_yes" (our ask lifted)
    price: float
    size: float
    fee: float
    rebate: float


def fee_on_notional(notional: float, bps: float) -> float:
    return abs(notional) * bps / 10_000.0


def _penetration_frac(through: float, ref_price: float) -> float:
    """Larger through-price move ⇒ closer to a full fill (still capped at 1)."""
    # 1¢ through ~0.43; 5¢ ~0.75; 8¢+ ~1.0
    return min(1.0, max(0.30, 0.35 + 8.0 * max(through, 0.0)))


def fills_from_mid_path(
    quote: OpenQuote,
    prev_mid: float,
    mid: float,
    max_fill_frac: float = 1.0,
    adverse_boost: float = 1.0,
) -> list[Fill]:
    """
    If mid crosses through resting quotes, fill a penetration-scaled size.

    - mid drops through bid -> our bid is hit (we buy YES)
    - mid rises through ask -> our ask is lifted (we sell YES)

    adverse_boost (>1 when the subsequent mid move favors the aggressor)
    scales size, then we cap at the resting quote size. This is still a
    sparse mid-cross model, not a full queue simulator.
    """
    fills: list[Fill] = []
    boost = min(2.0, max(0.5, float(adverse_boost)))
    if quote.bid_price is not None and quote.bid_size > 0:
        if prev_mid >= quote.bid_price > mid:
            frac = _penetration_frac(quote.bid_price - mid, quote.bid_price)
            size = min(quote.bid_size, quote.bid_size * frac * max_fill_frac * boost)
            notional = size * quote.bid_price
            fee = fee_on_notional(notional, MAKER_FEE_BPS)
            rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
            fills.append(Fill("buy_yes", quote.bid_price, size, fee, rebate))

    if quote.ask_price is not None and quote.ask_size > 0:
        if prev_mid <= quote.ask_price < mid:
            frac = _penetration_frac(mid - quote.ask_price, quote.ask_price)
            size = min(quote.ask_size, quote.ask_size * frac * max_fill_frac * boost)
            notional = size * quote.ask_price
            fee = fee_on_notional(notional, MAKER_FEE_BPS)
            rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
            fills.append(Fill("sell_yes", quote.ask_price, size, fee, rebate))

    return fills


def fills_from_trade(
    quote: OpenQuote,
    trade_price: float,
    trade_size: float,
    trade_side: str,
    adverse_boost: float = 1.0,
) -> list[Fill]:
    """
    If a public trade prints through our quote, take a fraction of size.

    trade_side: aggressive side ("BUY" means taker bought YES => hits asks).
    adverse_boost in [0,1+] scales fill size (engine sets higher when
    subsequent mid move favors the taker).
    """
    fills: list[Fill] = []
    take = max(0.0, min(1.0, 0.25 * adverse_boost))  # partial participation

    if trade_side.upper() == "BUY" and quote.ask_price is not None:
        if trade_price >= quote.ask_price and quote.ask_size > 0:
            size = min(quote.ask_size, trade_size * take)
            if size > 0:
                notional = size * quote.ask_price
                fills.append(
                    Fill(
                        "sell_yes",
                        quote.ask_price,
                        size,
                        fee_on_notional(notional, MAKER_FEE_BPS),
                        fee_on_notional(notional, MAKER_REBATE_BPS),
                    )
                )
    elif trade_side.upper() == "SELL" and quote.bid_price is not None:
        if trade_price <= quote.bid_price and quote.bid_size > 0:
            size = min(quote.bid_size, trade_size * take)
            if size > 0:
                notional = size * quote.bid_price
                fills.append(
                    Fill(
                        "buy_yes",
                        quote.bid_price,
                        size,
                        fee_on_notional(notional, MAKER_FEE_BPS),
                        fee_on_notional(notional, MAKER_REBATE_BPS),
                    )
                )
    return fills
