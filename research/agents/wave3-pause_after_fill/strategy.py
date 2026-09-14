"""
Defensive v2 Polymarket LP market-making strategy (EDITABLE by autoresearch).

Root-cause response: continuous backtests lose money because trading/inventory
losses exceed LP rewards (adverse selection / multi-day inventory bleed).
This baseline prioritizes inventory control and fill avoidance over reward chase.
"""

from __future__ import annotations


# Optional market subsets for axis experiments (default: None = use pool allowlist only)
TOP5_REWARD_MARKETS = frozenset({
    "0x8a42bb4cb9b9f157b539611f6a8c122388f652570cfc3c07d538e7df2bb78894",
    "0x58d5cc2bf06a3289b127049239aee051f3b941f219efebbca02d3f50f0eb2a64",
    "0xa3b36b2d6104d34af4e6c6215fc818e43352e78a748fbfb0b85e3a35f71dec9a",
    "0x876506d8b2bd7a0d3fa4fe18c024eee6e1dd81ee24c26795dadd6cfe4a7b5d0d",
    "0xa3d50cf0138c0faad988d80e35036aab97ae6d5627f539ce3ce531b555acc209",
})
SEED_FED_IRAN_MARKETS = frozenset({
    "0xa3b36b2d6104d34af4e6c6215fc818e43352e78a748fbfb0b85e3a35f71dec9a",
    "0x876506d8b2bd7a0d3fa4fe18c024eee6e1dd81ee24c26795dadd6cfe4a7b5d0d",
    "0x5db999fad322cea2914535aae5517060c3f80ad6d8c0231cde2124a434d16846",
    "0x12aa13b3da17ceae1b0a59b5d5b77121e91bb79b4bb0b52bf6543ed3f8d0953b",
    "0xdf9bf27ee5757c55b44b8b9826ddc9ec3a8809aa3278634c45edbb7fc8f1a3e3",
    "0x377e7fe65cf198a7fc4fdae3f2136b74729279267858daaf96718b23bc2a5607",
    "0x059db22dae2d735516017d47d1def0ea43e5d7221259c3aaa60c090d32566d4e",
    "0xd4e77ba6f29fc093509d24f508631abd445ecf506bbdc9c4c80e60256a318527",
    "0x094772b3529f455e881a4483eaf1c24266384f55e97c23f24f638f5726ba9920",
})


