from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel

from prescient.alerts.models import TradeNotificationResult
from prescient.analyst.models import ClaudeAnalysisResult, SubAgentReviewPacket
from prescient.broker.models import BrokerOrder, OrderExecutionResult
from prescient.journal import SourceCitation, merge_source_citations
from prescient.risk import PositionSizingDecision, RiskGateDecision
from prescient.rollout import RolloutGateDecision
from prescient.runtime.models import (
    DecisionJournalRecord,
    DecisionJournalRecordType,
    DecisionOutcome,
    DecisionOutcomeType,
)
from prescient.signal.models import (
    OptionContractSnapshot,
    StrategyDecision,
    StrategySettings,
    StrategyStatus,
    TargetMarketData,
)
from prescient.signal.strategy_types import DEFAULT_STRATEGY_TYPE


def build_decision_id(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    strategy_type: str = DEFAULT_STRATEGY_TYPE.value,
) -> str:
    target, _ = _target_and_theme(decision)
    return _stable_hash(
        {
            "run_id": run_id,
            "decision_index": decision_index,
            "target": target,
            "strategy_type": strategy_type,
            "strategy_status": decision.status.value,
        }
    )


def build_strategy_decision_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    trading_date: date,
    settings: StrategySettings,
    target_market_data: TargetMarketData | None = None,
    options_chain: list[OptionContractSnapshot] | None = None,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    payload = {
        "thesis": _decision_thesis(decision),
        "decision_summary": decision.status.value,
        "strategy_decision": _dump_model(decision),
        "candidate_brief": _dump_model(decision.candidate),
        "rejection_reasons": [reason.value for reason in decision.rejection_reasons],
        "rejection_details": [_dump_model(detail) for detail in decision.rejection_details],
        "warnings": [],
        "data_snapshot": _data_snapshot(
            decision=decision,
            target_market_data=target_market_data,
            options_chain=options_chain or [],
        ),
        "settings_snapshot": settings.model_dump(mode="json"),
        "missing_data": _missing_data(decision),
        "source_events": [],
    }
    return _record(
        record_type=DecisionJournalRecordType.STRATEGY_DECISION,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        payload=payload,
        source_citations=decision.audit_trail.source_citations,
    )


def build_analyst_review_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    claude_result: ClaudeAnalysisResult,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    payload = {
        "claude_result": _dump_model(claude_result),
        "status": claude_result.status.value,
        "analysis": _dump_model(claude_result.analysis),
        "error_message": claude_result.error_message,
    }
    return _record(
        record_type=DecisionJournalRecordType.ANALYST_REVIEW,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        payload=payload,
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            claude_result.audit_trail.source_citations,
        ),
    )


def build_sub_agent_review_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    sub_agent_packet: SubAgentReviewPacket,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    payload = {
        "sub_agent_packet": _dump_model(sub_agent_packet),
        "results": [_dump_model(result) for result in sub_agent_packet.results],
    }
    return _record(
        record_type=DecisionJournalRecordType.SUB_AGENT_REVIEW,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        payload=payload,
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            sub_agent_packet.audit_trail.source_citations,
        ),
    )


def build_risk_decision_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    risk_decision: RiskGateDecision,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    payload = {
        "risk_gate_decision": _dump_model(risk_decision),
        "status": risk_decision.status.value,
        "rejection_reasons": [reason.value for reason in risk_decision.rejection_reasons],
        "broker_execution_allowed": risk_decision.broker_execution_allowed,
    }
    return _record(
        record_type=DecisionJournalRecordType.RISK_DECISION,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        payload=payload,
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            risk_decision.audit_trail.source_citations,
        ),
    )


