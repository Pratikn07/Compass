"""Shared cost model (rulebook §3, deliberately pessimistic).

- 0.10% of notional per side (slippage + spread).
- Tax haircut on POSITIVE P&L only: 35% if held < 365 calendar days, 20% if
  held >= 365 days. Losses get no tax credit (pessimistic by design).
"""
from __future__ import annotations

from datetime import date

TRADING_COST_PER_SIDE = 0.001
SHORT_TERM_TAX = 0.35
LONG_TERM_TAX = 0.20
LONG_TERM_DAYS = 365


def apply_side_cost(equity: float) -> float:
    """One side (a buy or a sell) of a trade."""
    return equity * (1.0 - TRADING_COST_PER_SIDE)


def tax_rate(entry: date, exit: date) -> float:
    return LONG_TERM_TAX if (exit - entry).days >= LONG_TERM_DAYS else SHORT_TERM_TAX


def after_tax_equity(equity_at_exit: float, cost_basis: float, entry: date, exit: date) -> float:
    """Apply the tax haircut to a closed position's gain. Losses pass through
    untouched (no credit)."""
    gain = equity_at_exit - cost_basis
    if gain <= 0:
        return equity_at_exit
    return cost_basis + gain * (1.0 - tax_rate(entry, exit))


def net_trade_return(gross_return: float, entry: date, exit: date) -> float:
    """One round-trip trade: charge both sides, then tax any remaining gain.
    Used by per-trade scoring (H3)."""
    after_costs = (1.0 + gross_return) * (1.0 - TRADING_COST_PER_SIDE) ** 2 - 1.0
    if after_costs <= 0:
        return after_costs
    return after_costs * (1.0 - tax_rate(entry, exit))
