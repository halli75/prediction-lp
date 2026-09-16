"""Paper portfolio engine: mid-cross fills + LP reward accrual (simulate only)."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sim.fills import OpenQuote, fills_from_mid_path
from sim.portfolio import Portfolio
from sim.rewards import QuoteScoreInput, q_min_for_quotes, sample_reward_usd

CHAMPION_LABEL = "creative_wave5_fr_w20_t3_b30"

# Liveish-aligned paper defaults
PAPER_ENGINE_CFG = {
    "quote_latency_rows": 1,
    "max_fill_frac": 0.40,
    "adverse_mid_cross_strength": 2.0,  # light heuristic (no future path)
    "portfolio_inv_cap": 800.0,
    "competition_q_mult": 25.0,
    "competition_q_floor": 500.0,
    "min_daily_payout": 1.0,
    "tick": 0.01,
}


@dataclass
class RestingState:
    open_quotes: dict[str, OpenQuote] = field(default_factory=dict)
    pending_quotes: dict[str, tuple[OpenQuote, int]] = field(default_factory=dict)
    prev_mid: dict[str, float] = field(default_factory=dict)
    last_mid_delta: dict[str, float] = field(default_factory=dict)  # for light adverse


class PaperEngine:
    def __init__(
        self,
        markets: list[dict[str, Any]],
        strategy: Any,
        *,
        capital0: float = 10_000.0,
        poll_sec: float = 15.0,
        config: dict[str, Any] | None = None,
        fills_csv: Path | None = None,
        equity_csv: Path | None = None,
        champion: str = CHAMPION_LABEL,
    ):
        self.markets = {m["market_id"]: m for m in markets}
        self.strategy = strategy
        self.cfg = {**PAPER_ENGINE_CFG, **(config or {})}
        self.capital0 = float(capital0)
        self.poll_sec = float(poll_sec)
        self.samples_per_day = max(1, int(round(86400.0 / max(self.poll_sec, 1.0))))
        self.port = Portfolio(cash=self.capital0, capital0=self.capital0)
        self.rest = RestingState()
        self.n_fills = 0
        self.cycle = 0
        self.started_at = time.time()
        self.champion = champion
        self.reward_pnl_est = 0.0  # accrued incl. not-yet-paid day buffer
        self._daily_reward_acc: dict[str, float] = {}
        self._current_day: str | None = None
        self.fills_csv = fills_csv
        self.equity_csv = equity_csv
        self._fills_header_written = False
        self._equity_header_written = False
        self.last_mids: dict[str, float] = {}
        self.last_book_ok = 0
        self.last_n_quoted = 0
        if fills_csv:
            fills_csv.parent.mkdir(parents=True, exist_ok=True)
        if equity_csv:
            equity_csv.parent.mkdir(parents=True, exist_ok=True)

    def set_markets(self, markets: list[dict[str, Any]]) -> None:
        self.markets = {m["market_id"]: m for m in markets}

    def resume_from_session(
        self,
        *,
        fills_csv: Path | None = None,
        status_path: Path | None = None,
        started_at: float | None = None,
    ) -> dict[str, Any]:
        """Rebuild cash/inventory from fills.csv so a restart keeps the session."""
        from sim.fills import Fill

        path = Path(fills_csv or self.fills_csv or "")
        info: dict[str, Any] = {"resumed": False, "n_fills": 0, "cash": self.port.cash}
        if not path or not path.exists():
            return info

        # Replay without re-appending CSV rows
        saved_fills = self.fills_csv
        self.fills_csv = None
        n = 0
        last_cycle = 0
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                side = (row.get("side") or "").strip()
                if side not in ("buy_yes", "sell_yes"):
                    # tolerate ACTION-style
                    act = (row.get("action") or "").upper()
                    if act == "BUY_YES":
                        side = "buy_yes"
                    elif act == "SELL_YES":
                        side = "sell_yes"
                    else:
                        continue
                fill = Fill(
                    side=side,
                    price=float(row["price"]),
                    size=float(row["size"]),
                    fee=0.0,
                    rebate=0.0,
                )
                mid_at = float(row.get("mid_at_fill") or row["price"])
                ts_at = int(float(row.get("ts") or 0))
                self.cycle = int(float(row.get("cycle") or self.cycle or 0))
                self._apply_fill(row["market_id"], fill, mid_at, ts_at)
                n += 1
                last_cycle = max(last_cycle, self.cycle)
        self.fills_csv = saved_fills
        if saved_fills and Path(saved_fills).exists():
            self._fills_header_written = True
        if self.equity_csv and Path(self.equity_csv).exists():
            self._equity_header_written = True

        snap_path = Path("results/paper/session_snapshot.json")
        st: dict[str, Any] = {}
        if snap_path.exists():
            try:
                st = json.loads(snap_path.read_text())
            except Exception:
                st = {}
        if (not st) and status_path and Path(status_path).exists():
            try:
                cand = json.loads(Path(status_path).read_text())
                # Ignore incomplete stop stubs (no reward / wiped equity)
                if cand.get("reward_pnl_est") is not None or cand.get("n_fills"):
                    st = cand
            except Exception:
                pass
        if st:
            if st.get("reward_pnl_est") is not None:
                self.reward_pnl_est = float(st["reward_pnl_est"])
                # Seed flushed rewards so equity math / status do not wipe the estimate
                if float(st["reward_pnl_est"]) > 0 and self.port.rewards_earned <= 0:
                    self.port.rewards_earned = float(st["reward_pnl_est"])
            if st.get("cycle") is not None:
                last_cycle = max(last_cycle, int(st["cycle"]))
            if st.get("cash") is not None:
                self.port.cash = float(st["cash"])
        self.cycle = last_cycle
        if started_at is not None:
            self.started_at = float(started_at)
        # n_fills already counted in _apply_fill
        # Seed last_mids so orphaned holdings keep a mark after rediscovery gaps
        if path.exists():
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        self.last_mids[row["market_id"]] = float(row["mid_at_fill"])
                    except Exception:
                        continue
        if isinstance(st, dict) and st.get("last_mids"):
            for k, v in dict(st["last_mids"]).items():
                try:
                    self.last_mids[str(k)] = float(v)
                except Exception:
                    continue
        info = {
            "resumed": True,
            "n_fills": self.n_fills,
            "cash": round(self.port.cash, 4),
            "cycle": self.cycle,
            "reward_pnl_est": round(self.reward_pnl_est, 4),
            "n_inv_markets": sum(
                1
                for iv in self.port.inventory.values()
                if abs(iv.yes) > 1e-9 or abs(iv.no) > 1e-9
            ),
            "portfolio_abs_inv": round(
                sum(abs(iv.yes - iv.no) for iv in self.port.inventory.values()), 2
            ),
            "n_last_mids": len(self.last_mids),
        }
        return info


    def _competition_q(self, meta: dict) -> float:
        if meta.get("competition_q") is not None:
            return float(meta["competition_q"])
        return max(
            float(self.cfg["competition_q_floor"]),
            float(self.cfg["competition_q_mult"]) * float(meta.get("rewards_min_size", 50)),
        )

    def _light_adverse_boost(self, market_id: str, side: str) -> float:
        """Boost fill size slightly when recent mid move favors the aggressor."""
        strength = float(self.cfg.get("adverse_mid_cross_strength") or 0.0)
        if strength <= 0:
            return 1.0
        d = float(self.rest.last_mid_delta.get(market_id) or 0.0)
        # buy_yes (bid hit) is adverse if mid continues down; sell_yes if mid continues up
        if side == "buy_yes":
            signal = max(0.0, -d)
        else:
            signal = max(0.0, d)
        # scale: 1 + strength * |Δmid|  (capped)
        return min(2.0, 1.0 + strength * signal)

    def _apply_fill(self, market_id: str, fill, mid_at: float, ts_at: int) -> dict:
        inv = self.port.inv(market_id)
        inv_yes_before = float(inv.yes)
        inv_no_before = float(inv.no)
        cash_before = float(self.port.cash)

        if fill.side == "buy_yes":
            cost = fill.size * fill.price
            self.port.cash -= cost
            inv.yes += fill.size
            inv.yes_cost += cost
        elif fill.side == "sell_yes":
            proceeds = fill.size * fill.price
            self.port.cash += proceeds
            if inv.yes >= fill.size:
                inv.yes -= fill.size
            else:
                short = fill.size - max(inv.yes, 0.0)
                inv.yes = 0.0
                no_price = 1.0 - fill.price
                no_cost = short * no_price
                self.port.cash -= no_cost
                inv.no += short
                inv.no_cost += no_cost
        if fill.fee:
            self.port.apply_fee(fill.fee)
        if fill.rebate:
            self.port.apply_rebate(fill.rebate)

        self.n_fills += 1
        meta = self.markets.get(market_id, {})
        row = {
            "ts": ts_at,
            "iso_time": datetime.fromtimestamp(ts_at, tz=timezone.utc).isoformat(),
            "market_id": market_id,
            "question": (meta.get("question") or "")[:120],
            "side": fill.side,
            "action": "BUY_YES" if fill.side == "buy_yes" else "SELL_YES",
            "price": float(fill.price),
            "size": float(fill.size),
            "notional": float(fill.size) * float(fill.price),
            "mid_at_fill": float(mid_at),
            "inv_yes_before": inv_yes_before,
            "inv_no_before": inv_no_before,
            "inv_yes_after": float(inv.yes),
            "inv_no_after": float(inv.no),
            "cash_before": cash_before,
            "cash_after": float(self.port.cash),
            "cycle": self.cycle,
        }
        self._append_fill(row)
        return row

    def _append_fill(self, row: dict) -> None:
        if not self.fills_csv:
            return
        write_header = not self._fills_header_written or not self.fills_csv.exists()
        with open(self.fills_csv, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                w.writeheader()
                self._fills_header_written = True
            w.writerow(row)

    def _append_equity(self, row: dict) -> None:
        if not self.equity_csv:
            return
        write_header = not self._equity_header_written or not self.equity_csv.exists()
        with open(self.equity_csv, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                w.writeheader()
                self._equity_header_written = True
            w.writerow(row)

    def _flush_day_rewards_if_needed(self, day: str, ts_i: int) -> None:
        if self._current_day is None:
            self._current_day = day
            return
        if day == self._current_day:
            return
        amt = self._daily_reward_acc.pop(self._current_day, 0.0)
        if amt >= float(self.cfg["min_daily_payout"]):
            self.port.apply_reward(amt)
        self._current_day = day

    def process_cycle(self, snapshots: dict[str, dict[str, Any]], ts: float | None = None) -> dict:
        """
        One poll cycle.
        snapshots: market_id -> {mid, best_bid, best_ask, ok}
        """
        self.cycle += 1
        ts_i = int(ts if ts is not None else time.time())
        day = datetime.fromtimestamp(ts_i, tz=timezone.utc).strftime("%Y-%m-%d")
        self._flush_day_rewards_if_needed(day, ts_i)

        quote_latency = max(int(self.cfg.get("quote_latency_rows") or 0), 0)
        max_fill_frac = float(self.cfg.get("max_fill_frac", 0.40))
        port_cap = float(self.cfg.get("portfolio_inv_cap") or 0.0)
        tick = float(self.cfg.get("tick", 0.01))

        n_quoted = 0
        n_book_ok = 0
        fill_rows: list[dict] = []

        portfolio_abs_inv = sum(abs(iv.yes - iv.no) for iv in self.port.inventory.values())

        for market_id, snap in snapshots.items():
            meta = self.markets.get(market_id)
            if meta is None:
                continue
            if not snap.get("ok") or snap.get("mid") is None:
                continue
            mid = float(snap["mid"])
            if not (0.0 < mid < 1.0):
                continue
            n_book_ok += 1
            self.last_mids[market_id] = mid

            # Activate pending quotes (1-cycle latency)
            if market_id in self.rest.pending_quotes:
                pq, left = self.rest.pending_quotes[market_id]
                left -= 1
                if left <= 0:
                    self.rest.open_quotes[market_id] = pq
                    del self.rest.pending_quotes[market_id]
                else:
                    self.rest.pending_quotes[market_id] = (pq, left)

            # Track mid delta for light adverse
            if market_id in self.rest.prev_mid:
                self.rest.last_mid_delta[market_id] = mid - self.rest.prev_mid[market_id]

            inv = self.port.inv(market_id)
            oq = self.rest.open_quotes.get(market_id)

            # 1) Fills vs resting quotes when mid path crosses
            if oq is not None and market_id in self.rest.prev_mid:
                pm = self.rest.prev_mid[market_id]
                bp, ap, bs, a_s = oq.bid_price, oq.ask_price, oq.bid_size, oq.ask_size
                adv_b = self._light_adverse_boost(market_id, "buy_yes")
                adv_a = self._light_adverse_boost(market_id, "sell_yes")
                for fill in fills_from_mid_path(
                    OpenQuote(bp, None, bs, 0.0),
                    pm,
                    mid,
                    max_fill_frac=max_fill_frac,
                    adverse_boost=adv_b,
                ):
                    fill_rows.append(self._apply_fill(market_id, fill, mid, ts_i))
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
                    fill_rows.append(self._apply_fill(market_id, fill, mid, ts_i))
                    a_s = max(0.0, a_s - fill.size)
                    if a_s <= 1e-12:
                        ap, a_s = None, 0.0
                self.rest.open_quotes[market_id] = OpenQuote(
                    bp, ap, bs if bp is not None else 0.0, a_s if ap is not None else 0.0
                )

            portfolio_abs_inv = sum(abs(iv.yes - iv.no) for iv in self.port.inventory.values())

            # 2) Strategy quote
            best_bid = snap.get("best_bid")
            best_ask = snap.get("best_ask")
            if best_bid is None:
                best_bid = mid - tick
            if best_ask is None:
                best_ask = mid + tick
            competition_q = self._competition_q(meta)
            state = {
                "ts": ts_i,
                "market_id": market_id,
                "mid": mid,
                "best_bid": float(best_bid),
                "best_ask": float(best_ask),
                "inv_yes": inv.yes,
                "inv_no": inv.no,
                "cash": self.port.cash,
                "capital0": self.capital0,
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

            if bid_p is not None:
                bid_p = float(bid_p)
                if bid_p <= 0 or bid_p >= mid:
                    bid_p = None
            if ask_p is not None:
                ask_p = float(ask_p)
                if ask_p >= 1 or ask_p <= mid:
                    ask_p = None
            if bid_p is not None and bid_s > 0:
                max_afford = max(0.0, self.port.cash / bid_p)
                bid_s = min(bid_s, max_afford)
                if bid_s <= 0:
                    bid_p = None
            if ask_p is not None and ask_s > 0 and inv.yes < ask_s:
                uncovered = ask_s - max(inv.yes, 0.0)
                collat = uncovered * float(ask_p)
                if collat > self.port.cash:
                    ask_s = max(inv.yes, 0.0) + max(0.0, self.port.cash / float(ask_p))
                if ask_s <= 0:
                    ask_p = None

            if port_cap > 0 and portfolio_abs_inv >= port_cap:
                net = inv.yes - inv.no
                if net >= 0:
                    bid_p, bid_s = None, 0.0
                if net <= 0:
                    ask_p, ask_s = None, 0.0

            oq_new = OpenQuote(bid_p, ask_p, bid_s, ask_s)
            if bid_p is not None or ask_p is not None:
                n_quoted += 1

            if quote_latency <= 0:
                self.rest.open_quotes[market_id] = oq_new
                self.rest.pending_quotes.pop(market_id, None)
            else:
                self.rest.pending_quotes[market_id] = (oq_new, quote_latency)

            # 3) Reward sample on resting (displayed) quote
            scored = self.rest.open_quotes.get(market_id, oq_new)
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
                competition_q,
                float(meta.get("daily_reward_pool", 0)),
                self.samples_per_day,
            )
            # Approximate fallback: tiny share when two-sided in band and our_q==0
            if sample <= 0 and scored.bid_price is not None and scored.ask_price is not None:
                half = max(mid - float(scored.bid_price), float(scored.ask_price) - mid)
                vmax = float(meta.get("rewards_max_spread", 3.5)) / 100.0
                if half <= vmax and scored.bid_size > 0 and scored.ask_size > 0:
                    sample = 0.0005 * float(meta.get("daily_reward_pool", 0)) / self.samples_per_day
            self._daily_reward_acc[day] = self._daily_reward_acc.get(day, 0.0) + sample
            self.reward_pnl_est += sample

            self.rest.prev_mid[market_id] = mid

        self.last_book_ok = n_book_ok
        self.last_n_quoted = n_quoted

        equity = self.port.mark_to_market(self.last_mids)
        trading_mtm = equity - self.capital0 - self.port.rewards_earned
        # rewards_earned only flushed on day boundary; include pending day buffer in est
        pending_day = self._daily_reward_acc.get(day, 0.0)
        reward_est = float(self.port.rewards_earned) + pending_day
        net_pnl = equity - self.capital0

        status = {
            "ts": ts_i,
            "iso_time": datetime.fromtimestamp(ts_i, tz=timezone.utc).isoformat(),
            "equity": round(equity, 4),
            "cash": round(self.port.cash, 4),
            "net_pnl": round(net_pnl, 4),
            "reward_pnl_est": round(reward_est, 4),
            "trading_mtm": round(trading_mtm, 4),
            "n_fills": self.n_fills,
            "n_fills_cycle": len(fill_rows),
            "n_markets": len(self.markets),
            "n_markets_book_ok": n_book_ok,
            "n_markets_quoted": n_quoted,
            "top_positions": self._top_positions(8),
            "champion": self.champion,
            "uptime_sec": round(time.time() - self.started_at, 1),
            "cycle": self.cycle,
            "capital0": self.capital0,
            "paper": True,
            "real_orders": False,
        }
        self._append_equity(
            {
                "ts": ts_i,
                "iso_time": status["iso_time"],
                "equity": status["equity"],
                "cash": status["cash"],
                "net_pnl": status["net_pnl"],
                "reward_pnl_est": status["reward_pnl_est"],
                "n_fills": self.n_fills,
                "n_markets_quoted": n_quoted,
            }
        )
        return status

    def _top_positions(self, n: int = 8) -> list[dict]:
        rows = []
        for mid_id, inv in self.port.inventory.items():
            net = inv.yes - inv.no
            if abs(net) < 1e-9 and inv.yes < 1e-9 and inv.no < 1e-9:
                continue
            m = self.last_mids.get(mid_id)
            q = (self.markets.get(mid_id) or {}).get("question") or ""
            rows.append(
                {
                    "market_id": mid_id,
                    "question": str(q)[:60],
                    "yes": round(inv.yes, 3),
                    "no": round(inv.no, 3),
                    "net": round(net, 3),
                    "mid": None if m is None else round(float(m), 4),
                }
            )
        rows.sort(key=lambda r: -abs(r["net"]))
        return rows[:n]

    def write_status(self, path: Path, status: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2))
