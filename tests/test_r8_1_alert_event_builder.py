from __future__ import annotations

from datetime import date, datetime, timezone

from prescient.alerts import AlertEventType, build_alert_event, build_alert_events
from prescient.journal import SourceCitation
from prescient.runtime.models import DecisionJournalRecord, DecisionJournalRecordType


def _record(
    record_type: DecisionJournalRecordType,
    *,
    strategy_status: str | None = "candidate_ready_for_analyst",
    payload: dict[str, object] | None = None,
    order_id: str | None = None,
) -> DecisionJournalRecord:
    return DecisionJournalRecord(
        journal_record_id=f"journal-{record_type.value}",
        record_type=record_type,
        run_id="scheduled:2026-06-03",
        decision_id="decision-1",
        decision_index=0,
        trading_date=date(2026, 6, 3),
        created_at=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        target="ntnx",
        theme="ai_storage",
        strategy_type="bullish_earnings_readthrough",
        strategy_status=strategy_status,
        execution_mode="paper",
        source="prescient.runtime",
        order_id=order_id,
        payload=payload or {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
        source_citations=[
            SourceCitation(
                citation_id="cit-peer",
                provider="fixture",
                source_type="earnings_result",
            )
        ],
    )


def test_strategy_candidate_record_builds_setup_detected_alert() -> None:
    event = build_alert_event(_record(DecisionJournalRecordType.STRATEGY_DECISION))

    assert event is not None
    assert event.event_type == AlertEventType.SETUP_DETECTED
    assert event.target == "NTNX"
    assert event.theme == "AI_STORAGE"
    assert event.run_id == "scheduled:2026-06-03"
    assert event.decision_id == "decision-1"
    assert event.journal_record_id == "journal-strategy_decision"
    assert event.source_citations[0].citation_id == "cit-peer"
    assert "Bullish AI_STORAGE" in event.summary


def test_rejected_strategy_record_builds_setup_blocked_alert() -> None:
    event = build_alert_event(
        _record(
            DecisionJournalRecordType.STRATEGY_DECISION,
            strategy_status="rejected_with_reason",
            payload={"rejection_reasons": ["insufficient_peers_reported"]},
        )
    )

    assert event is not None
    assert event.event_type == AlertEventType.SETUP_BLOCKED
    assert "insufficient_peers_reported" in event.summary


def test_risk_daily_halt_record_builds_daily_halt_alert() -> None:
    event = build_alert_event(
        _record(
            DecisionJournalRecordType.RISK_DECISION,
            payload={
                "status": "blocked",
                "rejection_reasons": ["daily_halt_active"],
                "risk_gate_decision": {"explanation": "Daily halt is active."},
            },
        )
    )

    assert event is not None
    assert event.event_type == AlertEventType.DAILY_HALT_ACTIVE
    assert event.severity == "critical"


def test_trade_lifecycle_records_map_to_alert_types() -> None:
    expected = {
        DecisionJournalRecordType.EXECUTION_PROPOSAL: AlertEventType.TRADE_PROPOSED,
        DecisionJournalRecordType.ORDER_SUBMITTED: AlertEventType.ORDER_SUBMITTED,
        DecisionJournalRecordType.ORDER_FILL: AlertEventType.ORDER_FILLED,
        DecisionJournalRecordType.ORDER_CANCELLED: AlertEventType.ORDER_CANCELLED,
        DecisionJournalRecordType.BROKER_REJECTION: AlertEventType.ORDER_REJECTED,
        DecisionJournalRecordType.TRADE_EXIT: AlertEventType.TRADE_EXITED,
        DecisionJournalRecordType.TRADE_OUTCOME: AlertEventType.TRADE_OUTCOME_RECORDED,
        DecisionJournalRecordType.OUTCOME_CORRECTION: AlertEventType.TRADE_OUTCOME_RECORDED,
    }

    events = [
        build_alert_event(
            _record(record_type, payload={"status": record_type.value}, order_id="order-1")
        )
        for record_type in expected
    ]

    assert [event.event_type for event in events if event is not None] == list(expected.values())
    assert all(event is not None and event.order_id == "order-1" for event in events)


def test_analyst_and_sized_records_do_not_build_alerts() -> None:
    events = build_alert_events(
        [
            _record(DecisionJournalRecordType.ANALYST_REVIEW),
            _record(DecisionJournalRecordType.SUB_AGENT_REVIEW),
            _record(
                DecisionJournalRecordType.POSITION_SIZING,
                payload={"status": "sized"},
            ),
        ]
    )

    assert events == []

