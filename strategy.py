"""
Baseline Polymarket LP market-making strategy (EDITABLE by autoresearch).

Two-sided quotes around mid with inventory skew. Targets reward band
(max spread) while keeping sizes above rewards_min_size when affordable.
"""

from __future__ import annotations


class Strategy:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        # Half-spread as fraction of rewards_max_spread (in price units, not cents)
        self.spread_frac = float(cfg.get("spread_frac", 0.41112018249852267))
        # Inventory skew strength (price shift per share of net YES exposure)
        self.skew_bps_per_share = float(cfg.get("skew_bps_per_share", 0.028229670700551976))
        # Target quote size as multiple of min_size
        self.size_mult = float(cfg.get("size_mult", 2.7830035640301776))
        # Hard inventory cap (shares of YES-equivalent net)
        self.max_abs_inv = float(cfg.get("max_abs_inv", 800.0))
        # Stop quoting a side if inventory exceeds this
        self.inv_soft_cap = float(cfg.get("inv_soft_cap", 414.1155121066232))
        # Minimum half-spread in price
        self.min_half_spread = float(cfg.get("min_half_spread", 0.01))
        # When daily_reward_pool is large, tighten half-spread by this fraction
        self.reward_spread_boost = float(cfg.get("reward_spread_boost", 0.1319184422951412))

    def quote(self, state: dict) -> dict:
        mid = float(state["mid"])
        min_size = float(state["rewards_min_size"])
        max_spread_cents = float(state["rewards_max_spread"])
        inv_yes = float(state["inv_yes"])
        inv_no = float(state["inv_no"])
        cash = float(state["cash"])

        # Net YES exposure: long YES minus long NO (NO ≈ short YES)
        net = inv_yes - inv_no

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

        bid_price: float | None = bid
        ask_price: float | None = ask
        bid_size = size
        ask_size = size

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

        # Don't bid if we can't afford even min_size
        if bid_price is not None and cash < bid_price * min_size:
            bid_price, bid_size = None, 0.0

        # Near tails, force two-sided if possible (reward rule)
        if mid < 0.10 or mid > 0.90:
            if bid_price is None or ask_price is None:
                # restore minimal two-sided if cash allows
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
