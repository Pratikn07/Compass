from __future__ import annotations

from typing import Literal

from prescient.edge.models import OptionPnl

Direction = Literal["UP", "DOWN", "NONE"]


def simulate_option_pnl(
    *,
    direction: Direction,
    strike: float,
    entry_premium: float,
    post_report_close: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    """Hypothetical single ATM option buy, pessimistic: extrinsic value fully
    crushed post-report (exit = intrinsic only), plus a cost/spread haircut.

    Returns None when there is no trade (direction NONE) or inputs are invalid.
    Loss is floored at -100% of premium (you cannot lose more than you paid).
    """
    if direction == "NONE":
        return None
    if entry_premium <= 0 or strike <= 0:
        return None

    if direction == "UP":
        intrinsic = max(0.0, post_report_close - strike)
    else:  # DOWN
        intrinsic = max(0.0, strike - post_report_close)

    cost_haircut = entry_premium * cost_haircut_pct
    net_pnl = intrinsic - entry_premium - cost_haircut
    # floor at -100% of premium
    if net_pnl < -entry_premium:
        net_pnl = -entry_premium
    return OptionPnl(
        entry_premium=entry_premium,
        exit_value=intrinsic,
        cost_haircut=cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / entry_premium) * 100.0,
    )
