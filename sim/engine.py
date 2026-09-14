"""Event-driven LP backtest engine over 1-min mids (+ optional trades)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sim.fills import (
    OpenQuote,
    fills_from_mid_path,
    fills_from_mid_persist,
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
    # --- realism knobs (defaults preserve legacy optimistic behavior) ---
    "quote_latency_rows": 0,  # new quotes/cancels apply after N per-market rows
    "max_fill_frac": 1.0,  # mid-cross fills at most this fraction of resting size
    "adverse_mid_cross_strength": 0.0,  # 0=off; >0 boosts mid-cross size when adverse
    "fill_persist_rows": 0,  # 0=path-cross; >=1 require mid through quote for M rows
    "portfolio_inv_cap": 0.0,  # 0=off; else hard cap on sum_m |yes-no|
}

# Stricter defaults for --liveish (closer to a deployed bot).
LIVEISH_CONFIG = {
    "quote_latency_rows": 1,
    "max_fill_frac": 0.40,
    "adverse_mid_cross_strength": 6.0,
    "fill_persist_rows": 1,
    "portfolio_inv_cap": 400.0,
    "adverse_lookback_min": 5,
    "use_trades": False,
}


def liveish_engine_config(base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge caller config with LIVEISH_CONFIG (liveish realism keys win)."""
    merged = {**DEFAULT_CONFIG, **(base or {})}
    for k, v in LIVEISH_CONFIG.items():
        merged[k] = v
    if base and "capital0" in base:
        merged["capital0"] = base["capital0"]
    return merged


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
        # Optional diagnostics (empty by default; does not affect PnL)
        self.fills_ledger: list[dict[str, Any]] = []
        self.rewards_ledger: list[dict[str, Any]] = []
        self._current_ts: int | None = None
        self._current_mid: float | None = None
        self._last_mids: dict[str, float] = {}

    def run(
        self,
        prices: pd.DataFrame,
        trades: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        cfg = self.cfg
        capital0 = float(cfg["capital0"])
        port = Portfolio(cash=capital0, capital0=capital0)
        self.fills_ledger = []
        self.rewards_ledger = []
        self._current_ts = None
        self._current_mid = None
        self._last_mids = {}

        prices = prices.sort_values(["ts", "market_id"]).reset_index(drop=True)
        if prices.empty:
            return summarize([], capital0, 0, 0, 0, 0, {"error": "empty_prices"})

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
        # Latency: pending quote replaces open after N per-market rows
        pending_quotes: dict[str, tuple[OpenQuote, int]] = {}
        # Persist-fill counters
        bid_through: dict[str, int] = {}
        ask_through: dict[str, int] = {}
        equity: list[float] = []
        equity_ts: list[int] = []
        n_fills = 0
        daily_reward_acc: dict[str, float] = {}  # date -> accrued before min payout
        last_mids: dict[str, float] = {}
        current_day: str | None = None

        quote_latency = max(int(cfg.get("quote_latency_rows") or 0), 0)
        max_fill_frac = float(cfg.get("max_fill_frac", 1.0))
        adv_strength = float(cfg.get("adverse_mid_cross_strength") or 0.0)
        fill_persist = max(int(cfg.get("fill_persist_rows") or 0), 0)
        port_cap = float(cfg.get("portfolio_inv_cap") or 0.0)

        # Iterate minutes; process all markets at each timestamp group
        for ts, group in prices.groupby("ts", sort=True):
            ts_i = int(ts)
            day = str(pd.Timestamp(ts_i, unit="s", tz="UTC").date())
            if current_day is None:
                current_day = day
            elif day != current_day:
                amt = daily_reward_acc.pop(current_day, 0.0)
                if amt >= float(cfg["min_daily_payout"]):
                    cash_before = port.cash
                    port.apply_reward(amt)
                    self.rewards_ledger.append(
                        {
                            "date": current_day,
                            "ts": ts_i,
                            "amount": float(amt),
                            "cash_before": cash_before,
                            "cash_after": port.cash,
                        }
                    )
                current_day = day

            # Portfolio-level |net| for strategy state / enforcement
            portfolio_abs_inv = sum(
                abs(iv.yes - iv.no) for iv in port.inventory.values()
            )

            for row in group.itertuples(index=False):
                market_id = str(row.market_id)
                meta = self.markets.get(market_id)
                if meta is None:
                    continue
                mid = float(row.mid)
                last_mids[market_id] = mid
                self._current_ts = ts_i
                self._current_mid = mid
                inv = port.inv(market_id)

                # Activate pending quotes whose latency has elapsed
                if market_id in pending_quotes:
                    pq, left = pending_quotes[market_id]
                    left -= 1
                    if left <= 0:
                        open_quotes[market_id] = pq
                        del pending_quotes[market_id]
                        bid_through[market_id] = 0
                        ask_through[market_id] = 0
                    else:
                        pending_quotes[market_id] = (pq, left)

                # 1) Fills against previous (resting) quotes
                oq = open_quotes.get(market_id)
                if oq is not None and market_id in prev_mid:
                    series_m = mid_series.get(market_id)
                    if fill_persist > 0:
                        adv_bid = self._adverse_mid_cross_boost(
                            series_m, ts_i, "buy_yes", mid, adv_strength
                        )
                        adv_ask = self._adverse_mid_cross_boost(
                            series_m, ts_i, "sell_yes", mid, adv_strength
                        )
                        fills, br, ar, oq2 = fills_from_mid_persist(
                            oq,
                            mid,
                            bid_through.get(market_id, 0),
                            ask_through.get(market_id, 0),
                            fill_persist,
                            max_fill_frac=max_fill_frac,
                            adverse_boost_bid=adv_bid,
                            adverse_boost_ask=adv_ask,
                        )
                        bid_through[market_id] = br
                        ask_through[market_id] = ar
                        open_quotes[market_id] = oq2
                        oq = oq2
                        for fill in fills:
                            self._apply_fill(port, market_id, fill)
                            n_fills += 1
                    else:
                        # Path-cross with optional per-side adverse boost + partial fill
                        adv_b = self._adverse_mid_cross_boost(
                            series_m, ts_i, "buy_yes", mid, adv_strength
                        )
                        adv_a = self._adverse_mid_cross_boost(
                            series_m, ts_i, "sell_yes", mid, adv_strength
                        )
                        bp, ap, bs, a_s = oq.bid_price, oq.ask_price, oq.bid_size, oq.ask_size
                        pm = prev_mid[market_id]
                        for fill in fills_from_mid_path(
                            OpenQuote(bp, None, bs, 0.0),
                            pm,
                            mid,
                            max_fill_frac=max_fill_frac,
                            adverse_boost=adv_b,
                        ):
                            self._apply_fill(port, market_id, fill)
                            n_fills += 1
                            bs = max(0.0, bs - fill.size)
                            if bs <= 1e-12:
                                bp, bs = None, 0.0
                        for fill in fills_from_mid_path(
                            OpenQuote(None, ap, 0.0, a_s),
                            pm,
                            mid,
                            max_fill_frac=max_fill_frac,
                            adverse_boost=adv_a,
                        ):
                            self._apply_fill(port, market_id, fill)
                            n_fills += 1
                            a_s = max(0.0, a_s - fill.size)
                            if a_s <= 1e-12:
                                ap, a_s = None, 0.0
                        oq = OpenQuote(bp, ap, bs if bp is not None else 0.0, a_s if ap is not None else 0.0)
                        open_quotes[market_id] = oq

                    # Trade tape fills with adverse selection bias
                    for tr in trades_by_key.get((market_id, ts_i), []):
                        adv = self._adverse_boost(series_m, ts_i, tr["side"], mid)
                        for fill in fills_from_trade(
                            oq, tr["price"], tr["size"], tr["side"], adv
                        ):
                            self._apply_fill(port, market_id, fill)
                            n_fills += 1

                # Refresh portfolio abs after fills
                portfolio_abs_inv = sum(
                    abs(iv.yes - iv.no) for iv in port.inventory.values()
                )

                # 2) Ask strategy for new quotes
                tick = float(cfg["tick"])
                best_bid = mid - tick
                best_ask = mid + tick
                # Prefer L2-derived competition on the row; else market exogenous
                row_comp = getattr(row, "competition_q", None)
                if row_comp is not None and not (row_comp != row_comp):  # not NaN
                    competition_q = float(row_comp)
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
                    "portfolio_abs_inv": portfolio_abs_inv,
                    "portfolio_inv_cap": port_cap,
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

                # Portfolio-level inventory cap enforcement (engine hard guard)
                if port_cap > 0 and portfolio_abs_inv >= port_cap:
                    net = inv.yes - inv.no
                    # Only allow reducing side
                    if net >= 0:
                        bid_p, bid_s = None, 0.0
                    if net <= 0:
                        ask_p, ask_s = None, 0.0

                oq_new = OpenQuote(bid_p, ask_p, bid_s, ask_s)
                if quote_latency <= 0:
                    open_quotes[market_id] = oq_new
                    bid_through[market_id] = 0
                    ask_through[market_id] = 0
                    pending_quotes.pop(market_id, None)
                else:
                    # Old resting quotes remain live until latency elapses
                    pending_quotes[market_id] = (oq_new, quote_latency)

                # 3) LP reward sample (~1/min) — score the quote we *intended*
                # (pending), approximating live reward accrual on displayed book.
                # Use resting open quote if latency>0 and we still show old quotes.
                scored = open_quotes.get(market_id, oq_new)
                q_in = QuoteScoreInput(
                    mid=mid,
                    bid_price=scored.bid_price,
                    ask_price=scored.ask_price,
                    bid_size=scored.bid_size,
                    ask_size=scored.ask_size,
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
        end_ts = int(prices["ts"].iloc[-1]) if len(prices) else 0
        for _d, amt in list(daily_reward_acc.items()):
            if amt >= float(cfg["min_daily_payout"]):
                cash_before = port.cash
                port.apply_reward(amt)
                self.rewards_ledger.append(
                    {
                        "date": _d,
                        "ts": end_ts,
                        "amount": float(amt),
                        "cash_before": cash_before,
                        "cash_after": port.cash,
                    }
                )
        daily_reward_acc.clear()

        # Final equity point
        eq = port.mark_to_market(last_mids)
        if not equity or equity[-1] != eq:
            equity.append(eq)
            equity_ts.append(int(prices["ts"].iloc[-1]))

        self._last_mids = dict(last_mids)
        extra = {
            "start_ts": int(prices["ts"].iloc[0]),
            "end_ts": int(prices["ts"].iloc[-1]),
            "n_markets": len(self.markets),
            "final_cash": round(port.cash, 4),
            "inventory": {
                k: {"yes": round(v.yes, 4), "no": round(v.no, 4)}
                for k, v in port.inventory.items()
            },
            "realism": {
                "quote_latency_rows": quote_latency,
                "max_fill_frac": max_fill_frac,
                "adverse_mid_cross_strength": adv_strength,
                "fill_persist_rows": fill_persist,
                "portfolio_inv_cap": port_cap,
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
        inv_yes_before = float(inv.yes)
        inv_no_before = float(inv.no)
        cash_before = float(port.cash)
        mid_at = float(self._current_mid) if self._current_mid is not None else float("nan")
        ts_at = int(self._current_ts) if self._current_ts is not None else 0

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

        # Diagnostics only — never used by metrics / strategy
        portfolio_abs_inv_after = sum(
            abs(iv.yes - iv.no) for iv in port.inventory.values()
        )
        meta = self.markets.get(market_id, {})
        side = str(fill.side)
        action = "BUY_YES" if side == "buy_yes" else "SELL_YES"
        self.fills_ledger.append(
            {
                "ts": ts_at,
                "iso_time": str(pd.Timestamp(ts_at, unit="s", tz="UTC")),
                "market_id": market_id,
                "question": meta.get("question", ""),
                "side": side,
                "action": action,
                "price": float(fill.price),
                "size": float(fill.size),
                "notional": float(fill.size) * float(fill.price),
                "fee": float(fill.fee or 0.0),
                "rebate": float(fill.rebate or 0.0),
                "mid_at_fill": mid_at,
                "inv_yes_before": inv_yes_before,
                "inv_no_before": inv_no_before,
                "inv_yes_after": float(inv.yes),
                "inv_no_after": float(inv.no),
                "cash_before": cash_before,
                "cash_after": float(port.cash),
                "portfolio_abs_inv_after": float(portfolio_abs_inv_after),
            }
        )

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

    def _adverse_mid_cross_boost(
        self,
        series: pd.Series | None,
        ts_i: int,
        fill_side: str,
        mid_now: float,
        strength: float,
    ) -> float:
        """
        Scale mid-cross fill size when future mid continues against us.

        buy_yes (bid hit) is adverse if mid falls further.
        sell_yes (ask lifted) is adverse if mid rises further.
        strength=0 → always 1.0 (legacy).
        """
        if strength <= 0 or series is None or series.empty:
            return 1.0
        lb = int(self.cfg["adverse_lookback_min"])
        future_ts = ts_i + lb * 60
        try:
            idx = series.index.searchsorted(future_ts)
            if idx >= len(series):
                idx = len(series) - 1
            mid_f = float(series.iloc[idx])
        except Exception:
            return 1.0
        move = mid_f - mid_now
        if fill_side == "buy_yes":
            adverse = max(-move, 0.0)
        else:
            adverse = max(move, 0.0)
        # Map adverse move (price units) through strength → boost in ~[1, 2.5]
        return float(np.clip(1.0 + strength * adverse, 1.0, 2.5))