def build_position_sizing_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    sizing_decision: PositionSizingDecision,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    payload = {
        "position_sizing_decision": _dump_model(sizing_decision),
        "status": sizing_decision.status.value,
        "approved_quantity": sizing_decision.approved_quantity,
        "projected_max_loss": sizing_decision.projected_max_loss,
        "entry_cost_required": sizing_decision.entry_cost_required,
        "rejection_reasons": [
            reason.value for reason in sizing_decision.rejection_reasons
        ],
    }
    return _record(
        record_type=DecisionJournalRecordType.POSITION_SIZING,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        payload=payload,
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            sizing_decision.audit_trail.source_citations,
        ),
    )


def build_rollout_gate_decision_record(
    *,
    run_id: str,
    trading_date: date,
    gate_decision: RolloutGateDecision,
    decision_id: str,
    decision_index: int | None = None,
    target: str | None = None,
    theme: str | None = None,
    strategy_status: str | None = None,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    payload = _rollout_payload(gate_decision)
    return _record(
        record_type=DecisionJournalRecordType.ROLLOUT_GATE_DECISION,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=strategy_status,
        execution_mode=execution_mode,
        payload=payload,
        source="prescient.rollout",
    )


def build_rollout_promotion_record(
    *,
    run_id: str,
    trading_date: date,
    gate_decision: RolloutGateDecision,
) -> DecisionJournalRecord:
    decision_id = _stable_hash(
        {
            "run_id": run_id,
            "record_type": DecisionJournalRecordType.ROLLOUT_PROMOTION.value,
            "current_stage": gate_decision.current_stage.value,
            "requested_stage": gate_decision.requested_stage.value
            if gate_decision.requested_stage is not None
            else None,
            "status": gate_decision.status.value,
        }
    )
    return _record(
        record_type=DecisionJournalRecordType.ROLLOUT_PROMOTION,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=None,
        trading_date=trading_date,
        target=None,
        theme=None,
        strategy_status=None,
        execution_mode=gate_decision.requested_execution_mode,
        payload=_rollout_payload(gate_decision),
        source="prescient.rollout",
    )


def build_execution_proposal_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    payload: dict[str, Any],
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    return _lifecycle_record(
        record_type=DecisionJournalRecordType.EXECUTION_PROPOSAL,
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        trading_date=trading_date,
        execution_mode=execution_mode,
        payload=payload,
    )


def build_order_submitted_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    order_result: OrderExecutionResult,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    return _lifecycle_record(
        record_type=DecisionJournalRecordType.ORDER_SUBMITTED,
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        trading_date=trading_date,
        execution_mode=execution_mode,
        order_id=order_result.order_id,
        payload={"order_execution_result": _dump_model(order_result)},
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            order_result.source_citations,
            order_result.audit_trail.source_citations,
        ),
    )


def build_order_fill_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    order: BrokerOrder,
    trading_date: date,
    execution_mode: str | None = None,
) -> DecisionJournalRecord:
    return _lifecycle_record(
        record_type=DecisionJournalRecordType.ORDER_FILL,
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        trading_date=trading_date,
        execution_mode=execution_mode,
        order_id=order.order_id,
        payload={"broker_order": _dump_model(order)},
        source_citations=merge_source_citations(
            decision.audit_trail.source_citations,
            order.source_citations,
            order.audit_trail.source_citations,
        ),
    )


def build_trade_exit_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    payload: dict[str, Any],
    trading_date: date,
    execution_mode: str | None = None,
    order_id: str | None = None,
    source_citations: list[SourceCitation] | None = None,
) -> DecisionJournalRecord:
    return _lifecycle_record(
        record_type=DecisionJournalRecordType.TRADE_EXIT,
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        trading_date=trading_date,
        execution_mode=execution_mode,
        order_id=order_id,
        payload=payload,
    )


def build_trade_outcome_record(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    outcome: DecisionOutcome,
    trading_date: date,
    execution_mode: str | None = None,
    order_id: str | None = None,
) -> DecisionJournalRecord:
    return _lifecycle_record(
        record_type=DecisionJournalRecordType.TRADE_OUTCOME,
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        trading_date=trading_date,
        execution_mode=execution_mode,
        order_id=order_id,
        payload={"outcome": _dump_model(outcome)},
    )


