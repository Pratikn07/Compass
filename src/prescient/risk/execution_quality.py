from __future__ import annotations

from prescient.risk.models import (
    DailyRiskAction,
    ExecutionQualityDecision,
    ExecutionQualityRejectionReason,
    ExecutionQualitySettings,
    ExecutionQualityStatus,
    ExecutionQualityWarning,
    ExecutionQuoteSnapshot,
    MarketSessionSnapshot,
    MarketSessionStatus,
    RewardRiskProposal,
    TradeExpression,
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


def evaluate_execution_quality(
    action: DailyRiskAction,
    session: MarketSessionSnapshot | None,
    quote: ExecutionQuoteSnapshot | None,
    reward_risk: RewardRiskProposal | None,
    settings: ExecutionQualitySettings | None = None,
) -> ExecutionQualityDecision:
    active_settings = settings or ExecutionQualitySettings()

    if action in _RISK_REDUCING_ACTIONS:
        return _risk_reducing_decision(action, session, quote, active_settings)

    target = quote.target if quote is not None else None
    expression = quote.expression if quote is not None else None
    not_evaluable_reasons: list[ExecutionQualityRejectionReason] = []
    blocked_reasons: list[ExecutionQualityRejectionReason] = []
    warnings: list[ExecutionQualityWarning] = []
    spread_pct: float | None = None
    reward_risk_ratio: float | None = None

    _evaluate_session(session, active_settings, not_evaluable_reasons, blocked_reasons, warnings)

    if quote is None:
        not_evaluable_reasons.append(ExecutionQualityRejectionReason.QUOTE_MISSING)
    else:
        spread_pct = _evaluate_quote(
            quote,
            active_settings,
            not_evaluable_reasons,
            blocked_reasons,
        )

    if reward_risk is None:
        not_evaluable_reasons.append(
            ExecutionQualityRejectionReason.REWARD_RISK_MISSING
        )
    else:
        reward_risk_ratio = _reward_risk_ratio(reward_risk, not_evaluable_reasons)
        if (
            reward_risk_ratio is not None
            and reward_risk_ratio < active_settings.min_reward_to_risk_ratio
        ):
            blocked_reasons.append(
                ExecutionQualityRejectionReason.REWARD_RISK_BELOW_MINIMUM
            )

    rejection_reasons = _merge_reasons([*not_evaluable_reasons, *blocked_reasons])
    status = _status_for(not_evaluable_reasons, blocked_reasons)

    return ExecutionQualityDecision(
        status=status,
        target=target,
        expression=expression,
        proposed_action=action,
        market_date=session.market_date if session is not None else None,
        session_status=session.session_status if session is not None else None,
        spread_pct=spread_pct,
        reward_risk_ratio=reward_risk_ratio,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
        allowed_actions=_allowed_actions(status),
        blocked_actions=_blocked_actions(status),
        broker_execution_allowed_for_new_risk=status == ExecutionQualityStatus.ALLOWED,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.EXECUTION_QUALITY,
            rule_name="execution_quality",
            target=target,
            passed=status == ExecutionQualityStatus.ALLOWED,
            reason=",".join(reason.value for reason in rejection_reasons) or None,
        ),
    )


