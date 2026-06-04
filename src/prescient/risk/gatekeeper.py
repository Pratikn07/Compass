from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prescient.journal import DecisionType
from prescient.risk.audit import risk_audit_trail
from prescient.risk.models import (
    AccountRiskSnapshot,
    RiskGateDecision,
    RiskGateStatus,
    RiskOrderProposal,
    RiskRejectionReason,
    RiskPosition,
    RiskOrder,
    ConcentrationSettings,
)
from prescient.risk.safety import contains_unsafe_claude_key
from prescient.signal.models import StrategyDecision, StrategyStatus


def evaluate_risk_gate(
    strategy_decision: StrategyDecision,
    *,
    account_snapshot: AccountRiskSnapshot | None = None,
    order_proposal: RiskOrderProposal | None = None,
    claude_advisory: Mapping[str, Any] | None = None,
    broker_positions: Sequence[RiskPosition] | None = None,
    broker_orders: Sequence[RiskOrder] | None = None,
    concentration_settings: ConcentrationSettings | None = None,
) -> RiskGateDecision:
    target, theme = _target_and_theme(strategy_decision)
    claude_present = claude_advisory is not None
    claude_override_attempted = contains_unsafe_claude_key(claude_advisory)

    if claude_override_attempted:
        return RiskGateDecision(
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            status=RiskGateStatus.BLOCKED,
            rejection_reasons=[RiskRejectionReason.CLAUDE_OVERRIDE_ATTEMPTED],
            explanation="Claude advisory attempted to provide risk, sizing, or execution fields.",
            broker_execution_allowed=False,
            claude_present=claude_present,
            claude_override_attempted=True,
            audit_trail=_gate_audit(target, theme, False, "claude_override_attempted"),
        )

    if strategy_decision.status != StrategyStatus.CANDIDATE_READY_FOR_ANALYST:
        return RiskGateDecision(
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            status=RiskGateStatus.BLOCKED,
            rejection_reasons=[RiskRejectionReason.STRATEGY_NOT_CANDIDATE_READY],
            explanation="Risk gate blocks decisions that are not candidate-ready.",
            broker_execution_allowed=False,
            claude_present=claude_present,
            claude_override_attempted=False,
            audit_trail=_gate_audit(target, theme, False, "strategy_not_candidate_ready"),
        )

    if account_snapshot is None:
        return RiskGateDecision(
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            status=RiskGateStatus.NOT_EVALUABLE,
            rejection_reasons=[RiskRejectionReason.MISSING_ACCOUNT_SNAPSHOT],
            explanation="Risk gate requires a structured account snapshot before approval.",
            broker_execution_allowed=False,
            claude_present=claude_present,
            claude_override_attempted=False,
            audit_trail=_gate_audit(target, theme, False, "missing_account_snapshot"),
        )

    if order_proposal is None:
        return RiskGateDecision(
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            status=RiskGateStatus.NOT_EVALUABLE,
            rejection_reasons=[RiskRejectionReason.MISSING_ORDER_PROPOSAL],
            explanation="Risk gate requires a structured order proposal before approval.",
            broker_execution_allowed=False,
            claude_present=claude_present,
            claude_override_attempted=False,
            audit_trail=_gate_audit(target, theme, False, "missing_order_proposal"),
        )

    if broker_positions is not None:
        # 1. Averaging-down check (R3.6)
        active_positions = [p for p in broker_positions if p.qty != 0]
        has_existing_position = any(p.symbol.upper() == target.upper() for p in active_positions)
        if has_existing_position:
            return RiskGateDecision(
                target=target,
                theme=theme,
                strategy_status=strategy_decision.status,
                status=RiskGateStatus.BLOCKED,
                rejection_reasons=[RiskRejectionReason.AVERAGING_DOWN_BLOCKED],
                explanation=f"Adding to existing position for {target} is blocked (averaging down prevention).",
                broker_execution_allowed=False,
                claude_present=claude_present,
                claude_override_attempted=claude_override_attempted,
                audit_trail=_gate_audit(target, theme, False, "averaging_down_blocked"),
            )

        # 2. Concentration check (R3.5)
        if concentration_settings is not None:
            distinct_symbols = {p.symbol.upper() for p in active_positions}
            # Max open positions check
            if len(distinct_symbols) >= concentration_settings.max_open_positions:
                return RiskGateDecision(
                    target=target,
                    theme=theme,
                    strategy_status=strategy_decision.status,
                    status=RiskGateStatus.BLOCKED,
                    rejection_reasons=[RiskRejectionReason.CONCENTRATION_LIMIT_EXCEEDED],
                    explanation=f"Max open positions limit of {concentration_settings.max_open_positions} reached. Cannot open new position in {target}.",
                    broker_execution_allowed=False,
                    claude_present=claude_present,
                    claude_override_attempted=claude_override_attempted,
                    audit_trail=_gate_audit(target, theme, False, "concentration_limit_exceeded"),
                )

            # Single-ticker exposure check
            existing_exposure = 0.0
            equity = account_snapshot.equity
            if equity > 0:
                proposed_exposure_pct = (existing_exposure + order_proposal.estimated_entry_cost) / equity
                if proposed_exposure_pct > concentration_settings.max_single_ticker_exposure_pct:
                    return RiskGateDecision(
                        target=target,
                        theme=theme,
                        strategy_status=strategy_decision.status,
                        status=RiskGateStatus.BLOCKED,
                        rejection_reasons=[RiskRejectionReason.CONCENTRATION_LIMIT_EXCEEDED],
                        explanation=f"Proposed exposure of {proposed_exposure_pct:.1%} for {target} exceeds max single ticker exposure of {concentration_settings.max_single_ticker_exposure_pct:.1%}.",
                        broker_execution_allowed=False,
                        claude_present=claude_present,
                        claude_override_attempted=claude_override_attempted,
                        audit_trail=_gate_audit(target, theme, False, "concentration_limit_exceeded"),
                    )

        # If we got here with broker positions provided, it's approved
        return RiskGateDecision(
            target=target,
            theme=theme,
            strategy_status=strategy_decision.status,
            status=RiskGateStatus.APPROVED,
            rejection_reasons=[],
            explanation="Approved: portfolio concentration and averaging-down checks passed.",
            broker_execution_allowed=True,
            claude_present=claude_present,
            claude_override_attempted=claude_override_attempted,
            audit_trail=_gate_audit(target, theme, True, None),
        )

    return RiskGateDecision(
        target=target,
        theme=theme,
        strategy_status=strategy_decision.status,
        status=RiskGateStatus.NOT_EVALUABLE,
        rejection_reasons=[RiskRejectionReason.RISK_CHECKS_NOT_IMPLEMENTED],
        explanation=(
            "R3.1 establishes the hard risk boundary; R3.2 and later milestones must "
            "implement concrete approval checks."
        ),
        broker_execution_allowed=False,
        claude_present=claude_present,
        claude_override_attempted=False,
        audit_trail=_gate_audit(target, theme, False, "risk_checks_not_implemented"),
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme

    return decision.audit.target, decision.audit.theme


def _gate_audit(target: str, theme: str | None, passed: bool, reason: str | None):
    return risk_audit_trail(
        decision_type=DecisionType.RISK_GATE,
        rule_name="risk_gatekeeper",
        target=target,
        theme=theme,
        passed=passed,
        reason=reason,
    )
