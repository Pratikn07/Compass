from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from prescient.alerts import (
    InMemoryNotificationAdapter,
    NotificationDeliveryStatus,
    NotificationChannel,
    TradeNotificationSettings,
)
from prescient.broker import BrokerOrderStatus, OrderExecutionResult
from prescient.risk import (
    AccountRiskSnapshot,
    PositionSizingDecision,
    PositionSizingStatus,
    RiskReviewFlag,
    TradeExpression,
)
from prescient.rollout import RolloutStage
from prescient.runtime.execution import execute_pipeline_results
from prescient.runtime.models import PipelineRunResult
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


def _candidate_decision() -> StrategyDecision:
    candidate = CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 10),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=4.2,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP", "PSTG", "WDC"],
        peer_scores=[PeerScore(ticker="NTAP", score=5)],
        main_thesis="Bullish AI_STORAGE read-through for NTNX.",
        supporting_evidence=["Peers are strong."],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
    )
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=candidate,
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
            target="NTNX",
            theme="AI_STORAGE",
            peer_scores=[],
            thresholds={},
            missing_peer_factor_count=0,
            all_peer_data_missing=False,
            target_market_data_present=True,
            option_contract_count=1,
        ),
        claude_analysis_allowed=True,
    )


def _no_trade_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.NO_TRADE,
        candidate=None,
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
            target="NTNX",
            theme="AI_STORAGE",
            peer_scores=[],
            thresholds={},
            missing_peer_factor_count=0,
            all_peer_data_missing=False,
            target_market_data_present=True,
            option_contract_count=1,
        ),
        claude_analysis_allowed=False,
    )


def _sized_decision() -> PositionSizingDecision:
    return PositionSizingDecision(
        status=PositionSizingStatus.SIZED,
        target="NTNX",
        theme="AI_STORAGE",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        expression=TradeExpression.CALL_OPTION,
        account_equity=10_000.0,
        risk_budget=300.0,
        unit_max_loss=100.0,
        approved_quantity=1,
        projected_max_loss=100.0,
        entry_cost_required=100.0,
        rejection_reasons=[],
        warnings=[RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW],
        explanation="Sized for integration test.",
        claude_present=False,
        claude_sizing_override_attempted=False,
    )


def _broker(order_result: OrderExecutionResult) -> MagicMock:
    broker = MagicMock()
    broker.get_account_snapshot.return_value = AccountRiskSnapshot(
        equity=10_000.0,
        cash=10_000.0,
        buying_power=10_000.0,
    )
    broker.get_positions.return_value = []
    broker.get_orders.return_value = []
    broker.place_order.return_value = order_result
    return broker


def _filled_order() -> OrderExecutionResult:
    return OrderExecutionResult(
        broker="alpaca",
        order_id="order-123",
        status=BrokerOrderStatus.FILLED,
        filled_qty=1,
        avg_fill_price=5.15,
        submitted_at=datetime(2026, 6, 3, 14, 30, tzinfo=UTC),
        message="filled",
    )


def test_runtime_dispatches_notification_only_after_broker_result(monkeypatch) -> None:
    adapter = InMemoryNotificationAdapter()
    order_result = _filled_order()
    broker = _broker(order_result)

    def place_order_after_confirming_no_notification(_proposal):
        assert adapter.sent_requests == []
        return order_result

    broker.place_order.side_effect = place_order_after_confirming_no_notification
    monkeypatch.setattr("prescient.runtime.execution.size_position", lambda *a, **k: _sized_decision())

    result = execute_pipeline_results(
        PipelineRunResult(strategy_decisions=[_candidate_decision()]),
        broker,
        notification_adapter=adapter,
        notification_settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        rollout_stage=RolloutStage.PAPER_TRADING,
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
    )

    assert broker.place_order.call_count == 1
    assert len(adapter.sent_requests) == 1
    assert len(result.execution_results) == 1
    assert result.execution_results[0].order_result == order_result
    assert result.execution_results[0].notification_result is not None
    assert result.execution_results[0].notification_result.delivery_status == (
        NotificationDeliveryStatus.SENT
    )


def test_order_journal_record_is_written_before_notification_record(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("prescient.runtime.execution.size_position", lambda *a, **k: _sized_decision())
    journal_path = tmp_path / "execution-journal.jsonl"

    result = execute_pipeline_results(
        PipelineRunResult(strategy_decisions=[_candidate_decision()]),
        _broker(_filled_order()),
        notification_adapter=InMemoryNotificationAdapter(),
        notification_settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        rollout_stage=RolloutStage.PAPER_TRADING,
        journal_path=journal_path,
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
    )

    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [record["record_type"] for record in records] == [
        "order_submitted",
        "trade_notification",
    ]
    assert records[0]["order_id"] == "order-123"
    assert records[1]["order_id"] == "order-123"
    assert result.decision_journal_records[0].record_type.value == "order_submitted"
    assert result.decision_journal_records[1].record_type.value == "trade_notification"


class FailingNotificationAdapter:
    def send_trade_notification(self, _request):
        raise RuntimeError("push provider unavailable")


def test_notification_failure_does_not_mutate_order_result(monkeypatch) -> None:
    monkeypatch.setattr("prescient.runtime.execution.size_position", lambda *a, **k: _sized_decision())
    order_result = _filled_order()
    before = order_result.model_dump(mode="json")

    result = execute_pipeline_results(
        PipelineRunResult(strategy_decisions=[_candidate_decision()]),
        _broker(order_result),
        notification_adapter=FailingNotificationAdapter(),
        notification_settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        rollout_stage=RolloutStage.PAPER_TRADING,
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
    )

    assert order_result.model_dump(mode="json") == before
    assert result.execution_results[0].order_result == order_result
    assert result.execution_results[0].notification_result is not None
    assert result.execution_results[0].notification_result.delivery_status == (
        NotificationDeliveryStatus.FAILED
    )


def test_no_order_placed_means_no_notification() -> None:
    adapter = InMemoryNotificationAdapter()
    broker = _broker(_filled_order())

    result = execute_pipeline_results(
        PipelineRunResult(strategy_decisions=[_no_trade_decision()]),
        broker,
        notification_adapter=adapter,
        notification_settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
    )

    broker.place_order.assert_not_called()
    assert adapter.sent_requests == []
    assert result.execution_results == []
    assert result.notification_results == []


def test_existing_execution_callers_still_work_when_notification_args_are_omitted() -> None:
    broker = _broker(_filled_order())

    result = execute_pipeline_results(
        PipelineRunResult(strategy_decisions=[_no_trade_decision()]),
        broker,
    )

    broker.get_account_snapshot.assert_called_once()
    broker.place_order.assert_not_called()
    assert result.execution_results == []
