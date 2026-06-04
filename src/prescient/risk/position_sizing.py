from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prescient.risk.models import (
    AccountRiskSnapshot,
    AccountSnapshot,
    PositionSizingDecision,
    PositionSizingRejectionReason,
    PositionSizingStatus,
    RiskDecision,
    RiskRejectionReason,
    RiskReviewFlag,
    RiskSettings,
    TradeExpression,
    TradeProposal,
    RiskPosition,
    ConcentrationSettings,
)
from prescient.journal import DecisionType
from prescient.risk.audit import risk_audit_trail
from prescient.risk.safety import contains_unsafe_claude_key
from prescient.risk.trade_risk import evaluate_trade_risk
from prescient.signal.models import StrategyDecision, StrategyStatus


def size_position(
    strategy_decision: StrategyDecision,
    *,
    account_snapshot: AccountRiskSnapshot | None = None,
    proposal: TradeProposal | None = None,
    settings: RiskSettings = RiskSettings(),
    claude_advisory: Mapping[str, Any] | None = None,
    broker_positions: Sequence[RiskPosition] | None = None,
    concentration_settings: ConcentrationSettings | None = None,
) -> PositionSizingDecision:
    target, theme = _target_and_theme(strategy_decision)
    claude_present = claude_advisory is not None
    claude_override_attempted = contains_unsafe_claude_key(claude_advisory)

    if claude_override_attempted:
        return _decision(
            status=PositionSizingStatus.BLOCKED,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression if proposal is not None else None,
            account_equity=account_snapshot.equity if account_snapshot is not None else None,
            risk_budget=None,
            unit_max_loss=None,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[
                PositionSizingRejectionReason.CLAUDE_SIZING_OVERRIDE_ATTEMPTED
            ],
            warnings=[],
            explanation="Claude advisory attempted to provide sizing or execution fields.",
            claude_present=claude_present,
            claude_sizing_override_attempted=True,
        )

    if strategy_decision.status != StrategyStatus.CANDIDATE_READY_FOR_ANALYST:
        return _decision(
            status=PositionSizingStatus.BLOCKED,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression if proposal is not None else None,
            account_equity=account_snapshot.equity if account_snapshot is not None else None,
            risk_budget=None,
            unit_max_loss=None,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[
                PositionSizingRejectionReason.STRATEGY_NOT_CANDIDATE_READY
            ],
            warnings=[],
            explanation="Position sizing requires a candidate-ready strategy decision.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    if account_snapshot is None:
        return _decision(
            status=PositionSizingStatus.NOT_EVALUABLE,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression if proposal is not None else None,
            account_equity=None,
            risk_budget=None,
            unit_max_loss=None,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[PositionSizingRejectionReason.MISSING_ACCOUNT_SNAPSHOT],
            warnings=[],
            explanation="Position sizing requires a structured account snapshot.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    if proposal is None:
        return _decision(
            status=PositionSizingStatus.NOT_EVALUABLE,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=None,
            account_equity=account_snapshot.equity,
            risk_budget=None,
            unit_max_loss=None,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[PositionSizingRejectionReason.MISSING_ORDER_PROPOSAL],
            warnings=[],
            explanation="Position sizing requires a structured trade proposal.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    if broker_positions is not None:
        active_positions = [p for p in broker_positions if p.qty != 0]
        # 1. Averaging down check (R3.6)
        has_existing_position = any(p.symbol.upper() == target.upper() for p in active_positions)
        if has_existing_position:
            return _decision(
                status=PositionSizingStatus.BLOCKED,
                target=target,
                theme=theme,
                strategy_status=strategy_decision.status,
                expression=proposal.expression,
                account_equity=account_snapshot.equity,
                risk_budget=None,
                unit_max_loss=None,
                approved_quantity=0,
                projected_max_loss=None,
                entry_cost_required=None,
                rejection_reasons=[PositionSizingRejectionReason.AVERAGING_DOWN_BLOCKED],
                warnings=[],
                explanation=f"Averaging down or adding to existing position for {target} is blocked.",
                claude_present=claude_present,
                claude_sizing_override_attempted=False,
            )

        # 2. Max open positions check (R3.5)
        if concentration_settings is not None:
            distinct_symbols = {p.symbol.upper() for p in active_positions}
            if len(distinct_symbols) >= concentration_settings.max_open_positions:
                return _decision(
                    status=PositionSizingStatus.BLOCKED,
                    target=target,
                    theme=theme,
                    strategy_status=strategy_decision.status,
                    expression=proposal.expression,
                    account_equity=account_snapshot.equity,
                    risk_budget=None,
                    unit_max_loss=None,
                    approved_quantity=0,
                    projected_max_loss=None,
                    entry_cost_required=None,
                    rejection_reasons=[PositionSizingRejectionReason.CONCENTRATION_LIMIT_EXCEEDED],
                    warnings=[],
                    explanation=f"Adding {target} would exceed max open positions limit of {concentration_settings.max_open_positions}.",
                    claude_present=claude_present,
                    claude_sizing_override_attempted=False,
                )

    if proposal.expression not in {TradeExpression.CALL_OPTION, TradeExpression.STOCK}:
        return _decision(
            status=PositionSizingStatus.BLOCKED,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression,
            account_equity=account_snapshot.equity,
            risk_budget=None,
            unit_max_loss=None,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[PositionSizingRejectionReason.UNSUPPORTED_EXPRESSION],
            warnings=[],
            explanation="Position sizing supports only stock and call-option expressions.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    trade_risk = evaluate_trade_risk(
        account=AccountSnapshot(account_equity=account_snapshot.equity),
        proposal=proposal,
        settings=settings,
    )
    warnings = list(trade_risk.review_flags)
    rejection_reasons = _map_trade_risk_rejections(trade_risk)

    if rejection_reasons:
        return _decision(
            status=_status_for_rejections(rejection_reasons),
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression,
            account_equity=account_snapshot.equity,
            risk_budget=trade_risk.max_allowed_loss,
            unit_max_loss=trade_risk.unit_max_loss,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=rejection_reasons,
            warnings=warnings,
            explanation="Position sizing could not produce a valid whole-unit quantity.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    entry_cost_required = _entry_cost_required(proposal, trade_risk.approved_quantity)
    if entry_cost_required is None:
        return _decision(
            status=PositionSizingStatus.NOT_EVALUABLE,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression,
            account_equity=account_snapshot.equity,
            risk_budget=trade_risk.max_allowed_loss,
            unit_max_loss=trade_risk.unit_max_loss,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=None,
            rejection_reasons=[PositionSizingRejectionReason.ENTRY_PRICE_MISSING],
            warnings=warnings,
            explanation="Position sizing requires a valid entry price.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    if broker_positions is not None and concentration_settings is not None:
        active_positions = [p for p in broker_positions if p.qty != 0]
        existing_exposure = sum(p.market_value for p in active_positions if p.symbol.upper() == target.upper())
        equity = account_snapshot.equity
        if equity > 0:
            proposed_exposure_pct = (existing_exposure + entry_cost_required) / equity
            if proposed_exposure_pct > concentration_settings.max_single_ticker_exposure_pct:
                return _decision(
                    status=PositionSizingStatus.BLOCKED,
                    target=target,
                    theme=theme,
                    strategy_status=strategy_decision.status,
                    expression=proposal.expression,
                    account_equity=account_snapshot.equity,
                    risk_budget=trade_risk.max_allowed_loss,
                    unit_max_loss=trade_risk.unit_max_loss,
                    approved_quantity=0,
                    projected_max_loss=None,
                    entry_cost_required=entry_cost_required,
                    rejection_reasons=[
                        PositionSizingRejectionReason.CONCENTRATION_LIMIT_EXCEEDED
                    ],
                    warnings=warnings,
                    explanation=f"Proposed exposure of {proposed_exposure_pct:.1%} for {target} would exceed max single ticker exposure of {concentration_settings.max_single_ticker_exposure_pct:.1%}.",
                    claude_present=claude_present,
                    claude_sizing_override_attempted=False,
                )

    if trade_risk.approved_quantity < 1:
        return _decision(
            status=PositionSizingStatus.BLOCKED,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression,
            account_equity=account_snapshot.equity,
            risk_budget=trade_risk.max_allowed_loss,
            unit_max_loss=trade_risk.unit_max_loss,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=entry_cost_required,
            rejection_reasons=[
                PositionSizingRejectionReason.SMALLEST_TRADE_EXCEEDS_RISK_BUDGET
            ],
            warnings=warnings,
            explanation="Smallest valid trade exceeds the risk budget.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    available_funds = min(account_snapshot.cash, account_snapshot.buying_power)
    if entry_cost_required > available_funds:
        return _decision(
            status=PositionSizingStatus.BLOCKED,
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            expression=proposal.expression,
            account_equity=account_snapshot.equity,
            risk_budget=trade_risk.max_allowed_loss,
            unit_max_loss=trade_risk.unit_max_loss,
            approved_quantity=0,
            projected_max_loss=None,
            entry_cost_required=entry_cost_required,
            rejection_reasons=[
                PositionSizingRejectionReason.INSUFFICIENT_CASH_OR_BUYING_POWER
            ],
            warnings=warnings,
            explanation="Position sizing blocks trades that exceed cash or buying power.",
            claude_present=claude_present,
            claude_sizing_override_attempted=False,
        )

    return _decision(
        status=PositionSizingStatus.SIZED,
        target=target,
        theme=theme,
        strategy_status=strategy_decision.status,
        expression=proposal.expression,
        account_equity=account_snapshot.equity,
        risk_budget=trade_risk.max_allowed_loss,
        unit_max_loss=trade_risk.unit_max_loss,
        approved_quantity=trade_risk.approved_quantity,
        projected_max_loss=trade_risk.projected_max_loss,
        entry_cost_required=entry_cost_required,
        rejection_reasons=[],
        warnings=warnings,
        explanation="Position size was calculated by deterministic risk code.",
        claude_present=claude_present,
        claude_sizing_override_attempted=False,
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme

    return decision.audit.target, decision.audit.theme


def _map_trade_risk_rejections(
    trade_risk: RiskDecision,
) -> list[PositionSizingRejectionReason]:
    mapped: list[PositionSizingRejectionReason] = []
    for reason in trade_risk.rejection_reasons:
        mapped_reason = _map_trade_risk_rejection(reason)
        if mapped_reason is not None and mapped_reason not in mapped:
            mapped.append(mapped_reason)

    if (
        trade_risk.unit_max_loss is None
        and trade_risk.rejection_reasons == [RiskRejectionReason.STOP_PRICE_MISSING]
    ):
        mapped.append(PositionSizingRejectionReason.MAX_LOSS_NOT_COMPUTABLE)

    if trade_risk.max_allowed_loss is None and not mapped:
        mapped.append(PositionSizingRejectionReason.RISK_BUDGET_MISSING)

    return mapped


def _map_trade_risk_rejection(
    reason: RiskRejectionReason,
) -> PositionSizingRejectionReason | None:
    mapping = {
        RiskRejectionReason.ACCOUNT_EQUITY_MISSING: (
            PositionSizingRejectionReason.ACCOUNT_EQUITY_MISSING
        ),
        RiskRejectionReason.ACCOUNT_EQUITY_TOO_SMALL: (
            PositionSizingRejectionReason.ACCOUNT_EQUITY_TOO_SMALL
        ),
        RiskRejectionReason.ENTRY_PRICE_MISSING: (
            PositionSizingRejectionReason.ENTRY_PRICE_MISSING
        ),
        RiskRejectionReason.STOP_PRICE_MISSING: (
            PositionSizingRejectionReason.STOP_PRICE_MISSING
        ),
        RiskRejectionReason.INVALID_CONTRACT_MULTIPLIER: (
            PositionSizingRejectionReason.INVALID_CONTRACT_MULTIPLIER
        ),
        RiskRejectionReason.INVALID_QUANTITY: (
            PositionSizingRejectionReason.QUANTITY_NOT_INTEGER
        ),
        RiskRejectionReason.RISK_CAP_ABOVE_ALLOWED_CEILING: (
            PositionSizingRejectionReason.RISK_CAP_ABOVE_ALLOWED_CEILING
        ),
        RiskRejectionReason.MAX_LOSS_NOT_COMPUTABLE: (
            PositionSizingRejectionReason.MAX_LOSS_NOT_COMPUTABLE
        ),
        RiskRejectionReason.SMALLEST_TRADE_EXCEEDS_CAP: (
            PositionSizingRejectionReason.SMALLEST_TRADE_EXCEEDS_RISK_BUDGET
        ),
    }
    return mapping.get(reason)


def _status_for_rejections(
    reasons: list[PositionSizingRejectionReason],
) -> PositionSizingStatus:
    not_evaluable_reasons = {
        PositionSizingRejectionReason.ACCOUNT_EQUITY_MISSING,
        PositionSizingRejectionReason.ACCOUNT_EQUITY_TOO_SMALL,
        PositionSizingRejectionReason.ENTRY_PRICE_MISSING,
        PositionSizingRejectionReason.STOP_PRICE_MISSING,
        PositionSizingRejectionReason.UNIT_MAX_LOSS_MISSING,
        PositionSizingRejectionReason.UNIT_MAX_LOSS_INVALID,
        PositionSizingRejectionReason.INVALID_CONTRACT_MULTIPLIER,
        PositionSizingRejectionReason.QUANTITY_NOT_INTEGER,
        PositionSizingRejectionReason.INVALID_QUANTITY,
        PositionSizingRejectionReason.MAX_LOSS_NOT_COMPUTABLE,
        PositionSizingRejectionReason.RISK_BUDGET_MISSING,
    }
    return (
        PositionSizingStatus.NOT_EVALUABLE
        if any(reason in not_evaluable_reasons for reason in reasons)
        else PositionSizingStatus.BLOCKED
    )


def _entry_cost_required(
    proposal: TradeProposal,
    quantity: int,
) -> float | None:
    if proposal.entry_price is None or proposal.entry_price <= 0:
        return None

    multiplier = 1
    if proposal.expression == TradeExpression.CALL_OPTION:
        multiplier = (
            proposal.contract_multiplier if proposal.contract_multiplier is not None else 100
        )
        if multiplier <= 0:
            return None

    return _money(proposal.entry_price * multiplier * quantity)


def _decision(
    *,
    status: PositionSizingStatus,
    target: str,
    theme: str | None,
    strategy_status: StrategyStatus,
    expression: TradeExpression | None,
    account_equity: float | None,
    risk_budget: float | None,
    unit_max_loss: float | None,
    approved_quantity: int,
    projected_max_loss: float | None,
    entry_cost_required: float | None,
    rejection_reasons: list[PositionSizingRejectionReason],
    warnings: list[RiskReviewFlag],
    explanation: str,
    claude_present: bool,
    claude_sizing_override_attempted: bool,
) -> PositionSizingDecision:
    return PositionSizingDecision(
        status=status,
        target=target,
        theme=theme,
        strategy_status=strategy_status,
        expression=expression,
        account_equity=account_equity,
        risk_budget=risk_budget,
        unit_max_loss=unit_max_loss,
        approved_quantity=approved_quantity,
        projected_max_loss=projected_max_loss,
        entry_cost_required=entry_cost_required,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
        explanation=explanation,
        claude_present=claude_present,
        claude_sizing_override_attempted=claude_sizing_override_attempted,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.POSITION_SIZING,
            rule_name="position_sizing",
            target=target,
            theme=theme,
            passed=status == PositionSizingStatus.SIZED,
            reason=",".join(reason.value for reason in rejection_reasons) or None,
        ),
    )


def _money(value: float) -> float:
    return round(value, 2)
