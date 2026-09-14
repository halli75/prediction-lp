"""Fill model: mid-cross + optional trade-tape hits with adverse selection."""

from __future__ import annotations

from dataclasses import dataclass


# Approximate Polymarket crypto/fees: makers often ~0; take tiny residual.
# We model resting LP as maker: small fee or rebate. Documented in README.
MAKER_FEE_BPS = 0.0  # maker fee in bps of notional
MAKER_REBATE_BPS = 0.0
TAKER_FEE_BPS = 10.0  # unused for resting quotes; kept for completeness

# Adverse selection: when mid moves against us after a fill, extra mark loss
# is already captured by MTM; we additionally bias fill probability / size with
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


def _clip_frac(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def fills_from_mid_path(
    quote: OpenQuote,
    prev_mid: float,
    mid: float,
    max_fill_frac: float = 1.0,
    adverse_boost: float = 1.0,
) -> list[Fill]:
    """
    If mid crosses through resting quotes, fill the crossed size (capped).

    - mid drops through bid -> our bid is hit (we buy YES)
    - mid rises through ask -> our ask is lifted (we sell YES)

    max_fill_frac < 1 models partial queue / incomplete fill.
    adverse_boost > 1 scales size when the subsequent mid move favors the
    aggressor (stronger adverse selection) — still capped at resting size.
    """
    fills: list[Fill] = []
    frac = _clip_frac(max_fill_frac) * max(0.0, float(adverse_boost))
    # Never fill more than resting size
    frac = min(frac, 1.0)

    if quote.bid_price is not None and quote.bid_size > 0:
        if prev_mid >= quote.bid_price > mid:
            size = quote.bid_size * frac
            if size > 0:
                notional = size * quote.bid_price
                fee = fee_on_notional(notional, MAKER_FEE_BPS)
                rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
                fills.append(Fill("buy_yes", quote.bid_price, size, fee, rebate))

    if quote.ask_price is not None and quote.ask_size > 0:
        if prev_mid <= quote.ask_price < mid:
            size = quote.ask_size * frac
            if size > 0:
                notional = size * quote.ask_price
                fee = fee_on_notional(notional, MAKER_FEE_BPS)
                rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
                fills.append(Fill("sell_yes", quote.ask_price, size, fee, rebate))

    return fills


def fills_from_mid_persist(
    quote: OpenQuote,
    mid: float,
    bid_through_rows: int,
    ask_through_rows: int,
    persist_rows: int,
    max_fill_frac: float = 1.0,
    adverse_boost_bid: float = 1.0,
    adverse_boost_ask: float = 1.0,
) -> tuple[list[Fill], int, int, OpenQuote]:
    """
    Require mid to stay through the quote for `persist_rows` consecutive rows
    before filling; if mid recovers before that, the pending cross cancels.

    Returns (fills, new_bid_through_rows, new_ask_through_rows, updated_quote).
    Updated quote has filled side size reduced (remaining resting size).
    """
    fills: list[Fill] = []
    bid_rows = bid_through_rows
    ask_rows = ask_through_rows
    bid_p, ask_p = quote.bid_price, quote.ask_price
    bid_s, ask_s = quote.bid_size, quote.ask_size

    if bid_p is not None and bid_s > 0 and mid < bid_p:
        bid_rows += 1
    else:
        bid_rows = 0

    if ask_p is not None and ask_s > 0 and mid > ask_p:
        ask_rows += 1
    else:
        ask_rows = 0

    need = max(int(persist_rows), 1)

    if bid_rows >= need and bid_p is not None and bid_s > 0:
        frac = min(1.0, _clip_frac(max_fill_frac) * max(0.0, float(adverse_boost_bid)))
        size = bid_s * frac
        if size > 0:
            notional = size * bid_p
            fills.append(
                Fill(
                    "buy_yes",
                    bid_p,
                    size,
                    fee_on_notional(notional, MAKER_FEE_BPS),
                    fee_on_notional(notional, MAKER_REBATE_BPS),
                )
            )
            bid_s = max(0.0, bid_s - size)
            if bid_s <= 1e-12:
                bid_p, bid_s = None, 0.0
            bid_rows = 0

    if ask_rows >= need and ask_p is not None and ask_s > 0:
        frac = min(1.0, _clip_frac(max_fill_frac) * max(0.0, float(adverse_boost_ask)))
        size = ask_s * frac
        if size > 0:
            notional = size * ask_p
            fills.append(
                Fill(
                    "sell_yes",
                    ask_p,
                    size,
                    fee_on_notional(notional, MAKER_FEE_BPS),
                    fee_on_notional(notional, MAKER_REBATE_BPS),
                )
            )
            ask_s = max(0.0, ask_s - size)
            if ask_s <= 1e-12:
                ask_p, ask_s = None, 0.0
            ask_rows = 0

    return fills, bid_rows, ask_rows, OpenQuote(bid_p, ask_p, bid_s, ask_s)


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