class Strategy:
    """Defensive quoting with tight inventory, mid-move cancel, and add-side pause."""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        # Half-spread as fraction of rewards_max_spread band (higher = wider = harder to hit)
        self.spread_frac = float(cfg.get("spread_frac", 0.6676))
        # Inventory skew strength (price shift per share of net YES exposure) — stronger
        self.skew_bps_per_share = float(cfg.get("skew_bps_per_share", 0.35))
        # Target quote size as multiple of min_size — close to min
        self.size_mult = float(cfg.get("size_mult", 1.291))
        # Hard inventory cap (shares of YES-equivalent net) — much tighter than v1 (~800)
        self.max_abs_inv = float(cfg.get("max_abs_inv", 100.0))
        # Soft inventory cap — much tighter than v1 (~349)
        self.inv_soft_cap = float(cfg.get("inv_soft_cap", 35.0))
        # Minimum half-spread in price
        self.min_half_spread = float(cfg.get("min_half_spread", 0.015))
        # If mid moves more than this (cents) since last quote → cancel / widen
        self.mid_move_cancel_cents = float(cfg.get("mid_move_cancel_cents", 2.0))
        # Extra widen multiplier when mid moved but below hard-cancel
        self.mid_move_widen_mult = float(cfg.get("mid_move_widen_mult", 1.6))
        # After inventory grows, pause adding side for this many quote ticks
        self.inv_pause_ticks = int(cfg.get("inv_pause_ticks", 24))
        # Optional allowlist: only quote if daily_reward_pool >= threshold
        self.min_daily_reward_pool = float(cfg.get("min_daily_reward_pool", 100.0))
        self.enforce_pool_allowlist = bool(cfg.get("enforce_pool_allowlist", True))
        # Low-pool size haircut when allowlist not enforced
        self.low_pool_size_frac = float(cfg.get("low_pool_size_frac", 0.6424586683313698))
        # Extreme mid tails — skip or tiny two-sided only
        self.tail_lo = float(cfg.get("tail_lo", 0.08))
        self.tail_hi = float(cfg.get("tail_hi", 0.92))
        self.skip_extreme_tails = bool(cfg.get("skip_extreme_tails", True))
        # Skip all quoting if cash below this fraction of capital0
        self.cash_unsafe_frac = float(cfg.get("cash_unsafe_frac", 0.12))
        # Hard cancel mid-move (cents) — cancel both sides entirely
        self.mid_move_hard_cancel_cents = float(
            cfg.get("mid_move_hard_cancel_cents", 4.0)
        )
        # cancel_move in price units (alias); if provided, overrides soft cancel cents
        if "cancel_move" in cfg:
            self.cancel_move = float(cfg["cancel_move"])
            self.mid_move_cancel_cents = self.cancel_move * 100.0
        else:
            self.cancel_move = self.mid_move_cancel_cents / 100.0
        # Near-mid size shrink: when half-spread distance < near_mid_dist, multiply size
        # Default 1.0 = off (champion parity under optimistic sim)
        self.near_mid_dist = float(cfg.get("near_mid_dist", 0.02))
        self.near_mid_size_mult = float(cfg.get("near_mid_size_mult", 1.0))
        # Portfolio-level inventory cap (shares); 0 = off (engine may also enforce)
        self.portfolio_inv_cap = float(cfg.get("portfolio_inv_cap", 0.0))

        # Axis hooks (defaults preserve defensive_v2 behavior)
        # market_allowlist_mode: None | "top5" | "fed_iran"
        self.market_allowlist_mode = cfg.get("market_allowlist_mode", None)
        if self.market_allowlist_mode == "top5":
            self._market_allowlist = set(TOP5_REWARD_MARKETS)
        elif self.market_allowlist_mode == "fed_iran":
            self._market_allowlist = set(SEED_FED_IRAN_MARKETS)
        else:
            self._market_allowlist = None
        self.min_edge_vs_bbo = float(cfg.get("min_edge_vs_bbo", 0.0))
        self.vol_filter = float(cfg.get("vol_filter", 0.0))  # price units; 0=off
        self.vol_lookback = int(cfg.get("vol_lookback", 5))
        self.two_sided_strict = bool(cfg.get("two_sided_strict", False))
        self.pull_size_mult = float(cfg.get("pull_size_mult", 0.5))
        self._mid_hist: dict[str, list[float]] = {}

        # Per-market internal state (strategy-only; engine provides no hooks)
        self._last_mid: dict[str, float] = {}
        self._last_net: dict[str, float] = {}
        self._add_pause_left: dict[str, int] = {}  # remaining ticks to pause add side
        self._pause_side: dict[str, str] = {}  # "bid" | "ask" | ""

    def quote(self, state: dict) -> dict:
        mid = float(state["mid"])
        min_size = float(state["rewards_min_size"])
        max_spread_cents = float(state["rewards_max_spread"])
        inv_yes = float(state["inv_yes"])
        inv_no = float(state["inv_no"])
        cash = float(state["cash"])
        capital0 = float(state.get("capital0") or 10_000.0)
        market_id = str(state.get("market_id") or "_")
        daily_pool = float(state.get("daily_reward_pool") or 0.0)

        empty = {
            "bid_price": None,
            "ask_price": None,
            "bid_size": 0.0,
            "ask_size": 0.0,
        }


        # Explicit market subset (axis: top5 / fed_iran)
        if self._market_allowlist is not None and market_id not in self._market_allowlist:
            self._update_state(market_id, mid, inv_yes - inv_no)
            return empty

        # Vol regime filter (axis)
        hist = self._mid_hist.setdefault(market_id, [])
        hist.append(mid)
        if len(hist) > max(self.vol_lookback + 2, 8):
            del hist[: len(hist) - (self.vol_lookback + 2)]
        if self.vol_filter > 0 and len(hist) > self.vol_lookback:
            if abs(hist[-1] - hist[-1 - self.vol_lookback]) >= self.vol_filter:
                self._update_state(market_id, mid, inv_yes - inv_no)
                return empty

        # Cash / inventory unsafe → stand down
        if cash < capital0 * self.cash_unsafe_frac:
            self._update_state(market_id, mid, inv_yes - inv_no)
            return empty

        # Optional pool allowlist
        if self.enforce_pool_allowlist and daily_pool < self.min_daily_reward_pool:
            self._update_state(market_id, mid, inv_yes - inv_no)
            return empty

        # Extreme tails: skip entirely (v1 forced tiny two-sided which still got picked off)
        in_tail = mid < self.tail_lo or mid > self.tail_hi
        if in_tail and self.skip_extreme_tails:
            net = inv_yes - inv_no
            # Only quote if we need to flatten and both sides stay tiny
            if abs(net) < self.inv_soft_cap * 0.5:
                self._update_state(market_id, mid, net)
                return empty

        net = inv_yes - inv_no

        # Mid-move cancel / widen
        last_mid = self._last_mid.get(market_id)
        move_cents = 0.0 if last_mid is None else abs(mid - last_mid) * 100.0
        hard_cancel = move_cents >= self.mid_move_hard_cancel_cents
        soft_widen = move_cents >= self.mid_move_cancel_cents

        if hard_cancel:
            self._update_state(market_id, mid, net)
            return empty

        # Detect inventory growth → pause adding side
        prev_net = self._last_net.get(market_id)
        if prev_net is not None:
            grew_long = net > prev_net + 1e-9 and net > 0
            grew_short = net < prev_net - 1e-9 and net < 0
            if grew_long:
                self._add_pause_left[market_id] = self.inv_pause_ticks
                self._pause_side[market_id] = "bid"
            elif grew_short:
                self._add_pause_left[market_id] = self.inv_pause_ticks
                self._pause_side[market_id] = "ask"

        pause_left = int(self._add_pause_left.get(market_id, 0))
        pause_side = self._pause_side.get(market_id, "")

        # Half-spread inside the reward-eligible band
        max_half = (max_spread_cents / 100.0) * 0.95
        half = max(self.min_half_spread, max_half * self.spread_frac)
        if soft_widen:
            half = min(max_half, half * self.mid_move_widen_mult)
        # Near hard inventory, quote even wider
        if abs(net) >= self.inv_soft_cap:
            half = min(max_half, half * 1.25)

        # Stronger inventory skew: long YES -> lower quotes (encourage selling)
        skew = (self.skew_bps_per_share * net) / 10_000.0
        skew = max(-half * 0.9, min(half * 0.9, skew))

        bid = mid - half - skew
        ask = mid + half - skew

        bid = max(0.01, min(0.99, round(bid, 2)))
        ask = max(0.01, min(0.99, round(ask, 2)))
        if bid >= mid:
            bid = max(0.01, round(mid - self.min_half_spread, 2))
        if ask <= mid:
            ask = min(0.99, round(mid + self.min_half_spread, 2))

        if self.min_edge_vs_bbo > 0:
            best_bid = float(state.get("best_bid") or (mid - 0.01))
            best_ask = float(state.get("best_ask") or (mid + 0.01))
            bid = min(bid, round(best_bid - self.min_edge_vs_bbo, 2))
            ask = max(ask, round(best_ask + self.min_edge_vs_bbo, 2))
            if bid >= mid:
                bid = max(0.01, round(mid - self.min_half_spread, 2))
            if ask <= mid:
                ask = min(0.99, round(mid + self.min_half_spread, 2))

        size = max(min_size, min_size * self.size_mult)
        # Prefer smaller size on low reward pools
        if daily_pool < self.min_daily_reward_pool:
            size = max(min_size, size * self.low_pool_size_frac)
        # In tails (if we quote), keep tiny
        if in_tail:
            size = min_size
        # Near-mid size shrink (live bot defense against adverse selection at touch)
        if self.near_mid_size_mult < 1.0 - 1e-12 and half <= self.near_mid_dist:
            size = max(min_size * 0.5, size * self.near_mid_size_mult)

        bid_price: float | None = bid
        ask_price: float | None = ask
        bid_size = size
        ask_size = size

        # Soft inventory control: kill / shrink the adding side
        if net >= self.inv_soft_cap:
            bid_price = None
            bid_size = 0.0
            ask_size = size  # reduce, don't enlarge (v1 enlarged exit side)
        elif net <= -self.inv_soft_cap:
            ask_price = None
            ask_size = 0.0
            bid_size = size

        # Pause adding side after inventory growth
        if pause_left > 0:
            if pause_side == "bid":
                bid_price, bid_size = None, 0.0
                ask_size = max(min_size * 0.5, ask_size * self.pull_size_mult)
            elif pause_side == "ask":
                ask_price, ask_size = None, 0.0
                bid_size = max(min_size * 0.5, bid_size * self.pull_size_mult)
            self._add_pause_left[market_id] = pause_left - 1

        if abs(net) >= self.max_abs_inv:
            # Flatten mode: only quote the reducing side
            if net > 0:
                bid_price, bid_size = None, 0.0
            else:
                ask_price, ask_size = None, 0.0

        # Portfolio-level inventory cap (strategy soft guard; engine may hard-enforce)
        port_abs = float(state.get("portfolio_abs_inv") or 0.0)
        port_cap = self.portfolio_inv_cap
        if port_cap <= 0:
            port_cap = float(state.get("portfolio_inv_cap") or 0.0)
        if port_cap > 0 and port_abs >= port_cap:
            if net >= 0:
                bid_price, bid_size = None, 0.0
            if net <= 0:
                ask_price, ask_size = None, 0.0

        # Don't bid if we can't afford even min_size
        if bid_price is not None and cash < bid_price * min_size:
            bid_price, bid_size = None, 0.0

        # In extreme tails with inventory: allow only tiny reducing-side / tiny two-sided
        if in_tail and not self.skip_extreme_tails:
            half_t = max(self.min_half_spread, max_half * 0.9)
            if bid_price is not None:
                bid_price = max(0.01, round(mid - half_t, 2))
                bid_size = min_size
            if ask_price is not None:
                ask_price = min(0.99, round(mid + half_t, 2))
                ask_size = min_size


        if self.two_sided_strict:
            if bid_price is None or ask_price is None:
                if abs(net) < self.max_abs_inv and cash >= (mid - half) * min_size:
                    bid_price = max(0.01, round(mid - half, 2))
                    ask_price = min(0.99, round(mid + half, 2))
                    bid_size = ask_size = min_size
                else:
                    self._update_state(market_id, mid, net)
                    return empty

        self._update_state(market_id, mid, net)

        return {
            "bid_price": bid_price,
            "ask_price": ask_price,
            "bid_size": float(bid_size),
            "ask_size": float(ask_size),
        }

    def _update_state(self, market_id: str, mid: float, net: float) -> None:
        self._last_mid[market_id] = mid
        self._last_net[market_id] = net
