"""Backtest metrics."""

from __future__ import annotations

from typing import Any

import numpy as np


def max_drawdown(equity: list[float] | np.ndarray) -> tuple[float, float]:
    """Return (max_dd_usd, max_dd_pct_of_peak)."""
    if len(equity) == 0:
        return 0.0, 0.0
    eq = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = float(dd.max()) if len(dd) else 0.0
    # pct relative to starting capital handled by caller; also return vs peak
    peak_at = peak[int(dd.argmax())] if len(dd) else 1.0
    pct_peak = (max_dd / peak_at) if peak_at > 0 else 0.0
    return max_dd, float(pct_peak)


def summarize(
    equity: list[float],
    capital0: float,
    rewards: float,
    fees: float,
    rebates: float,
    n_fills: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eq0 = equity[0] if equity else capital0
    eq1 = equity[-1] if equity else capital0
    net_pnl = eq1 - capital0
    max_dd, dd_peak_pct = max_drawdown(equity)
    # Soft-reject uses DD as % of starting capital
    dd_pct_capital = (max_dd / capital0 * 100.0) if capital0 else 0.0
    out = {
        "net_pnl": round(net_pnl, 4),
        "end_equity": round(eq1, 4),
        "start_equity": round(eq0, 4),
        "max_drawdown_usd": round(max_dd, 4),
        "max_drawdown_pct": round(dd_pct_capital, 4),  # % of capital0
        "max_drawdown_pct_of_peak": round(dd_peak_pct * 100.0, 4),
        "reward_pnl": round(rewards, 4),
        "fees": round(fees, 4),
        "rebates": round(rebates, 4),
        "trading_pnl": round(net_pnl - rewards + fees - rebates, 4),
        "n_fills": int(n_fills),
        "n_equity_points": len(equity),
    }
    if extra:
        out.update(extra)
    return out
