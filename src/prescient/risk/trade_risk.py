from __future__ import annotations

from math import floor, isclose

from prescient.risk.models import (
    AccountSnapshot,
    RiskDecision,
    RiskDecisionStatus,
    RiskRejectionReason,
    RiskReviewFlag,
    RiskSettings,
    TradeExpression,
    TradeProposal,
)
from prescient.risk.audit import risk_audit_trail
from prescient.journal import DecisionType


MAX_TRADE_LOSS_PCT_CEILING = 0.03
SMALL_ACCOUNT_MIN_EQUITY = 2_000.0
SMALL_ACCOUNT_MAX_EQUITY = 5_000.0
OPTIONS_NEAR_CAP_RATIO = 0.80


def evaluate_trade_risk(
    account: AccountSnapshot | None,
    proposal: TradeProposal,
    settings: RiskSettings | None = None,
) -> RiskDecision:
    active_settings = settings or RiskSettings()
    target = proposal.target
    max_trade_loss_pct = active_settings.max_trade_loss_pct
    account_equity = account.account_equity if account is not None else None
    max_allowed_loss: float | None = None
    unit_max_loss: float | None = None
    approved_quantity = 0
    projected_max_loss: float | None = None
    rejection_reasons: list[RiskRejectionReason] = []
    review_flags: list[RiskReviewFlag] = []

    if max_trade_loss_pct > MAX_TRADE_LOSS_PCT_CEILING:
        rejection_reasons.append(RiskRejectionReason.RISK_CAP_ABOVE_ALLOWED_CEILING)

    if account_equity is None:
        rejection_reasons.append(RiskRejectionReason.ACCOUNT_EQUITY_MISSING)
    elif account_equity <= 0:
        rejection_reasons.append(RiskRejectionReason.ACCOUNT_EQUITY_TOO_SMALL)
    elif not rejection_reasons:
        max_allowed_loss = _money(account_equity * max_trade_loss_pct)
        review_flags.extend(_review_flags_for_settings_and_account(active_settings, account_equity))

    if proposal.entry_price is None:
        rejection_reasons.append(RiskRejectionReason.ENTRY_PRICE_MISSING)

    if proposal.minimum_quantity is None or proposal.minimum_quantity < 1:
        rejection_reasons.append(RiskRejectionReason.INVALID_QUANTITY)

    if _is_option_expression(proposal.expression):
        multiplier = proposal.contract_multiplier if proposal.contract_multiplier is not None else 100
        if multiplier <= 0:
            rejection_reasons.append(RiskRejectionReason.INVALID_CONTRACT_MULTIPLIER)
    else:
        multiplier = 1

    if not rejection_reasons:
        unit_max_loss = _compute_unit_max_loss(proposal, multiplier)
        if unit_max_loss is None:
            rejection_reasons.append(_max_loss_failure_reason(proposal))

    if not rejection_reasons and unit_max_loss is not None and max_allowed_loss is not None:
        minimum_quantity = proposal.minimum_quantity or 1
        if _is_option_expression(proposal.expression) and (
            unit_max_loss / max_allowed_loss >= OPTIONS_NEAR_CAP_RATIO
        ):
            review_flags.append(RiskReviewFlag.OPTIONS_CONTRACT_NEAR_CAP)

        approved_quantity = floor(max_allowed_loss / unit_max_loss)
        if approved_quantity < minimum_quantity:
            approved_quantity = 0
            projected_max_loss = None
            rejection_reasons.extend(
                [
                    RiskRejectionReason.SMALLEST_TRADE_EXCEEDS_CAP,
                    RiskRejectionReason.MAX_TRADE_LOSS_EXCEEDED,
                ]
            )
        else:
            projected_max_loss = _money(approved_quantity * unit_max_loss)

    status = _status_for(rejection_reasons, review_flags)

    return RiskDecision(
        status=status,
        target=target,
        account_equity=account_equity,
        max_trade_loss_pct=max_trade_loss_pct,
        max_allowed_loss=max_allowed_loss,
        proposed_expression=proposal.expression,
        entry_price=proposal.entry_price,
        stop_price=proposal.stop_price,
        unit_max_loss=unit_max_loss,
        approved_quantity=approved_quantity,
        projected_max_loss=projected_max_loss,
        rejection_reasons=rejection_reasons,
        review_flags=review_flags,
        broker_execution_allowed=status == RiskDecisionStatus.APPROVED,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.TRADE_RISK,
            rule_name="max_trade_loss_cap",
            target=target,
            passed=not rejection_reasons,
            reason=",".join(reason.value for reason in rejection_reasons) or None,
        ),
    )


def _compute_unit_max_loss(proposal: TradeProposal, multiplier: int) -> float | None:
    entry_price = proposal.entry_price
    if entry_price is None or entry_price <= 0:
        return None

    if proposal.expression == TradeExpression.STOCK:
        if proposal.stop_price is None:
            return None
        if proposal.stop_price >= entry_price:
            return None
        return _money(entry_price - proposal.stop_price)

    if proposal.stop_price is None:
        return _money(entry_price * multiplier)

    if proposal.stop_price >= entry_price:
        return None

    return _money((entry_price - proposal.stop_price) * multiplier)


def _max_loss_failure_reason(proposal: TradeProposal) -> RiskRejectionReason:
    if proposal.expression == TradeExpression.STOCK and proposal.stop_price is None:
        return RiskRejectionReason.STOP_PRICE_MISSING

    return RiskRejectionReason.MAX_LOSS_NOT_COMPUTABLE


def _review_flags_for_settings_and_account(
    settings: RiskSettings,
    account_equity: float,
) -> list[RiskReviewFlag]:
    review_flags: list[RiskReviewFlag] = []
    if isclose(settings.max_trade_loss_pct, MAX_TRADE_LOSS_PCT_CEILING):
        review_flags.append(RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW)

    if SMALL_ACCOUNT_MIN_EQUITY <= account_equity <= SMALL_ACCOUNT_MAX_EQUITY:
        review_flags.extend(
            [
                RiskReviewFlag.SMALL_ACCOUNT,
                RiskReviewFlag.PROPOSE_ONLY_RECOMMENDED,
            ]
        )

    return review_flags


def _status_for(
    rejection_reasons: list[RiskRejectionReason],
    review_flags: list[RiskReviewFlag],
) -> RiskDecisionStatus:
    if rejection_reasons:
        return RiskDecisionStatus.REJECTED
    if review_flags:
        return RiskDecisionStatus.REVIEW_REQUIRED
    return RiskDecisionStatus.APPROVED


def _is_option_expression(expression: TradeExpression) -> bool:
    return expression in {TradeExpression.CALL_OPTION, TradeExpression.PUT_OPTION}


def _money(value: float) -> float:
    return round(value, 2)