def _risk_reducing_decision(
    action: DailyRiskAction,
    session: MarketSessionSnapshot | None,
    quote: ExecutionQuoteSnapshot | None,
    settings: ExecutionQualitySettings,
) -> ExecutionQualityDecision:
    if not settings.allow_risk_reducing_actions:
        return ExecutionQualityDecision(
            status=ExecutionQualityStatus.BLOCKED,
            target=quote.target if quote is not None else None,
            expression=quote.expression if quote is not None else None,
            proposed_action=action,
            market_date=session.market_date if session is not None else None,
            session_status=session.session_status if session is not None else None,
            spread_pct=None,
            reward_risk_ratio=None,
            rejection_reasons=[
                ExecutionQualityRejectionReason.RISK_REDUCING_ACTION_NOT_ALLOWED
            ],
            warnings=[],
            allowed_actions=[],
            blocked_actions=list(_ALL_ACTIONS),
            broker_execution_allowed_for_new_risk=False,
            audit_trail=risk_audit_trail(
                decision_type=DecisionType.EXECUTION_QUALITY,
                rule_name="execution_quality",
                target=quote.target if quote is not None else None,
                passed=False,
                reason=ExecutionQualityRejectionReason.RISK_REDUCING_ACTION_NOT_ALLOWED.value,
            ),
        )

    return ExecutionQualityDecision(
        status=ExecutionQualityStatus.ALLOWED,
        target=quote.target if quote is not None else None,
        expression=quote.expression if quote is not None else None,
        proposed_action=action,
        market_date=session.market_date if session is not None else None,
        session_status=session.session_status if session is not None else None,
        spread_pct=None,
        reward_risk_ratio=None,
        rejection_reasons=[],
        warnings=[
            ExecutionQualityWarning.RISK_REDUCING_ACTION_ALLOWED_WITHOUT_NEW_RISK_CHECKS
        ],
        allowed_actions=list(_RISK_REDUCING_ACTIONS),
        blocked_actions=[],
        broker_execution_allowed_for_new_risk=False,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.EXECUTION_QUALITY,
            rule_name="execution_quality",
            target=quote.target if quote is not None else None,
            passed=True,
            reason="risk_reducing_action",
        ),
    )


def _evaluate_session(
    session: MarketSessionSnapshot | None,
    settings: ExecutionQualitySettings,
    not_evaluable_reasons: list[ExecutionQualityRejectionReason],
    blocked_reasons: list[ExecutionQualityRejectionReason],
    warnings: list[ExecutionQualityWarning],
) -> None:
    if session is None:
        not_evaluable_reasons.append(
            ExecutionQualityRejectionReason.MARKET_SESSION_MISSING
        )
        return

    if session.is_halted or session.session_status == MarketSessionStatus.HALTED:
        blocked_reasons.append(ExecutionQualityRejectionReason.SYMBOL_HALTED)
        return

    if session.session_status == MarketSessionStatus.UNKNOWN:
        not_evaluable_reasons.append(
            ExecutionQualityRejectionReason.MARKET_SESSION_UNKNOWN
        )
        return

    if session.session_status != MarketSessionStatus.REGULAR_OPEN:
        blocked_reasons.append(
            ExecutionQualityRejectionReason.OUTSIDE_REGULAR_MARKET_HOURS
        )
        return

    if session.is_early_close:
        warnings.append(ExecutionQualityWarning.EARLY_CLOSE_SESSION)

    if (
        session.minutes_to_close is not None
        and session.minutes_to_close < settings.min_minutes_before_close_for_new_risk
    ):
        blocked_reasons.append(
            ExecutionQualityRejectionReason.TOO_CLOSE_TO_MARKET_CLOSE
        )


def _evaluate_quote(
    quote: ExecutionQuoteSnapshot,
    settings: ExecutionQualitySettings,
    not_evaluable_reasons: list[ExecutionQualityRejectionReason],
    blocked_reasons: list[ExecutionQualityRejectionReason],
) -> float | None:
    if quote.quote_age_seconds is None or quote.quote_age_seconds > settings.max_quote_age_seconds:
        not_evaluable_reasons.append(ExecutionQualityRejectionReason.QUOTE_STALE)

    spread_pct = _spread_pct(quote, not_evaluable_reasons, blocked_reasons)
    if spread_pct is not None:
        if quote.expression == TradeExpression.STOCK:
            if spread_pct > settings.max_stock_bid_ask_spread_pct:
                blocked_reasons.append(
                    ExecutionQualityRejectionReason.STOCK_SPREAD_TOO_WIDE
                )
        elif _is_option_expression(quote.expression):
            if spread_pct > settings.max_option_bid_ask_spread_pct:
                blocked_reasons.append(
                    ExecutionQualityRejectionReason.OPTION_SPREAD_TOO_WIDE
                )
        else:
            blocked_reasons.append(ExecutionQualityRejectionReason.UNSUPPORTED_EXPRESSION)

    if quote.avg_daily_volume is None:
        not_evaluable_reasons.append(
            ExecutionQualityRejectionReason.AVERAGE_VOLUME_MISSING
        )
    elif quote.avg_daily_volume < settings.min_avg_daily_volume:
        blocked_reasons.append(ExecutionQualityRejectionReason.AVERAGE_VOLUME_TOO_LOW)

    if _is_option_expression(quote.expression):
        if quote.option_open_interest is None:
            not_evaluable_reasons.append(
                ExecutionQualityRejectionReason.OPTION_OPEN_INTEREST_MISSING
            )
        elif quote.option_open_interest < settings.min_option_open_interest:
            blocked_reasons.append(
                ExecutionQualityRejectionReason.OPTION_OPEN_INTEREST_TOO_LOW
            )

    return spread_pct


