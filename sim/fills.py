"""Fill model: mid-cross + optional trade-tape hits with adverse selection."""

from __future__ import annotations

from dataclasses import dataclass


# Approximate Polymarket crypto/fees: makers often ~0; take tiny residual.
# We model resting LP as maker: small fee or rebate. Documented in README.
MAKER_FEE_BPS = 0.0  # maker fee in bps of notional
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


def fills_from_mid_path(
    quote: OpenQuote,
    prev_mid: float,
    mid: float,
    max_fill_frac: float = 1.0,
) -> list[Fill]:
    """
    If mid crosses through resting quotes, fill the crossed size (capped).

    - mid drops through bid -> our bid is hit (we buy YES)
    - mid rises through ask -> our ask is lifted (we sell YES)
    """
    fills: list[Fill] = []
    if quote.bid_price is not None and quote.bid_size > 0:
        if prev_mid >= quote.bid_price > mid:
            size = quote.bid_size * max_fill_frac
            notional = size * quote.bid_price
            fee = fee_on_notional(notional, MAKER_FEE_BPS)
            rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
            fills.append(Fill("buy_yes", quote.bid_price, size, fee, rebate))

    if quote.ask_price is not None and quote.ask_size > 0:
        if prev_mid <= quote.ask_price < mid:
            size = quote.ask_size * max_fill_frac
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