def build_trade_notification_record(
    *,
    notification_result: TradeNotificationResult,
    trading_date: date,
) -> DecisionJournalRecord:
    request = notification_result.request
    return _record(
        record_type=DecisionJournalRecordType.TRADE_NOTIFICATION,
        run_id=notification_result.run_id,
        decision_id=notification_result.decision_id,
        decision_index=request.decision_index,
        trading_date=trading_date,
        target=notification_result.target,
        theme=request.theme,
        strategy_status=request.strategy_status.value,
        execution_mode=notification_result.execution_mode,
        order_id=notification_result.order_id,
        source="prescient.alerts",
        payload={
            "trade_notification_result": _dump_model(notification_result),
            "event_type": notification_result.event_type.value,
            "delivery_status": notification_result.delivery_status.value,
            "delivery_channel": notification_result.delivery_channel.value
            if notification_result.delivery_channel is not None
            else None,
            "message": notification_result.message,
        },
        source_citations=merge_source_citations(
            request.source_citations,
            request.audit_trail.source_citations,
            notification_result.audit_trail.source_citations,
        ),
    )


def classify_decision_outcome(
    *,
    net_realized_pnl: float | None,
    gross_realized_pnl: float | None = None,
    fees: float | None = None,
    pnl_currency: str = "USD",
    open_quantity: float | None = None,
    closed_quantity: float | None = None,
    outcome_reasons: list[str] | None = None,
    ambiguous: bool = False,
) -> DecisionOutcome:
    if net_realized_pnl is None:
        outcome_type = DecisionOutcomeType.UNKNOWN
    elif net_realized_pnl > 0:
        outcome_type = DecisionOutcomeType.CLOSED_WIN
    elif net_realized_pnl < 0:
        outcome_type = DecisionOutcomeType.CLOSED_LOSS
    else:
        outcome_type = DecisionOutcomeType.CLOSED_FLAT

    return DecisionOutcome(
        outcome_type=outcome_type,
        net_realized_pnl=net_realized_pnl,
        gross_realized_pnl=gross_realized_pnl,
        fees=fees,
        pnl_currency=pnl_currency,
        open_quantity=open_quantity,
        closed_quantity=closed_quantity,
        outcome_reasons=outcome_reasons or [],
        ambiguous=ambiguous,
    )


def _lifecycle_record(
    *,
    record_type: DecisionJournalRecordType,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    trading_date: date,
    execution_mode: str | None,
    payload: dict[str, Any],
    order_id: str | None = None,
    source_citations: list[SourceCitation] | None = None,
) -> DecisionJournalRecord:
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    target, theme = _target_and_theme(decision)
    return _record(
        record_type=record_type,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
        order_id=order_id,
        payload=_json_safe(payload),
        source_citations=source_citations
        if source_citations is not None
        else decision.audit_trail.source_citations,
    )


