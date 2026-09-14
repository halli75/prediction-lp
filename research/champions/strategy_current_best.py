"""Promoted creative champion: creative_wave4_ovn_e3

Fork of creative_df_max8_pool110 + WAVE4 overnight overlay {"day_flatten": true, "day_flatten_max_net": 8, "min_daily_reward_pool": 110.0, "overnight_quiet": true, "overnight_mode": "reduce_only", "overnight_end_hour": 3}.
Liveish: sample 726.73 / 30d 1703.17 / 60d 2710.25.
"""
from __future__ import annotations

from datetime import datetime, timezone


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


def _utc_date_str(ts) -> str:
    """UTC YYYY-MM-DD from unix seconds (int/float) or ISO-ish string."""
    try:
        t = float(ts)
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        s = str(ts)
        return s[:10] if len(s) >= 10 else s


def _utc_hour(ts) -> int | None:
    """UTC hour 0-23 from unix seconds, or None if unparseable."""
    try:
        t = float(ts)
        return datetime.fromtimestamp(t, tz=timezone.utc).hour
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _session_id(ts, session_hours: int) -> str | None:
    """Bucket id for session boundaries every `session_hours` UTC hours."""
    try:
        t = float(ts)
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        sh = max(1, int(session_hours))
        bucket = (dt.hour // sh) * sh
        return f"{dt.strftime('%Y-%m-%d')}:{bucket:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return None


class Strategy:
    """wave5b + creative structural inventory / selection modes."""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        # --- champion knobs (wave5b defaults) ---
        self.spread_frac = float(cfg.get("spread_frac", 0.672))
        self.skew_bps_per_share = float(cfg.get("skew_bps_per_share", 0.35))
        self.size_mult = float(cfg.get("size_mult", 1.291))
        self.max_abs_inv = float(cfg.get("max_abs_inv", 100.0))
        self.inv_soft_cap = float(cfg.get("inv_soft_cap", 35.0))
        self.min_half_spread = float(cfg.get("min_half_spread", 0.015))
        self.mid_move_cancel_cents = float(cfg.get("mid_move_cancel_cents", 2.0))
        self.mid_move_widen_mult = float(cfg.get("mid_move_widen_mult", 1.6))
        self.inv_pause_ticks = int(cfg.get("inv_pause_ticks", 24))
        self.min_daily_reward_pool = float(cfg.get("min_daily_reward_pool", 110.0))
        self.enforce_pool_allowlist = bool(cfg.get("enforce_pool_allowlist", True))
        self.low_pool_size_frac = float(cfg.get("low_pool_size_frac", 0.6424586683313698))
        self.tail_lo = float(cfg.get("tail_lo", 0.08))
        self.tail_hi = float(cfg.get("tail_hi", 0.92))
        self.skip_extreme_tails = bool(cfg.get("skip_extreme_tails", True))
        self.cash_unsafe_frac = float(cfg.get("cash_unsafe_frac", 0.12))
        self.mid_move_hard_cancel_cents = float(cfg.get("mid_move_hard_cancel_cents", 4.0))
        if "cancel_move" in cfg:
            self.cancel_move = float(cfg["cancel_move"])
            self.mid_move_cancel_cents = self.cancel_move * 100.0
        else:
            self.cancel_move = self.mid_move_cancel_cents / 100.0
        self.near_mid_dist = float(cfg.get("near_mid_dist", 0.02))
        self.near_mid_size_mult = float(cfg.get("near_mid_size_mult", 1.0))
        self.portfolio_inv_cap = float(cfg.get("portfolio_inv_cap", 0.0))

        self.market_allowlist_mode = cfg.get("market_allowlist_mode", None)
        if self.market_allowlist_mode == "top5":
            self._market_allowlist = set(TOP5_REWARD_MARKETS)
        elif self.market_allowlist_mode == "fed_iran":
            self._market_allowlist = set(SEED_FED_IRAN_MARKETS)
        else:
            self._market_allowlist = None
        self.min_edge_vs_bbo = float(cfg.get("min_edge_vs_bbo", 0.0))
        self.vol_filter = float(cfg.get("vol_filter", 0.0))
        self.vol_lookback = int(cfg.get("vol_lookback", 5))
        self.two_sided_strict = bool(cfg.get("two_sided_strict", False))
        self.pull_size_mult = float(cfg.get("pull_size_mult", 0.464))
        self._mid_hist: dict[str, list[float]] = {}

        # --- creative mode 1: force_flatten ---
        self.force_flatten = bool(cfg.get("force_flatten", False))
        self.flatten_trigger_frac = float(cfg.get("flatten_trigger_frac", 0.4))
        self.flatten_half_frac = float(cfg.get("flatten_half_frac", 0.25))
        self.flatten_size_mult = float(cfg.get("flatten_size_mult", 2.0))

        # --- creative mode 2: day_boundary_flatten ---
        self.day_flatten = bool(cfg.get("day_flatten", True)  # PROMOTED creative default)
        self.day_flatten_max_net = float(cfg.get("day_flatten_max_net", 8.0))
        self.day_flatten_global = bool(cfg.get("day_flatten_global", False))

        # --- creative mode 3: toxicity_blackout ---
        self.tox_blackout_ticks = int(cfg.get("tox_blackout_ticks", 0))  # 0 = off
        self.tox_move_cents = float(cfg.get("tox_move_cents", 1.5))
        self.tox_watch_ticks = int(cfg.get("tox_watch_ticks", 8))

        # --- creative mode 4: dynamic_top_k ---
        self.dynamic_top_k = int(cfg.get("dynamic_top_k", 0))  # 0 = off

        # --- creative mode 5: harvest_or_flatten ---
        self.harvest_mode = bool(cfg.get("harvest_mode", False))
        self.harvest_flat_max = float(cfg.get("harvest_flat_max", 2.0))
        self.harvest_flatten_half_frac = float(cfg.get("harvest_flatten_half_frac", 0.5))
        self.harvest_flatten_size_mult = float(cfg.get("harvest_flatten_size_mult", 1.5))

        # --- WAVE3 mode 6: session_flatten ---
        self.session_flatten = bool(cfg.get("session_flatten", False))
        self.session_hours = int(cfg.get("session_hours", 12))  # 12 → 00/12; 8 → 00/08/16
        self.session_flatten_max_net = float(
            cfg.get("session_flatten_max_net", cfg.get("day_flatten_max_net", 5.0))
        )

        # --- WAVE3 mode 7: inventory_age_flatten ---
        self.max_inv_age_ticks = int(cfg.get("max_inv_age_ticks", 0))  # 0 = off
        self.inv_age_flat_eps = float(cfg.get("inv_age_flat_eps", 1.0))

        # --- WAVE3 mode 8: overnight_quiet ---
        self.overnight_quiet = bool(cfg.get("overnight_quiet", True))
        self.overnight_start_hour = int(cfg.get("overnight_start_hour", 0))
        self.overnight_end_hour = int(cfg.get("overnight_end_hour", 3))  # [start, end)
        # "reduce_only" | "size_mult"
        self.overnight_mode = str(cfg.get("overnight_mode", "reduce_only"))
        self.overnight_size_mult = float(cfg.get("overnight_size_mult", 0.3))

        # --- WAVE3 mode 9: carry_budget ---
        self.carry_budget_shares = float(cfg.get("carry_budget_shares", 0.0))  # 0 = off

        # --- WAVE3 mode 10: toxic_market_day_ban ---
        self.tox_day_ban_cents = float(cfg.get("tox_day_ban_cents", 0.0))  # 0 = off
        self.tox_day_ban_flat_eps = float(cfg.get("tox_day_ban_flat_eps", 1.0))

        # --- WAVE3 mode 11: day_flatten + mild harvest gate ---
        self.day_flatten_harvest_gate = bool(cfg.get("day_flatten_harvest_gate", False))
        self.df_gate_vol = float(cfg.get("df_gate_vol", 0.015))  # require |Δmid| < this
        self.df_gate_min_pool = float(cfg.get("df_gate_min_pool", 0.0))  # 0 → use min_daily_reward_pool
        self.df_gate_vol_lookback = int(cfg.get("df_gate_vol_lookback", 5))

        # Per-market / creative internal state
        self._last_mid: dict[str, float] = {}
        self._last_net: dict[str, float] = {}
        self._add_pause_left: dict[str, int] = {}
        self._pause_side: dict[str, str] = {}

        # day flatten state
        self._day_flatten_active: dict[str, bool] = {}
        self._last_utc_day: dict[str, str] = {}
        self._global_utc_day: str | None = None
        self._global_day_flatten = False

        # toxicity blackout
        self._tox_blackout_left: dict[str, int] = {}
        self._tox_watch_left: dict[str, int] = {}
        self._tox_watch_side: dict[str, str] = {}  # "long" | "short"
        self._tox_watch_mid: dict[str, float] = {}

        # dynamic top-k: day -> {market_id: max pool seen}
        self._topk_day: str | None = None
        self._topk_pools: dict[str, float] = {}
        self._topk_set: set[str] | None = None  # None = bootstrap (allow all)

        # WAVE3 state
        self._session_flatten_active: dict[str, bool] = {}
        self._last_session_id: dict[str, str] = {}
        self._inv_age_ticks: dict[str, int] = {}
        self._tox_day_ban_day: dict[str, str] = {}  # market -> utc_day banned
        self._tox_hold_mid: dict[str, float] = {}  # mid when |net| left ~0
        self._tox_hold_side: dict[str, str] = {}  # "long"|"short"
        self._df_gate_pending: dict[str, bool] = {}  # after day-flatten clear, gate resume
        self._df_was_active: dict[str, bool] = {}

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
        ts = state.get("ts")

        empty = {
            "bid_price": None,
            "ask_price": None,
            "bid_size": 0.0,
            "ask_size": 0.0,
        }

        net = inv_yes - inv_no
        utc_day = _utc_date_str(ts) if ts is not None else None

        # --- day boundary tracking (mode 2) ---
        if self.day_flatten and utc_day is not None:
            if self.day_flatten_global:
                if self._global_utc_day is None:
                    self._global_utc_day = utc_day
                elif utc_day != self._global_utc_day:
                    self._global_utc_day = utc_day
                    self._global_day_flatten = True
                if self._global_day_flatten and abs(net) <= self.day_flatten_max_net:
                    # only clear when *this* market is flat; keep flag until we see
                    # all markets flat is hard without portfolio scan — clear per call
                    # when this market is flat; re-arm only on next day change.
                    pass
                # Per-market day flatten flag mirrors global day change
                key = market_id
                last = self._last_utc_day.get(key)
                if last is not None and last != utc_day:
                    self._day_flatten_active[key] = True
                self._last_utc_day[key] = utc_day
                if abs(net) <= self.day_flatten_max_net:
                    self._day_flatten_active[key] = False
            else:
                last = self._last_utc_day.get(market_id)
                if last is not None and last != utc_day:
                    self._day_flatten_active[market_id] = True
                self._last_utc_day[market_id] = utc_day
                if abs(net) <= self.day_flatten_max_net:
                    self._day_flatten_active[market_id] = False

        in_day_flatten = bool(
            self.day_flatten and self._day_flatten_active.get(market_id, False)
        )

        # Track day-flatten clear → harvest gate pending (mode 11)
        if self.day_flatten_harvest_gate and self.day_flatten:
            was = bool(self._df_was_active.get(market_id, False))
            if was and not in_day_flatten:
                self._df_gate_pending[market_id] = True
            self._df_was_active[market_id] = in_day_flatten

        utc_hr = _utc_hour(ts) if ts is not None else None
        in_df_gate = False

        # --- WAVE3 session_flatten (mode 6) ---
        in_session_flatten = False
        if self.session_flatten and ts is not None:
            sid = _session_id(ts, self.session_hours)
            if sid is not None:
                last_sid = self._last_session_id.get(market_id)
                if last_sid is not None and last_sid != sid:
                    self._session_flatten_active[market_id] = True
                self._last_session_id[market_id] = sid
                if abs(net) <= self.session_flatten_max_net:
                    self._session_flatten_active[market_id] = False
            in_session_flatten = bool(self._session_flatten_active.get(market_id, False))

        # --- WAVE3 inventory_age_flatten (mode 7) ---
        in_age_flatten = False
        if self.max_inv_age_ticks > 0:
            if abs(net) <= self.inv_age_flat_eps:
                self._inv_age_ticks[market_id] = 0
            else:
                self._inv_age_ticks[market_id] = int(self._inv_age_ticks.get(market_id, 0)) + 1
            if self._inv_age_ticks.get(market_id, 0) > self.max_inv_age_ticks:
                in_age_flatten = True

        # --- WAVE3 overnight_quiet (mode 8) ---
        in_overnight = False
        if self.overnight_quiet and utc_hr is not None:
            lo = self.overnight_start_hour
            hi = self.overnight_end_hour
            if lo <= hi:
                in_overnight = lo <= utc_hr < hi
            else:
                # wraps midnight e.g. 22..6
                in_overnight = utc_hr >= lo or utc_hr < hi

        # --- WAVE3 carry_budget (mode 9) ---
        port_abs = float(state.get("portfolio_abs_inv") or 0.0)
        in_carry_budget = bool(
            self.carry_budget_shares > 0 and port_abs > self.carry_budget_shares
        )

        # --- WAVE3 toxic_market_day_ban (mode 10) ---
        banned_today = False
        if self.tox_day_ban_cents > 0 and utc_day is not None:
            ban_day = self._tox_day_ban_day.get(market_id)
            if ban_day == utc_day:
                banned_today = True
            else:
                # track hold mid when leaving flat
                prev_net = self._last_net.get(market_id)
                if abs(net) > self.tox_day_ban_flat_eps:
                    if market_id not in self._tox_hold_mid or (
                        prev_net is not None and abs(prev_net) <= self.tox_day_ban_flat_eps
                    ):
                        self._tox_hold_mid[market_id] = mid
                        self._tox_hold_side[market_id] = "long" if net > 0 else "short"
                    hmid = self._tox_hold_mid.get(market_id, mid)
                    hside = self._tox_hold_side.get(market_id, "long" if net > 0 else "short")
                    adverse = False
                    if hside == "long" and (hmid - mid) * 100.0 >= self.tox_day_ban_cents:
                        adverse = True
                    elif hside == "short" and (mid - hmid) * 100.0 >= self.tox_day_ban_cents:
                        adverse = True
                    if adverse:
                        self._tox_day_ban_day[market_id] = utc_day
                        banned_today = True
                else:
                    self._tox_hold_mid.pop(market_id, None)
                    self._tox_hold_side.pop(market_id, None)

        # If banned and flat → stand down; if banned and holding → reduce-only via flag
        if banned_today and abs(net) < 1e-9:
            self._update_state(market_id, mid, net)
            return empty

        # --- dynamic top-k (mode 4) ---
        if self.dynamic_top_k > 0 and utc_day is not None:
            if self._topk_day != utc_day:
                self._topk_day = utc_day
                self._topk_pools = {}
                self._topk_set = None  # bootstrap until K known
            if daily_pool > 0:
                prev = self._topk_pools.get(market_id, 0.0)
                if daily_pool > prev:
                    self._topk_pools[market_id] = daily_pool
                if len(self._topk_pools) >= self.dynamic_top_k:
                    ranked = sorted(
                        self._topk_pools.items(), key=lambda kv: kv[1], reverse=True
                    )
                    self._topk_set = {m for m, _ in ranked[: self.dynamic_top_k]}
            if self._topk_set is not None and market_id not in self._topk_set:
                # still allow reduce-side if we have inventory (don't trap)
                if abs(net) < 1e-9:
                    self._update_state(market_id, mid, net)
                    return empty
                # else fall through into flatten-style reduce-only later
                in_day_flatten = True  # reuse reduce-only path loosely via force path

        # Explicit market subset
        if self._market_allowlist is not None and market_id not in self._market_allowlist:
            self._update_state(market_id, mid, net)
            return empty

        # Vol regime filter
        hist = self._mid_hist.setdefault(market_id, [])
        hist.append(mid)
        if len(hist) > max(self.vol_lookback + 2, 8):
            del hist[: len(hist) - (self.vol_lookback + 2)]
        if self.vol_filter > 0 and len(hist) > self.vol_lookback:
            if abs(hist[-1] - hist[-1 - self.vol_lookback]) >= self.vol_filter:
                self._update_state(market_id, mid, net)
                return empty

        if cash < capital0 * self.cash_unsafe_frac:
            self._update_state(market_id, mid, net)
            return empty

        if self.enforce_pool_allowlist and daily_pool < self.min_daily_reward_pool:
            self._update_state(market_id, mid, net)
            return empty

        # --- WAVE3 day_flatten harvest gate (mode 11) ---
        if self.day_flatten_harvest_gate and self._df_gate_pending.get(market_id, False):
            gate_pool = self.df_gate_min_pool if self.df_gate_min_pool > 0 else self.min_daily_reward_pool
            # vol quiet: |mid - mid[lookback]| < df_gate_vol
            hist_g = self._mid_hist.get(market_id, [])
            vol_ok = False
            if len(hist_g) > self.df_gate_vol_lookback:
                vol_ok = abs(hist_g[-1] - hist_g[-1 - self.df_gate_vol_lookback]) < self.df_gate_vol
            pool_ok = daily_pool >= gate_pool
            if vol_ok or pool_ok:
                self._df_gate_pending[market_id] = False
            else:
                in_df_gate = True  # hold reduce-only / no add until gate passes
                if abs(net) < 1e-9:
                    self._update_state(market_id, mid, net)
                    return empty

        in_tail = mid < self.tail_lo or mid > self.tail_hi
        if in_tail and self.skip_extreme_tails:
            if abs(net) < self.inv_soft_cap * 0.5:
                self._update_state(market_id, mid, net)
                return empty

        # Mid-move cancel / widen
        last_mid = self._last_mid.get(market_id)
        move_cents = 0.0 if last_mid is None else abs(mid - last_mid) * 100.0
        hard_cancel = move_cents >= self.mid_move_hard_cancel_cents
        soft_widen = move_cents >= self.mid_move_cancel_cents

        if hard_cancel:
            self._update_state(market_id, mid, net)
            return empty

        # Detect inventory growth → pause adding side + tox watch
        prev_net = self._last_net.get(market_id)
        grew_long = False
        grew_short = False
        if prev_net is not None:
            grew_long = net > prev_net + 1e-9 and net > 0
            grew_short = net < prev_net - 1e-9 and net < 0
            if grew_long:
                self._add_pause_left[market_id] = self.inv_pause_ticks
                self._pause_side[market_id] = "bid"
                if self.tox_blackout_ticks > 0:
                    self._tox_watch_left[market_id] = self.tox_watch_ticks
                    self._tox_watch_side[market_id] = "long"
                    self._tox_watch_mid[market_id] = mid
            elif grew_short:
                self._add_pause_left[market_id] = self.inv_pause_ticks
                self._pause_side[market_id] = "ask"
                if self.tox_blackout_ticks > 0:
                    self._tox_watch_left[market_id] = self.tox_watch_ticks
                    self._tox_watch_side[market_id] = "short"
                    self._tox_watch_mid[market_id] = mid

        # --- toxicity blackout (mode 3) ---
        tox_left = int(self._tox_blackout_left.get(market_id, 0))
        if tox_left > 0:
            self._tox_blackout_left[market_id] = tox_left - 1
            self._update_state(market_id, mid, net)
            return empty

        watch_left = int(self._tox_watch_left.get(market_id, 0))
        if self.tox_blackout_ticks > 0 and watch_left > 0:
            wmid = self._tox_watch_mid.get(market_id, mid)
            wside = self._tox_watch_side.get(market_id, "")
            adverse = False
            if wside == "long" and (wmid - mid) * 100.0 >= self.tox_move_cents:
                adverse = True
            elif wside == "short" and (mid - wmid) * 100.0 >= self.tox_move_cents:
                adverse = True
            if adverse:
                self._tox_blackout_left[market_id] = self.tox_blackout_ticks
                self._tox_watch_left[market_id] = 0
                self._update_state(market_id, mid, net)
                return empty
            self._tox_watch_left[market_id] = watch_left - 1

        pause_left = int(self._add_pause_left.get(market_id, 0))
        pause_side = self._pause_side.get(market_id, "")

        # Decide flatten / reduce-only regimes
        force_trig = self.inv_soft_cap * self.flatten_trigger_frac
        in_force_flatten = bool(
            self.force_flatten and abs(net) >= force_trig
        )
        in_harvest_flatten = bool(
            self.harvest_mode and abs(net) >= self.harvest_flat_max
        )
        # dynamic top-k reduce-only when excluded but holding inv
        in_topk_reduce = bool(
            self.dynamic_top_k > 0
            and self._topk_set is not None
            and market_id not in self._topk_set
            and abs(net) >= 1e-9
        )

        # overnight reduce-only path
        in_overnight_reduce = bool(
            in_overnight and self.overnight_mode == "reduce_only" and abs(net) >= 1e-9
        )
        # banned but still holding → reduce-only
        in_ban_reduce = bool(banned_today and abs(net) >= 1e-9)

        # Creative reduce-only only (hard max_abs_inv handled like champion below)
        want_reduce_only = (
            in_force_flatten
            or in_day_flatten
            or in_harvest_flatten
            or in_topk_reduce
            or in_session_flatten
            or in_age_flatten
            or in_overnight_reduce
            or in_carry_budget
            or in_ban_reduce
            or in_df_gate
        )

        # Overnight quiet: when flat, do not open new overnight risk in reduce_only mode
        if in_overnight and self.overnight_mode == "reduce_only" and abs(net) < 1e-9:
            self._update_state(market_id, mid, net)
            return empty

        # Carry budget: when portfolio over budget and this market flat, do not add
        if in_carry_budget and abs(net) < 1e-9:
            self._update_state(market_id, mid, net)
            return empty

        # Half-spread
        max_half = (max_spread_cents / 100.0) * 0.95
        half = max(self.min_half_spread, max_half * self.spread_frac)
        if soft_widen:
            half = min(max_half, half * self.mid_move_widen_mult)
        if abs(net) >= self.inv_soft_cap and not want_reduce_only:
            half = min(max_half, half * 1.25)

        # Tight flatten half when paying to exit
        tight_flatten = (
            in_force_flatten
            or in_day_flatten
            or in_topk_reduce
            or in_session_flatten
            or in_age_flatten
            or in_carry_budget
            or in_ban_reduce
        )
        if tight_flatten:
            half = max(
                self.min_half_spread * 0.5,
                max_half * self.spread_frac * self.flatten_half_frac,
            )
        elif in_harvest_flatten:
            half = max(
                self.min_half_spread * 0.5,
                max_half * self.spread_frac * self.harvest_flatten_half_frac,
            )

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
        if daily_pool < self.min_daily_reward_pool:
            size = max(min_size, size * self.low_pool_size_frac)
        if in_tail:
            size = min_size
        if self.near_mid_size_mult < 1.0 - 1e-12 and half <= self.near_mid_dist:
            size = max(min_size * 0.5, size * self.near_mid_size_mult)
        if in_overnight and self.overnight_mode == "size_mult":
            size = max(min_size * 0.5, size * self.overnight_size_mult)

        # Enlarge reduce side when force/day flattening
        reduce_size = size
        if tight_flatten:
            reduce_size = max(min_size, size * self.flatten_size_mult)
        elif in_harvest_flatten:
            reduce_size = max(min_size, size * self.harvest_flatten_size_mult)

        bid_price: float | None = bid
        ask_price: float | None = ask
        bid_size = size
        ask_size = size

        # Soft inventory control (champion)
        if net >= self.inv_soft_cap:
            bid_price = None
            bid_size = 0.0
            ask_size = size
        elif net <= -self.inv_soft_cap:
            ask_price = None
            ask_size = 0.0
            bid_size = size

        # Pause adding side after inventory growth
        if pause_left > 0 and not want_reduce_only:
            if pause_side == "bid":
                bid_price, bid_size = None, 0.0
                ask_size = max(min_size * 0.5, ask_size * self.pull_size_mult)
            elif pause_side == "ask":
                ask_price, ask_size = None, 0.0
                bid_size = max(min_size * 0.5, bid_size * self.pull_size_mult)
            self._add_pause_left[market_id] = pause_left - 1
        elif pause_left > 0:
            self._add_pause_left[market_id] = pause_left - 1

        # Hard inventory: never add past hard cap
        if abs(net) >= self.max_abs_inv:
            if net > 0:
                bid_price, bid_size = None, 0.0
            else:
                ask_price, ask_size = None, 0.0

        # Creative reduce-only regimes (still respect hard for add)
        if want_reduce_only and abs(net) >= 1e-9:
            if net > 0:
                # long YES → only ask (sell)
                bid_price, bid_size = None, 0.0
                ask_price = ask
                ask_size = reduce_size
            else:
                ask_price, ask_size = None, 0.0
                bid_price = bid
                bid_size = reduce_size

        # Portfolio-level inventory cap
        # port_abs already computed above for carry_budget
        port_cap = self.portfolio_inv_cap
        if port_cap <= 0:
            port_cap = float(state.get("portfolio_inv_cap") or 0.0)
        if port_cap > 0 and port_abs >= port_cap:
            if net >= 0:
                bid_price, bid_size = None, 0.0
            if net <= 0:
                ask_price, ask_size = None, 0.0

        if bid_price is not None and cash < bid_price * min_size:
            bid_price, bid_size = None, 0.0

        if in_tail and not self.skip_extreme_tails:
            half_t = max(self.min_half_spread, max_half * 0.9)
            if bid_price is not None:
                bid_price = max(0.01, round(mid - half_t, 2))
                bid_size = min_size
            if ask_price is not None:
                ask_price = min(0.99, round(mid + half_t, 2))
                ask_size = min_size

        if self.two_sided_strict and not want_reduce_only:
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
