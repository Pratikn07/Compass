from __future__ import annotations

from typing import Literal

from compass.research.edge.models import OptionPnl

Direction = Literal["UP", "DOWN", "NONE"]


def simulate_option_pnl(
    *,
    direction: Direction,
    strike: float,
    entry_premium: float,
    post_report_close: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    if direction == "NONE" or entry_premium <= 0 or strike <= 0:
        return None
    intrinsic = (
        max(0.0, post_report_close - strike)
        if direction == "UP"
        else max(0.0, strike - post_report_close)
    )
    cost_haircut = entry_premium * cost_haircut_pct
    net_pnl = max(intrinsic - entry_premium - cost_haircut, -entry_premium)
    return OptionPnl(
        entry_premium=entry_premium,
        exit_value=intrinsic,
        cost_haircut=cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / entry_premium) * 100.0,
    )


def simulate_vol_ramp_pnl(
    *,
    entry_premium: float,
    exit_value: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    if entry_premium <= 0 or exit_value <= 0:
        return None
    buy_cost = entry_premium * (1 + cost_haircut_pct)
    sell_proceeds = exit_value * (1 - cost_haircut_pct)
    cost_haircut = (entry_premium + exit_value) * cost_haircut_pct
    net_pnl = max(sell_proceeds - buy_cost, -entry_premium)
    return OptionPnl(
        entry_premium=entry_premium,
        exit_value=exit_value,
        cost_haircut=cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / entry_premium) * 100.0,
    )


def simulate_capped_short_straddle_pnl(
    *,
    straddle_price: float,
    strike: float,
    underlying_price: float,
    post_report_close: float,
    risk_width: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    del underlying_price
    if straddle_price <= 0 or strike <= 0 or risk_width <= 0:
        return None
    credit = straddle_price
    wing_cost = credit * min(1.0, straddle_price / (2.0 * risk_width))
    payout = abs(post_report_close - strike)
    spread_cost = credit * cost_haircut_pct
    net_pnl = max(credit - wing_cost - payout - spread_cost, -risk_width)
    return OptionPnl(
        entry_premium=credit,
        exit_value=payout,
        cost_haircut=wing_cost + spread_cost,
        net_pnl=net_pnl,
        return_pct=(net_pnl / risk_width) * 100.0,
    )
