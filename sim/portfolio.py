"""Portfolio state: cash + YES/NO inventory per market."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketInventory:
    yes: float = 0.0
    no: float = 0.0
    # average costs for diagnostics
    yes_cost: float = 0.0
    no_cost: float = 0.0


@dataclass
class Portfolio:
    cash: float
    capital0: float
    inventory: dict[str, MarketInventory] = field(default_factory=dict)
    fees_paid: float = 0.0
    rebates: float = 0.0
    rewards_earned: float = 0.0
    trading_pnl_realized: float = 0.0

    def inv(self, market_id: str) -> MarketInventory:
        if market_id not in self.inventory:
            self.inventory[market_id] = MarketInventory()
        return self.inventory[market_id]

    def mark_to_market(self, mids: dict[str, float]) -> float:
        """Equity = cash + YES*mid + NO*(1-mid)."""
        eq = self.cash
        for mid_id, mid in mids.items():
            inv = self.inventory.get(mid_id)
            if not inv:
                continue
            eq += inv.yes * mid + inv.no * (1.0 - mid)
        return eq

    def apply_fee(self, fee: float) -> None:
        self.cash -= fee
        self.fees_paid += fee

    def apply_rebate(self, rebate: float) -> None:
        self.cash += rebate
        self.rebates += rebate

    def apply_reward(self, usd: float) -> None:
        if usd <= 0:
            return
        self.cash += usd
        self.rewards_earned += usd