def _spread_pct(
    quote: ExecutionQuoteSnapshot,
    not_evaluable_reasons: list[ExecutionQualityRejectionReason],
    blocked_reasons: list[ExecutionQualityRejectionReason],
) -> float | None:
    if quote.bid is None or quote.ask is None:
        not_evaluable_reasons.append(ExecutionQualityRejectionReason.BID_ASK_MISSING)
        return None

    if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        blocked_reasons.append(ExecutionQualityRejectionReason.INVALID_BID_ASK)
        return None

    midpoint = (quote.ask + quote.bid) / 2
    if midpoint <= 0:
        blocked_reasons.append(ExecutionQualityRejectionReason.INVALID_BID_ASK)
        return None

    return _money(((quote.ask - quote.bid) / midpoint) * 100)


def _reward_risk_ratio(
    reward_risk: RewardRiskProposal,
    not_evaluable_reasons: list[ExecutionQualityRejectionReason],
) -> float | None:
    if reward_risk.expected_reward is not None or reward_risk.maximum_loss is not None:
        if reward_risk.expected_reward is None:
            not_evaluable_reasons.append(
                ExecutionQualityRejectionReason.TARGET_PRICE_MISSING
            )
            return None

        if reward_risk.maximum_loss is None or reward_risk.maximum_loss <= 0:
            not_evaluable_reasons.append(
                ExecutionQualityRejectionReason.STOP_OR_MAX_LOSS_MISSING
            )
            return None

        if reward_risk.expected_reward <= 0:
            not_evaluable_reasons.append(
                ExecutionQualityRejectionReason.TARGET_PRICE_MISSING
            )
            return None

        return _money(reward_risk.expected_reward / reward_risk.maximum_loss)

    entry_price = reward_risk.entry_price
    stop_price = reward_risk.stop_price
    target_price = reward_risk.target_price

    if entry_price is None or entry_price <= 0:
        not_evaluable_reasons.append(ExecutionQualityRejectionReason.ENTRY_PRICE_MISSING)
        return None

    if stop_price is None or stop_price >= entry_price:
        not_evaluable_reasons.append(
            ExecutionQualityRejectionReason.STOP_OR_MAX_LOSS_MISSING
        )
        return None

    if target_price is None or target_price <= entry_price:
        not_evaluable_reasons.append(ExecutionQualityRejectionReason.TARGET_PRICE_MISSING)
        return None

    maximum_loss = entry_price - stop_price
    expected_reward = target_price - entry_price
    return _money(expected_reward / maximum_loss)


def _status_for(
    not_evaluable_reasons: list[ExecutionQualityRejectionReason],
    blocked_reasons: list[ExecutionQualityRejectionReason],
) -> ExecutionQualityStatus:
    if not_evaluable_reasons:
        return ExecutionQualityStatus.NOT_EVALUABLE
    if blocked_reasons:
        return ExecutionQualityStatus.BLOCKED
    return ExecutionQualityStatus.ALLOWED


def _allowed_actions(status: ExecutionQualityStatus) -> list[DailyRiskAction]:
    if status == ExecutionQualityStatus.ALLOWED:
        return list(_ALL_ACTIONS)
    return []


def _blocked_actions(status: ExecutionQualityStatus) -> list[DailyRiskAction]:
    if status == ExecutionQualityStatus.ALLOWED:
        return []
    return list(_RISK_INCREASING_ACTIONS)


def _merge_reasons(
    reasons: list[ExecutionQualityRejectionReason],
) -> list[ExecutionQualityRejectionReason]:
    merged: list[ExecutionQualityRejectionReason] = []
    for reason in reasons:
        if reason not in merged:
            merged.append(reason)
    return merged


def _is_option_expression(expression: TradeExpression) -> bool:
    return expression in {TradeExpression.CALL_OPTION, TradeExpression.PUT_OPTION}


def _money(value: float) -> float:
    return round(value, 2)
