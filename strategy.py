"""
Polymarket LP market-making strategy (EDITABLE by autoresearch).

Two-sided quotes around mid with inventory skew, plus continuous-book
defenses against adverse selection:
  - per-market + portfolio inventory caps
  - cancel-on-move when mid jumps through the quote
  - shrink size when quoting near mid
  - pause the adding side after a fill
"""

from __future__ import annotations


class Strategy:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        # Half-spread as fraction of rewards_max_spread (in price units, not cents)
        self.spread_frac = float(cfg.get("spread_frac", 0.30361660934315987))
        # Inventory skew strength (price shift per share of net YES exposure)
        self.skew_bps_per_share = float(cfg.get("skew_bps_per_share", 0.086961148768161))
        # Target quote size as multiple of min_size
        self.size_mult = float(cfg.get("size_mult", 4.703308838637967))
        # Hard inventory cap (shares of YES-equivalent net) per market
        self.max_abs_inv = float(cfg.get("max_abs_inv", 800.0))
        # Stop quoting a side if inventory exceeds this
        self.inv_soft_cap = float(cfg.get("inv_soft_cap", 516.4965284986445))
        # Minimum half-spread in price
        self.min_half_spread = float(cfg.get("min_half_spread", 0.01))
        # When daily_reward_pool is large, tighten half-spread by this fraction
        self.reward_spread_boost = float(cfg.get("reward_spread_boost", 0.17184274218966544))
        # Cancel both sides if |Δmid| since last bar on this market exceeds this
        self.cancel_move = float(cfg.get("cancel_move", 0.025))
        # After a fill, pause adding for this many seconds
        self.pause_secs = float(cfg.get("pause_secs", 900.0))
        # Size multiplier when half-spread is at or inside near_mid_half
        self.near_mid_size_frac = float(cfg.get("near_mid_size_frac", 0.55))
        # Half-spread (price units) at/under which size is shrunk
        self.near_mid_half = float(cfg.get("near_mid_half", 0.02))
        # Sum of |net| across markets — stop adding when breached
        self.portfolio_inv_cap = float(cfg.get("portfolio_inv_cap", 4500.0))
        # Keep this fraction of starting capital as cash (don't bid it away)
        self.cash_reserve_frac = float(cfg.get("cash_reserve_frac", 0.12))

        self._prev_mid: dict[str, float] = {}
        self._prev_inv: dict[str, tuple[float, float]] = {}
        self._pause_until: dict[str, int] = {}
        self._net: dict[str, float] = {}

    def quote(self, state: dict) -> dict:
        mid = float(state["mid"])
        min_size = float(state["rewards_min_size"])
        max_spread_cents = float(state["rewards_max_spread"])
        inv_yes = float(state["inv_yes"])
        inv_no = float(state["inv_no"])
        cash = float(state["cash"])
        capital0 = float(state.get("capital0") or 10_000.0)
        ts = int(state.get("ts") or 0)
        market_id = str(state.get("market_id") or "_")

        # Net YES exposure: long YES minus long NO (NO ≈ short YES)
        net = inv_yes - inv_no
        self._net[market_id] = net

        # Detect a fill via inventory change on this market
        prev_inv = self._prev_inv.get(market_id)
        if prev_inv is not None:
            dy = inv_yes - prev_inv[0]
            dn = inv_no - prev_inv[1]
            if abs(dy) + abs(dn) > 1e-6:
                self._pause_until[market_id] = ts + int(self.pause_secs)
        self._prev_inv[market_id] = (inv_yes, inv_no)

        prev_mid = self._prev_mid.get(market_id)
        jump = abs(mid - prev_mid) if prev_mid is not None else 0.0
        self._prev_mid[market_id] = mid

        # Half-spread inside the reward-eligible band
        max_half = (max_spread_cents / 100.0) * 0.95  # stay inside v
        half = max(self.min_half_spread, max_half * self.spread_frac)
        pool = float(state.get("daily_reward_pool") or 0.0)
        if self.reward_spread_boost > 0 and pool >= 150.0:
            # Chase richer reward pools with a tighter (still eligible) quote
            half *= max(0.55, 1.0 - self.reward_spread_boost)

        # Inventory skew: long YES -> lower quotes (encourage selling)
        skew = (self.skew_bps_per_share * net) / 10_000.0
        # clip skew so we still remain two-sided around mid
        skew = max(-half * 0.8, min(half * 0.8, skew))

        bid = mid - half - skew
        ask = mid + half - skew

        # Tick snap-ish
        bid = max(0.01, min(0.99, round(bid, 2)))
        ask = max(0.01, min(0.99, round(ask, 2)))
        if bid >= mid:
            bid = max(0.01, round(mid - self.min_half_spread, 2))
        if ask <= mid:
            ask = min(0.99, round(mid + self.min_half_spread, 2))

        size = max(min_size, min_size * self.size_mult)
        # Shrink size when the posted half-spread sits near mid (easy pick-off)
        if half <= self.near_mid_half:
            size *= max(0.25, self.near_mid_size_frac)
            size = max(min_size, size)

        bid_price: float | None = bid
        ask_price: float | None = ask
        bid_size = size
        ask_size = size

        # Cancel-on-move: mid jumped — pull both sides this bar, requote next
        if jump >= self.cancel_move:
            bid_price, bid_size = None, 0.0
            ask_price, ask_size = None, 0.0
            # A shock move also starts a pause so we do not chase the print
            if jump >= 2.0 * self.cancel_move:
                until = ts + int(self.pause_secs)
                self._pause_until[market_id] = max(self._pause_until.get(market_id, 0), until)

        # Pause after fills / shocks: only quote the reducing side
        paused = ts < self._pause_until.get(market_id, 0)
        if paused and (bid_price is not None or ask_price is not None):
            if net > 0:
                bid_price, bid_size = None, 0.0
            elif net < 0:
                ask_price, ask_size = None, 0.0
            else:
                bid_price, bid_size = None, 0.0
                ask_price, ask_size = None, 0.0

        # Soft inventory control: reduce/remove the adding side
        if net >= self.inv_soft_cap:
            bid_price = None
            bid_size = 0.0
            ask_size = size * 1.25
        elif net <= -self.inv_soft_cap:
            ask_price = None
            ask_size = 0.0
            bid_size = size * 1.25

        if abs(net) >= self.max_abs_inv:
            # flatten mode: only quote the reducing side
            if net > 0:
                bid_price, bid_size = None, 0.0
            else:
                ask_price, ask_size = None, 0.0

        # Portfolio-level cap: too much gross YES-equivalent across names
        gross = sum(abs(v) for v in self._net.values())
        if gross >= self.portfolio_inv_cap:
            if net >= 0:
                bid_price, bid_size = None, 0.0
            if net <= 0:
                ask_price, ask_size = None, 0.0

        # Cash reserve: don't bid down to zero (continuous adverse walks)
        reserve = capital0 * self.cash_reserve_frac
        if bid_price is not None and cash - reserve < bid_price * min_size:
            bid_price, bid_size = None, 0.0

        # Don't bid if we can't afford even min_size
        if bid_price is not None and cash < bid_price * min_size:
            bid_price, bid_size = None, 0.0

        # Near tails, force two-sided if possible (reward rule) — skip after a jump
        if jump < self.cancel_move and (mid < 0.10 or mid > 0.90):
            if bid_price is None or ask_price is None:
                half_t = max(self.min_half_spread, max_half * 0.6)
                if bid_price is None and cash >= (mid - half_t) * min_size:
                    bid_price = max(0.01, round(mid - half_t, 2))
                    bid_size = min_size
                if ask_price is None:
                    ask_price = min(0.99, round(mid + half_t, 2))
                    ask_size = min_size

        return {
            "bid_price": bid_price,
            "ask_price": ask_price,
            "bid_size": float(bid_size),
            "ask_size": float(ask_size),
        }
