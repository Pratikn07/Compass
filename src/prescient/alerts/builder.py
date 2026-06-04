from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from prescient.runtime.models import DecisionJournalRecordType

from prescient.alerts.models import (
    AlertEvent,
    AlertEventType,
    AlertSeverity,
    deterministic_alert_id,
)


_TRADE_EVENT_TYPES = {
    DecisionJournalRecordType.EXECUTION_PROPOSAL: AlertEventType.TRADE_PROPOSED,
    DecisionJournalRecordType.ORDER_SUBMITTED: AlertEventType.ORDER_SUBMITTED,
    DecisionJournalRecordType.ORDER_FILL: AlertEventType.ORDER_FILLED,
    DecisionJournalRecordType.ORDER_CANCELLED: AlertEventType.ORDER_CANCELLED,
    DecisionJournalRecordType.BROKER_REJECTION: AlertEventType.ORDER_REJECTED,
    DecisionJournalRecordType.TRADE_EXIT: AlertEventType.TRADE_EXITED,
    DecisionJournalRecordType.TRADE_OUTCOME: AlertEventType.TRADE_OUTCOME_RECORDED,
    DecisionJournalRecordType.OUTCOME_CORRECTION: AlertEventType.TRADE_OUTCOME_RECORDED,
}


def build_alert_events(records: Iterable[Any]) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for record in records:
        event = build_alert_event(record)
        if event is not None:
            events.append(event)
    return events


def build_alert_event(record: Any) -> AlertEvent | None:
    event_type = _event_type_for_record(record)
    if event_type is None:
        return None

    severity = _severity_for_event(event_type)
    return AlertEvent(
        alert_id=deterministic_alert_id(
            event_type=event_type,
            run_id=record.run_id,
            decision_id=record.decision_id,
            journal_record_id=record.journal_record_id,
        ),
        event_type=event_type,
        severity=severity,
        run_id=record.run_id,
        decision_id=record.decision_id,
        journal_record_id=record.journal_record_id,
        target=record.target,
        theme=record.theme,
        strategy_type=record.strategy_type,
        execution_mode=record.execution_mode,
        order_id=record.order_id,
        title=_title(event_type, record),
        summary=_summary(event_type, record),
        details=_details(record),
        source_citations=record.source_citations,
        created_at=record.created_at,
    )


def _event_type_for_record(record: Any) -> AlertEventType | None:
    if record.record_type == DecisionJournalRecordType.STRATEGY_DECISION:
        status = (record.strategy_status or "").lower()
        if status == "candidate_ready_for_analyst":
            return AlertEventType.SETUP_DETECTED
        if status in {"rejected_with_reason", "no_trade"}:
            return AlertEventType.SETUP_BLOCKED
        return None

    if record.record_type == DecisionJournalRecordType.RISK_DECISION:
        if _is_daily_halt(record.payload):
            return AlertEventType.DAILY_HALT_ACTIVE
        if _payload_status(record.payload) in {"blocked", "not_evaluable", "rejected"}:
            return AlertEventType.SETUP_BLOCKED
        return None

    if record.record_type == DecisionJournalRecordType.POSITION_SIZING:
        if _payload_status(record.payload) not in {"", "sized", "approved"}:
            return AlertEventType.SETUP_BLOCKED
        return None

    return _TRADE_EVENT_TYPES.get(record.record_type)


def _severity_for_event(event_type: AlertEventType) -> AlertSeverity:
    if event_type == AlertEventType.DAILY_HALT_ACTIVE:
        return AlertSeverity.CRITICAL
    if event_type in {
        AlertEventType.SETUP_BLOCKED,
        AlertEventType.ORDER_REJECTED,
        AlertEventType.ORDER_CANCELLED,
    }:
        return AlertSeverity.WARNING
    return AlertSeverity.INFO


def _title(event_type: AlertEventType, record: Any) -> str:
    target = record.target or "UNKNOWN"
    return f"{event_type.name}: {target}"


def _summary(event_type: AlertEventType, record: Any) -> str:
    payload = record.payload
    if event_type == AlertEventType.SETUP_DETECTED:
        return str(payload.get("thesis") or "Setup detected.")

    if event_type == AlertEventType.SETUP_BLOCKED:
        reasons = payload.get("rejection_reasons")
        if isinstance(reasons, list) and reasons:
            return ", ".join(str(reason) for reason in reasons)
        return str(payload.get("status") or payload.get("thesis") or "Setup blocked.")

    if event_type == AlertEventType.DAILY_HALT_ACTIVE:
        risk = payload.get("risk_gate_decision")
        if isinstance(risk, dict):
            return str(risk.get("explanation") or "Daily halt is active.")
        return "Daily halt is active."

    if event_type == AlertEventType.TRADE_OUTCOME_RECORDED:
        outcome = payload.get("outcome")
        if isinstance(outcome, dict):
            pnl = outcome.get("net_realized_pnl")
            outcome_type = outcome.get("outcome_type", "unknown")
            return f"Trade outcome recorded: {outcome_type}; net P&L={pnl}."
    return f"{event_type.name} recorded."


def _details(record: Any) -> dict[str, Any]:
    return {
        "record_type": record.record_type.value,
        "strategy_status": record.strategy_status,
        "order_id": record.order_id,
        "payload_summary": _compact_payload(record.payload),
    }


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "rejection_reasons",
        "broker_execution_allowed",
        "approved_quantity",
        "projected_max_loss",
        "entry_cost_required",
        "outcome",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _payload_status(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    return str(status).lower() if status is not None else ""


def _is_daily_halt(payload: dict[str, Any]) -> bool:
    serialized = json.dumps(payload, sort_keys=True).lower()
    return "daily_halt" in serialized or "daily halt" in serialized
