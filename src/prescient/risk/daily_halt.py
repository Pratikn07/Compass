from __future__ import annotations

from prescient.risk.models import (
    DailyHaltDecision,
    DailyHaltReason,
    DailyHaltSettings,
    DailyHaltStatus,
    DailyRiskAction,
    DailyRiskState,
)
from prescient.journal import DecisionType
from prescient.risk.audit import risk_audit_trail


_RISK_INCREASING_ACTIONS = [
    DailyRiskAction.NEW_ENTRY,
    DailyRiskAction.ADD_TO_POSITION,
    DailyRiskAction.OPEN_OPTION_CONTRACT,
    DailyRiskAction.RISK_INCREASING_REPLACEMENT_ORDER,
]

_RISK_REDUCING_ACTIONS = [
    DailyRiskAction.EXIT_POSITION,
    DailyRiskAction.REDUCE_POSITION,
    DailyRiskAction.CANCEL_ORDER,
    DailyRiskAction.RISK_REDUCING_ORDER,
]

_ALL_ACTIONS = [*_RISK_INCREASING_ACTIONS, *_RISK_REDUCING_ACTIONS]


def evaluate_daily_halt(
    state: DailyRiskState,
    settings: DailyHaltSettings | None = None,
) -> DailyHaltDecision:
    active_settings = settings or DailyHaltSettings()
    halt_reasons: list[DailyHaltReason] = []
    max_daily_loss_amount: float | None = None

    if state.account_equity is None or state.account_equity <= 0:
        halt_reasons.append(DailyHaltReason.ACCOUNT_EQUITY_MISSING)
    else:
        max_daily_loss_amount = _money(
            state.account_equity * active_settings.max_daily_realized_loss_pct
        )

    if state.trading_day is None:
        halt_reasons.append(DailyHaltReason.TRADING_DAY_MISSING)

    if state.realized_pnl is None:
        halt_reasons.append(DailyHaltReason.DAILY_PNL_MISSING)

    if state.losing_trade_count is None:
        halt_reasons.append(DailyHaltReason.LOSING_TRADE_COUNT_MISSING)

    halt_reasons = _merge_reasons(halt_reasons, state.prior_halt_reasons)

    if (
        state.realized_pnl is not None
        and max_daily_loss_amount is not None
        and state.realized_pnl <= -max_daily_loss_amount
    ):
        halt_reasons = _append_reason(
            halt_reasons,
            DailyHaltReason.DAILY_LOSS_LIMIT_EXCEEDED,
        )

    if (
        state.losing_trade_count is not None
        and state.losing_trade_count >= active_settings.max_losing_trades_per_day
    ):
        halt_reasons = _append_reason(
            halt_reasons,
            DailyHaltReason.TOO_MANY_LOSING_TRADES,
        )

    status = DailyHaltStatus.HALTED if halt_reasons else DailyHaltStatus.ALLOWED
    allowed_actions = _allowed_actions(status, active_settings)
    blocked_actions = _blocked_actions(status, active_settings)

    return DailyHaltDecision(
        status=status,
        trading_day=state.trading_day,
        account_equity=state.account_equity,
        max_daily_loss_pct=active_settings.max_daily_realized_loss_pct,
        max_daily_loss_amount=max_daily_loss_amount,
        realized_pnl=state.realized_pnl,
        losing_trade_count=state.losing_trade_count,
        halted_until=state.halted_until,
        halt_reasons=halt_reasons,
        allowed_actions=allowed_actions,
        blocked_actions=blocked_actions,
        broker_execution_allowed_for_new_risk=status == DailyHaltStatus.ALLOWED,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.DAILY_HALT,
            rule_name="daily_halt",
            passed=status == DailyHaltStatus.ALLOWED,
            reason=",".join(reason.value for reason in halt_reasons) or None,
        ),
    )


def _allowed_actions(
    status: DailyHaltStatus,
    settings: DailyHaltSettings,
) -> list[DailyRiskAction]:
    if status == DailyHaltStatus.ALLOWED:
        return list(_ALL_ACTIONS)

    if settings.allow_risk_reducing_actions:
        return list(_RISK_REDUCING_ACTIONS)

    return []


def _blocked_actions(
    status: DailyHaltStatus,
    settings: DailyHaltSettings,
) -> list[DailyRiskAction]:
    if status == DailyHaltStatus.ALLOWED:
        return []

    if settings.allow_risk_reducing_actions:
        return list(_RISK_INCREASING_ACTIONS)

    return list(_ALL_ACTIONS)


def _merge_reasons(
    first: list[DailyHaltReason],
    second: list[DailyHaltReason],
) -> list[DailyHaltReason]:
    merged: list[DailyHaltReason] = []
    for reason in [*first, *second]:
        merged = _append_reason(merged, reason)
    return merged


def _append_reason(
    reasons: list[DailyHaltReason],
    reason: DailyHaltReason,
) -> list[DailyHaltReason]:
    if reason in reasons:
        return reasons
    return [*reasons, reason]


def _money(value: float) -> float:
    return round(value, 2)
