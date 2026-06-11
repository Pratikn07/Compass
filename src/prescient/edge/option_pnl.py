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


def simulate_vol_ramp_pnl(
    *,
    entry_premium: float,
    exit_value: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    """Hypothetical pre-earnings vol-ramp trade: BUY the ATM straddle ~1 week out,
    SELL the same contracts the day before the report. Never holds through the
    event, so it cannot eat IV crush and never predicts direction.

    Honesty model: the spread is crossed TWICE - buy at entry_premium*(1+h), sell
    at exit_value*(1-h). Theta is implicit in the exit value (a flat/decayed exit
    simply yields a negative return). Loss floored at -100% of premium. Returns
    None on non-positive entry premium or exit value.
    """
    if entry_premium <= 0 or exit_value <= 0:
        return None

    buy_cost = entry_premium * (1.0 + cost_haircut_pct)
    sell_proceeds = exit_value * (1.0 - cost_haircut_pct)
    cost_haircut = entry_premium * cost_haircut_pct + exit_value * cost_haircut_pct
    net_pnl = sell_proceeds - buy_cost
    if net_pnl < -entry_premium:
        net_pnl = -entry_premium
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
    """Hypothetical DEFINED-RISK short straddle (sell the ATM straddle, cap the loss
    at `risk_width` W via protective wings whose cost is modeled honestly).

    credit       = straddle_price (premium received for selling)
    wing_cost    = credit * min(1.0, straddle_price / (2 * W))  -- scales INVERSELY
                   with W (tighter cap = costlier wings), never exceeds the credit.
    payout       = |post_report_close - strike|  (what the short straddle owes)
    net          = credit - wing_cost - payout - bid/ask haircut, FLOORED at -W.
    return_pct   = net / W * 100  (return on capital-at-risk, not on premium).

    Returns None on invalid inputs (non-positive credit, strike, or W). The bid/ask
    haircut is applied to the credit (cost of getting in/out). This is the RETAIL,
    UNHEDGED, sell-and-hold version (no delta-hedging modeled). `underlying_price`
    is currently unused (reserved for a future strike-aware wing-pricing model); the
    ATM strike approximates it today."""
    if straddle_price <= 0 or strike <= 0 or risk_width <= 0:
        return None

    credit = straddle_price
    wing_cost = credit * min(1.0, straddle_price / (2.0 * risk_width))
    payout = abs(post_report_close - strike)
    cost_haircut = credit * cost_haircut_pct
    net_pnl = credit - wing_cost - payout - cost_haircut
    if net_pnl < -risk_width:
        net_pnl = -risk_width
    return OptionPnl(
        entry_premium=credit,
        exit_value=payout,
        cost_haircut=wing_cost + cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / risk_width) * 100.0,
    )
