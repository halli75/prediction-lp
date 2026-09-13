"""Event-driven LP backtest engine over 1-min mids (+ optional trades)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sim.fills import (
    MAKER_FEE_BPS,
    MAKER_REBATE_BPS,
    OpenQuote,
    fee_on_notional,
    fills_from_mid_path,
    fills_from_trade,
)
from sim.metrics import summarize
from sim.portfolio import Portfolio
from sim.rewards import QuoteScoreInput, q_min_for_quotes, sample_reward_usd


DEFAULT_CONFIG = {
    "capital0": 10_000.0,
    "tick": 0.01,
    "competition_q_mult": 25.0,  # exogenous competition = mult * our typical Q
    "competition_q_floor": 500.0,
    "samples_per_day": 1440,
    "equity_stride": 60,  # record equity every N minutes
    "use_trades": True,
    "adverse_lookback_min": 5,  # minutes of future mid move for adverse bias
    "min_daily_payout": 1.0,
}


class BacktestEngine:
    def __init__(
        self,
        markets: list[dict[str, Any]],
        strategy: Any,
        config: dict[str, Any] | None = None,
    ):
        self.markets = {m["market_id"]: m for m in markets}
        self.strategy = strategy
        self.cfg = {**DEFAULT_CONFIG, **(config or {})}

    def run(
        self,
        prices: pd.DataFrame,
        trades: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        cfg = self.cfg
        capital0 = float(cfg["capital0"])
        port = Portfolio(cash=capital0, capital0=capital0)

        prices = prices.sort_values(["ts", "market_id"]).reset_index(drop=True)
        if prices.empty:
            return summarize([], capital0, 0, 0, 0, 0, {"error": "empty_prices"})
        # Infer reward sample count from the bar (1-min → 1440; 5-min → 288)
        uniq_ts = prices["ts"].drop_duplicates().sort_values()
        if len(uniq_ts) >= 2:
            med_dt = float(uniq_ts.diff().median())
            if med_dt > 0:
                cfg["samples_per_day"] = max(1, int(round(86400.0 / med_dt)))

        # Index trades by (market_id, minute_ts)
        trades_by_key: dict[tuple[str, int], list[dict]] = {}
        if cfg["use_trades"] and trades is not None and len(trades) > 0:
            tdf = trades.copy()
            tdf["minute"] = (tdf["ts"].astype("int64") // 60) * 60
            for row in tdf.itertuples(index=False):
                key = (str(row.market_id), int(row.minute))
                trades_by_key.setdefault(key, []).append(
                    {
                        "price": float(row.price),
                        "size": float(row.size),
                        "side": str(row.side),
                    }
                )

        # Precompute mid series per market for adverse look-ahead
        mid_series: dict[str, pd.Series] = {}
        for mid_id, g in prices.groupby("market_id", sort=False):
            mid_series[str(mid_id)] = g.set_index("ts")["mid"].astype(float)

        prev_mid: dict[str, float] = {}
        open_quotes: dict[str, OpenQuote] = {}
        equity: list[float] = []
        equity_ts: list[int] = []
        n_fills = 0
        daily_reward_acc: dict[str, float] = {}  # date -> accrued before min payout
        last_mids: dict[str, float] = {}
        current_day: str | None = None

        # Iterate minutes; process all markets at each timestamp group
        for ts, group in prices.groupby("ts", sort=True):
            ts_i = int(ts)
            day = str(pd.Timestamp(ts_i, unit="s", tz="UTC").date())
            if current_day is None:
                current_day = day
            elif day != current_day:
                amt = daily_reward_acc.pop(current_day, 0.0)
                if amt >= float(cfg["min_daily_payout"]):
                    port.apply_reward(amt)
                current_day = day

            for row in group.itertuples(index=False):
                market_id = str(row.market_id)
                meta = self.markets.get(market_id)
                if meta is None:
                    continue
                mid = float(row.mid)
                last_mids[market_id] = mid
                inv = port.inv(market_id)

                # 1) Fills against previous quotes using mid path
                oq = open_quotes.get(market_id)
                if oq is not None and market_id in prev_mid:
                    # Aggressor on a bid hit is a SELL; on an ask lift a BUY.
                    # Look-ahead mid move scales fill size (adverse selection).
                    series = mid_series.get(market_id)
                    adv_bid = self._adverse_boost(series, ts_i, "SELL", mid)
                    adv_ask = self._adverse_boost(series, ts_i, "BUY", mid)
                    for fill in fills_from_mid_path(oq, prev_mid[market_id], mid):
                        boost = adv_bid if fill.side == "buy_yes" else adv_ask
                        cap = oq.bid_size if fill.side == "buy_yes" else oq.ask_size
                        fill.size = min(cap, fill.size * float(boost))
                        notional = fill.size * fill.price
                        fill.fee = fee_on_notional(notional, MAKER_FEE_BPS)
                        fill.rebate = fee_on_notional(notional, MAKER_REBATE_BPS)
                        self._apply_fill(port, market_id, fill)
                        n_fills += 1

                    # Trade tape fills with adverse selection bias
                    for tr in trades_by_key.get((market_id, ts_i), []):
                        adv = self._adverse_boost(
                            mid_series.get(market_id), ts_i, tr["side"], mid
                        )
                        for fill in fills_from_trade(
                            oq, tr["price"], tr["size"], tr["side"], adv
                        ):
                            self._apply_fill(port, market_id, fill)
                            n_fills += 1

                # 2) Ask strategy for new quotes
                tick = float(cfg["tick"])
                best_bid = mid - tick
                best_ask = mid + tick
                # Prefer L2-derived competition on the row; else market exogenous
                row_comp = getattr(row, "competition_q", None)
                if row_comp is not None and not (row_comp != row_comp):  # not NaN
                    competition_q = float(row_comp)
                    # If we quote behind a tight BBO, treat the touch as extra Q
                    bb = getattr(row, "best_bid", None)
                    ba = getattr(row, "best_ask", None)
                    if bb == bb and ba == ba and bb is not None and ba is not None:
                        spr = float(ba) - float(bb)
                        if 0 < spr <= 0.02:
                            competition_q *= 1.15
                else:
                    competition_q = float(
                        meta.get(
                            "competition_q",
                            max(
                                cfg["competition_q_floor"],
                                cfg["competition_q_mult"]
                                * float(meta.get("rewards_min_size", 50)),
                            ),
                        )
                    )
                # Prefer L2 BBO when present
                if hasattr(row, "best_bid") and row.best_bid == row.best_bid:
                    best_bid = float(row.best_bid)
                if hasattr(row, "best_ask") and row.best_ask == row.best_ask:
                    best_ask = float(row.best_ask)

                state = {
                    "ts": ts_i,
                    "market_id": market_id,
                    "mid": mid,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "inv_yes": inv.yes,
                    "inv_no": inv.no,
                    "cash": port.cash,
                    "capital0": capital0,
                    "rewards_min_size": float(meta.get("rewards_min_size", 50)),
                    "rewards_max_spread": float(meta.get("rewards_max_spread", 3.5)),
                    "daily_reward_pool": float(meta.get("daily_reward_pool", 0)),
                    "competition_q": competition_q,
                }
                raw = self.strategy.quote(state) or {}
                bid_p = raw.get("bid_price")
                ask_p = raw.get("ask_price")
                bid_s = float(raw.get("bid_size") or 0.0)
                ask_s = float(raw.get("ask_size") or 0.0)

                # Sanity clamps
                if bid_p is not None:
                    bid_p = float(bid_p)
                    if bid_p <= 0 or bid_p >= mid:
                        bid_p = None
                if ask_p is not None:
                    ask_p = float(ask_p)
                    if ask_p >= 1 or ask_p <= mid:
                        ask_p = None
                # Affordability: don't bid more YES than cash allows
                if bid_p is not None and bid_s > 0:
                    max_afford = max(0.0, port.cash / bid_p)
                    bid_s = min(bid_s, max_afford)
                    if bid_s <= 0:
                        bid_p = None
                # Don't sell more YES than inventory (allow naked short NO-equiv via selling YES we don't have -> treat as short YES / long NO by creating NO?)
                # Simpler: selling YES we don't have means we buy NO at (1-ask) economically:
                # We allow short YES by requiring cash buffer for settlement risk; cap by cash.
                if ask_p is not None and ask_s > 0 and inv.yes < ask_s:
                    # Convert uncovered portion into synthetic short: need collateral ~ask
                    uncovered = ask_s - max(inv.yes, 0.0)
                    collat = uncovered * float(ask_p)
                    if collat > port.cash:
                        ask_s = max(inv.yes, 0.0) + max(0.0, port.cash / float(ask_p))
                    if ask_s <= 0:
                        ask_p = None

                oq_new = OpenQuote(bid_p, ask_p, bid_s, ask_s)
                open_quotes[market_id] = oq_new

                # 3) LP reward sample (~1/min)
                q_in = QuoteScoreInput(
                    mid=mid,
                    bid_price=bid_p,
                    ask_price=ask_p,
                    bid_size=bid_s,
                    ask_size=ask_s,
                    max_spread_cents=float(meta.get("rewards_max_spread", 3.5)),
                    min_size=float(meta.get("rewards_min_size", 50)),
                )
                our_q = q_min_for_quotes(q_in)
                sample = sample_reward_usd(
                    our_q,
                    float(state["competition_q"]),
                    float(meta.get("daily_reward_pool", 0)),
                    int(cfg["samples_per_day"]),
                )
                daily_reward_acc[day] = daily_reward_acc.get(day, 0.0) + sample

                prev_mid[market_id] = mid

            stride = max(int(cfg["equity_stride"]), 1)
            if (ts_i // 60) % stride == 0:
                eq = port.mark_to_market(last_mids)
                equity.append(eq)
                equity_ts.append(ts_i)

        # Flush remaining daily rewards
        for _d, amt in list(daily_reward_acc.items()):
            if amt >= float(cfg["min_daily_payout"]):
                port.apply_reward(amt)
        daily_reward_acc.clear()

        # Final equity point
        eq = port.mark_to_market(last_mids)
        if not equity or equity[-1] != eq:
            equity.append(eq)
            equity_ts.append(int(prices["ts"].iloc[-1]))

        extra = {
            "start_ts": int(prices["ts"].iloc[0]),
            "end_ts": int(prices["ts"].iloc[-1]),
            "n_markets": len(self.markets),
            "final_cash": round(port.cash, 4),
            "inventory": {
                k: {"yes": round(v.yes, 4), "no": round(v.no, 4)}
                for k, v in port.inventory.items()
            },
        }
        return summarize(
            equity,
            capital0,
            port.rewards_earned,
            port.fees_paid,
            port.rebates,
            n_fills,
            extra,
        )

    def _apply_fill(self, port: Portfolio, market_id: str, fill) -> None:
        inv = port.inv(market_id)
        if fill.side == "buy_yes":
            cost = fill.size * fill.price
            port.cash -= cost
            inv.yes += fill.size
            inv.yes_cost += cost
        elif fill.side == "sell_yes":
            # Selling YES: if we have YES, reduce it; else create short YES
            # economically equivalent to buying NO at (1-price) funded by proceeds
            proceeds = fill.size * fill.price
            port.cash += proceeds
            if inv.yes >= fill.size:
                inv.yes -= fill.size
            else:
                short = fill.size - max(inv.yes, 0.0)
                inv.yes = 0.0
                # Buy NO with residual to keep YES+NO≈constant under complete set:
                # When shorting YES at p, buy NO at 1-p to stay hedged in binary.
                no_price = 1.0 - fill.price
                no_cost = short * no_price
                port.cash -= no_cost
                inv.no += short
                inv.no_cost += no_cost
        if fill.fee:
            port.apply_fee(fill.fee)
        if fill.rebate:
            port.apply_rebate(fill.rebate)

    def _adverse_boost(
        self,
        series: pd.Series | None,
        ts_i: int,
        side: str,
        mid_now: float,
    ) -> float:
        """Boost fill size when future mid move favors the aggressor (hurts us)."""
        if series is None or series.empty:
            return 1.0
        lb = int(self.cfg["adverse_lookback_min"])
        future_ts = ts_i + lb * 60
        # find nearest future mid
        try:
            # series index is ts
            idx = series.index.searchsorted(future_ts)
            if idx >= len(series):
                idx = len(series) - 1
            mid_f = float(series.iloc[idx])
        except Exception:
            return 1.0
        move = mid_f - mid_now
        # BUY aggressor profits if mid rises; that means our ask got adversely selected
        if side.upper() == "BUY":
            return float(np.clip(1.0 + 5.0 * max(move, 0.0), 0.5, 2.5))
        return float(np.clip(1.0 + 5.0 * max(-move, 0.0), 0.5, 2.5))
