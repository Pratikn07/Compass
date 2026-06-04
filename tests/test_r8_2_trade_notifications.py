from __future__ import annotations

from datetime import UTC, date, datetime

from prescient.alerts import (
    InMemoryNotificationAdapter,
    NotificationDeliveryStatus,
    NotificationError,
    NotificationErrorType,
    NotificationChannel,
    TradeNotificationEventType,
    TradeNotificationSettings,
    build_trade_notification_request,
    dispatch_trade_notification,
)
from prescient.broker import BrokerOrderStatus, OrderExecutionResult
from prescient.risk import RiskOrderProposal
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


def _proposal() -> RiskOrderProposal:
    return RiskOrderProposal(
        target="NTNX",
        expression="CALL_OPTION",
        estimated_entry_cost=515.0,
        maximum_loss=515.0,
    )


def _order_result(
    status: BrokerOrderStatus,
    *,
    order_id: str = "order-123",
    filled_qty: int = 0,
    avg_fill_price: float | None = None,
    broker: str = "alpaca",
) -> OrderExecutionResult:
    return OrderExecutionResult(
        broker=broker,
        order_id=order_id,
        status=status,
        filled_qty=filled_qty,
        avg_fill_price=avg_fill_price,
        submitted_at=datetime(2026, 6, 3, 14, 30, tzinfo=UTC),
        message="accepted",
    )


def _request(
    order_result: OrderExecutionResult,
    *,
    broker: str = "alpaca",
    execution_mode: str = "paper",
):
    return build_trade_notification_request(
        decision=_candidate_decision(),
        order_proposal=_proposal(),
        order_result=order_result,
        run_id="scheduled:2026-06-03",
        decision_id="decision-001",
        decision_index=0,
        broker=broker,
        execution_mode=execution_mode,
    )


def test_execution_statuses_map_to_notification_event_types() -> None:
    cases = [
        (
            _order_result(BrokerOrderStatus.FILLED, filled_qty=1, avg_fill_price=5.15),
            TradeNotificationEventType.ORDER_FILLED,
        ),
        (_order_result(BrokerOrderStatus.OPEN), TradeNotificationEventType.ORDER_SUBMITTED),
        (_order_result(BrokerOrderStatus.SUBMITTED), TradeNotificationEventType.ORDER_SUBMITTED),
        (
            _order_result(BrokerOrderStatus.OPEN, filled_qty=1, avg_fill_price=5.15),
            TradeNotificationEventType.PARTIAL_FILL,
        ),
        (_order_result(BrokerOrderStatus.REJECTED), TradeNotificationEventType.ORDER_REJECTED),
        (_order_result(BrokerOrderStatus.CANCELLED), TradeNotificationEventType.ORDER_CANCELLED),
    ]

    for order_result, expected_event_type in cases:
        request = _request(order_result)
        assert request.event_type == expected_event_type
        assert request.target == "NTNX"
        assert request.expression == "CALL_OPTION"
        assert request.side == "buy"
        assert request.order_id == order_result.order_id


def test_propose_only_result_is_marked_virtual_without_fake_fill() -> None:
    request = _request(
        _order_result(BrokerOrderStatus.OPEN, order_id="propose-only-abc"),
        broker="mock",
        execution_mode="propose_only",
    )

    assert request.event_type == TradeNotificationEventType.ORDER_SUBMITTED
    assert request.execution_mode == "propose_only"
    assert request.is_virtual_execution is True
    assert "virtual" in request.message.lower()
    assert request.filled_quantity == 0


def test_notification_message_contains_compact_trade_context() -> None:
    request = _request(
        _order_result(BrokerOrderStatus.FILLED, filled_qty=1, avg_fill_price=5.15)
    )

    assert "NTNX" in request.message
    assert "CALL_OPTION" in request.message
    assert "buy" in request.message
    assert "filled=1" in request.message
    assert "avg=5.15" in request.message
    assert "alpaca" in request.message
    assert "paper" in request.message
    assert "candidate_ready_for_analyst" in request.message
    assert "scheduled:2026-06-03" in request.message
    assert "decision-001" in request.message
    assert "order-123" in request.message