def _record(
    *,
    record_type: DecisionJournalRecordType,
    run_id: str,
    decision_id: str,
    decision_index: int | None,
    trading_date: date,
    target: str | None,
    theme: str | None,
    strategy_status: str | None,
    payload: dict[str, Any],
    execution_mode: str | None = None,
    order_id: str | None = None,
    source: str = "prescient.runtime",
    source_citations: list[SourceCitation] | None = None,
) -> DecisionJournalRecord:
    safe_payload = _json_safe(payload)
    journal_record_id = _stable_hash(
        {
            "record_type": record_type.value,
            "run_id": run_id,
            "decision_id": decision_id,
            "decision_index": decision_index,
            "target": target,
            "strategy_status": strategy_status,
            "execution_mode": execution_mode,
            "order_id": order_id,
            "source": source,
            "payload": safe_payload,
        }
    )
    return DecisionJournalRecord(
        journal_record_id=journal_record_id,
        record_type=record_type,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        trading_date=trading_date,
        created_at=datetime.now(timezone.utc),
        target=target,
        theme=theme,
        strategy_type=DEFAULT_STRATEGY_TYPE.value,
        strategy_status=strategy_status,
        execution_mode=execution_mode,
        source=source,
        order_id=order_id,
        payload=safe_payload,
        source_citations=source_citations or [],
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme

    return decision.audit.target, decision.audit.theme


def _decision_thesis(decision: StrategyDecision) -> str:
    if decision.candidate is not None:
        return decision.candidate.main_thesis

    if decision.rejection_details:
        reasons = "; ".join(detail.message for detail in decision.rejection_details)
    elif decision.rejection_reasons:
        reasons = ", ".join(reason.value for reason in decision.rejection_reasons)
    elif decision.status == StrategyStatus.NO_TRADE:
        reasons = "No trade was produced by the deterministic strategy engine."
    else:
        reasons = decision.status.value

    target, _ = _target_and_theme(decision)
    return f"Rejected strategy decision for {target}: {reasons}"


def _data_snapshot(
    *,
    decision: StrategyDecision,
    target_market_data: TargetMarketData | None,
    options_chain: list[OptionContractSnapshot],
) -> dict[str, Any]:
    audit = decision.audit
    snapshot = {
        "target": audit.target,
        "theme": audit.theme,
        "peer_scores": [_dump_model(score) for score in audit.peer_scores],
        "thresholds": audit.thresholds,
        "missing_peer_factor_count": audit.missing_peer_factor_count,
        "all_peer_data_missing": audit.all_peer_data_missing,
        "target_market_data_present": audit.target_market_data_present,
        "target_market_data": _dump_model(target_market_data),
        "option_contract_count": audit.option_contract_count,
        "options_chain_summary": [_option_summary(option) for option in options_chain],
        "indicator_snapshot_present": audit.indicator_snapshot_present,
        "indicator_missing_fields": audit.indicator_missing_fields,
        "indicator_source": audit.indicator_source,
        "indicator_freshness": audit.indicator_freshness.value
        if audit.indicator_freshness is not None
        else None,
    }
    if decision.candidate is not None:
        snapshot["reported_peers"] = decision.candidate.reported_peers
        snapshot["earnings_date"] = decision.candidate.earnings_date.isoformat()
        snapshot["recommended_expression"] = decision.candidate.recommended_expression

    return snapshot


def _option_summary(option: OptionContractSnapshot) -> dict[str, Any]:
    return {
        "ticker": option.ticker,
        "option_type": option.option_type,
        "expiration_date": option.expiration_date.isoformat(),
        "bid": option.bid,
        "ask": option.ask,
        "open_interest": option.open_interest,
    }


def _missing_data(decision: StrategyDecision) -> list[str]:
    missing: list[str] = []
    if decision.audit.all_peer_data_missing:
        missing.append("peer_data")
    if not decision.audit.target_market_data_present:
        missing.append("target_market_data")
    missing.extend(decision.audit.indicator_missing_fields)
    return missing


def _rollout_payload(gate_decision: RolloutGateDecision) -> dict[str, Any]:
    return {
        "rollout_gate_decision": _dump_model(gate_decision),
        "status": gate_decision.status.value,
        "current_stage": gate_decision.current_stage.value,
        "requested_stage": gate_decision.requested_stage.value
        if gate_decision.requested_stage is not None
        else None,
        "approved_stage": gate_decision.approved_stage.value
        if gate_decision.approved_stage is not None
        else None,
        "requested_execution_mode": gate_decision.requested_execution_mode,
        "proposed_max_loss_pct": gate_decision.proposed_max_loss_pct,
        "tiny_live_cap_pct": gate_decision.tiny_live_cap_pct,
        "broker_execution_allowed": gate_decision.broker_execution_allowed,
        "rejection_reasons": [
            reason.value for reason in gate_decision.rejection_reasons
        ],
        "explanation": gate_decision.explanation,
    }


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