def test_dispatch_uses_adapter_when_channel_configured() -> None:
    adapter = InMemoryNotificationAdapter()
    request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))

    result = dispatch_trade_notification(
        request,
        adapter=adapter,
        settings=TradeNotificationSettings(
            channel=NotificationChannel.IN_MEMORY,
            rely_on_robinhood_native_notifications=False,
        ),
    )

    assert result.delivery_status == NotificationDeliveryStatus.SENT
    assert adapter.sent_requests == [request]
    assert result.message == request.message


def test_robinhood_native_notification_suppresses_external_adapter_by_default() -> None:
    adapter = InMemoryNotificationAdapter()
    request = _request(
        _order_result(BrokerOrderStatus.FILLED, filled_qty=1, broker="robinhood"),
        broker="robinhood",
        execution_mode="live",
    )

    result = dispatch_trade_notification(request, adapter=adapter)

    assert result.delivery_status == (
        NotificationDeliveryStatus.SUPPRESSED_NATIVE_BROKER_NOTIFICATION_EXPECTED
    )
    assert adapter.sent_requests == []
    assert result.delivery_channel == NotificationChannel.BROKER_NATIVE


def test_robinhood_native_notification_can_be_disabled() -> None:
    adapter = InMemoryNotificationAdapter()
    request = _request(
        _order_result(BrokerOrderStatus.FILLED, filled_qty=1, broker="robinhood"),
        broker="robinhood",
        execution_mode="live",
    )

    result = dispatch_trade_notification(
        request,
        adapter=adapter,
        settings=TradeNotificationSettings(
            channel=NotificationChannel.IN_MEMORY,
            rely_on_robinhood_native_notifications=False,
        ),
    )

    assert result.delivery_status == NotificationDeliveryStatus.SENT
    assert adapter.sent_requests == [request]


def test_missing_adapter_returns_skipped_without_channel_configured() -> None:
    request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))

    result = dispatch_trade_notification(request, adapter=None)

    assert result.delivery_status == NotificationDeliveryStatus.SKIPPED_NO_CHANNEL_CONFIGURED
    assert result.error_type is None


class FailingNotificationAdapter:
    def send_trade_notification(self, request):
        raise RuntimeError("provider returned api_key=secret")


def test_adapter_failure_returns_safe_failed_result_without_mutating_request() -> None:
    request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))
    before = request.model_dump(mode="json")

    result = dispatch_trade_notification(
        request,
        adapter=FailingNotificationAdapter(),
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
    )

    assert result.delivery_status == NotificationDeliveryStatus.FAILED
    assert result.error_type == NotificationErrorType.ADAPTER_ERROR
    assert "api_key" not in result.model_dump_json()
    assert request.model_dump(mode="json") == before


def test_duplicate_event_key_suppresses_duplicate_delivery() -> None:
    adapter = InMemoryNotificationAdapter()
    processed: set[str] = set()
    request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))

    first = dispatch_trade_notification(
        request,
        adapter=adapter,
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        processed_notification_keys=processed,
    )
    second = dispatch_trade_notification(
        request,
        adapter=adapter,
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
        processed_notification_keys=processed,
    )

    assert first.delivery_status == NotificationDeliveryStatus.SENT
    assert second.delivery_status == NotificationDeliveryStatus.DUPLICATE_SUPPRESSED
    assert adapter.sent_requests == [request]


def test_same_input_serializes_deterministically() -> None:
    first_request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))
    second_request = _request(_order_result(BrokerOrderStatus.FILLED, filled_qty=1))
    adapter = InMemoryNotificationAdapter()

    first_result = dispatch_trade_notification(
        first_request,
        adapter=adapter,
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
    )
    second_result = dispatch_trade_notification(
        second_request,
        adapter=InMemoryNotificationAdapter(),
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
    )

    assert first_request.model_dump(mode="json") == second_request.model_dump(mode="json")
    assert first_result.model_dump(mode="json") == second_result.model_dump(mode="json")


def test_notification_error_redacts_secret_like_messages() -> None:
    error = NotificationError(
        error_type=NotificationErrorType.ADAPTER_ERROR,
        message="Authorization header leaked token",
    )

    assert "Authorization" not in error.model_dump_json()
    assert "sensitive details were redacted" in error.message
