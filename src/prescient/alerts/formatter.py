from __future__ import annotations

from prescient.alerts.models import (
    AlertEvent,
    TradeNotificationEventType,
    TradeNotificationRequest,
    deterministic_notification_id,
    deterministic_notification_key,
    notification_audit_trail,
)
from prescient.broker.models import BrokerOrderStatus, OrderExecutionResult
from prescient.journal import merge_source_citations
from prescient.risk.models import RiskOrderProposal
from prescient.signal.models import StrategyDecision


def build_trade_notification_request(
    *,
    decision: StrategyDecision,
    order_proposal: RiskOrderProposal,
    order_result: OrderExecutionResult,
    run_id: str,
    decision_id: str,
    decision_index: int,
    broker: str,
    execution_mode: str,
) -> TradeNotificationRequest:
    target, theme = _target_and_theme(decision)
    active_broker = (order_result.broker or broker).strip().lower()
    active_execution_mode = execution_mode.strip().lower()
    event_type = _event_type(order_result)
    is_virtual = (
        active_execution_mode == "propose_only"
        or order_result.order_id.startswith("propose-only-")
    )
    notification_key = deterministic_notification_key(
        broker=active_broker,
        order_id=order_result.order_id,
        event_type=event_type,
        status=order_result.status.value,
        filled_quantity=order_result.filled_qty,
        execution_mode=active_execution_mode,
    )
    source_citations = merge_source_citations(
        decision.audit_trail.source_citations,
        order_result.source_citations,
        order_result.audit_trail.source_citations,
    )
    message = _message(
        event_type=event_type,
        target=target,
        expression=order_proposal.expression,
        side="buy",
        filled_quantity=order_result.filled_qty,
        average_fill_price=order_result.avg_fill_price,
        broker=active_broker,
        execution_mode=active_execution_mode,
        strategy_status=decision.status.value,
        run_id=run_id,
        decision_id=decision_id,
        order_id=order_result.order_id,
        is_virtual=is_virtual,
    )
    return TradeNotificationRequest(
        notification_id=deterministic_notification_id(notification_key),
        notification_key=notification_key,
        event_type=event_type,
        target=target,
        theme=theme,
        broker=active_broker,
        execution_mode=active_execution_mode,
        strategy_status=decision.status,
        recommended_expression=(
            decision.candidate.recommended_expression if decision.candidate is not None else None
        ),
        expression=order_proposal.expression,
        side="buy",
        quantity=order_result.filled_qty if order_result.filled_qty > 0 else None,
        filled_quantity=order_result.filled_qty,
        limit_price=order_proposal.estimated_entry_cost,
        average_fill_price=order_result.avg_fill_price,
        order_id=order_result.order_id,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        is_virtual_execution=is_virtual,
        message=message,
        source_citations=source_citations,
        audit_trail=notification_audit_trail(
            target=target,
            theme=theme,
            run_id=run_id,
            decision_id=decision_id,
            order_id=order_result.order_id,
            source_citations=source_citations,
            seed=notification_key,
        ),
    )


def _event_type(order_result: OrderExecutionResult) -> TradeNotificationEventType:
    if order_result.status == BrokerOrderStatus.REJECTED:
        return TradeNotificationEventType.ORDER_REJECTED
    if order_result.status == BrokerOrderStatus.CANCELLED:
        return TradeNotificationEventType.ORDER_CANCELLED
    if order_result.status == BrokerOrderStatus.FILLED:
        return TradeNotificationEventType.ORDER_FILLED
    if (
        order_result.status in {BrokerOrderStatus.OPEN, BrokerOrderStatus.SUBMITTED}
        and order_result.filled_qty > 0
    ):
        return TradeNotificationEventType.PARTIAL_FILL
    return TradeNotificationEventType.ORDER_SUBMITTED


def _message(
    *,
    event_type: TradeNotificationEventType,
    target: str,
    expression: str,
    side: str,
    filled_quantity: int,
    average_fill_price: float | None,
    broker: str,
    execution_mode: str,
    strategy_status: str,
    run_id: str,
    decision_id: str,
    order_id: str,
    is_virtual: bool,
) -> str:
    virtual = " virtual" if is_virtual else ""
    parts = [
        f"{event_type.value}{virtual}",
        target,
        expression,
        side,
        f"filled={filled_quantity}",
    ]
    if average_fill_price is not None:
        parts.append(f"avg={average_fill_price:g}")
    parts.extend(
        [
            f"broker={broker}",
            f"mode={execution_mode}",
            f"strategy={strategy_status}",
            f"run={run_id}",
            f"decision={decision_id}",
            f"order={order_id}",
        ]
    )
    return " | ".join(parts)


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme
    return decision.audit.target, decision.audit.theme


class PlainTextAlertFormatter:
    def __init__(self, *, max_chars: int | None = None) -> None:
        self.max_chars = max_chars

    def format_text(self, event: AlertEvent) -> str:
        lines = [
            event.title,
            event.summary,
            "",
            f"Event: {event.event_type.value}",
            f"Severity: {event.severity.value}",
            f"Target: {event.target or 'UNKNOWN'}",
        ]
        if event.theme:
            lines.append(f"Theme: {event.theme}")
        if event.strategy_type:
            lines.append(f"Strategy: {event.strategy_type}")
        if event.execution_mode:
            lines.append(f"Mode: {event.execution_mode}")
        if event.order_id:
            lines.append(f"Order: {event.order_id}")
        lines.extend(
            [
                f"Run: {event.run_id}",
                f"Decision: {event.decision_id}",
                f"Journal: {event.journal_record_id}",
            ]
        )
        if event.source_citations:
            lines.append(f"Sources: {len(event.source_citations)}")

        text = "\n".join(lines)
        if self.max_chars is not None:
            return _truncate(text, self.max_chars)
        return text

    def format_email_subject(self, event: AlertEvent) -> str:
        target = event.target or "UNKNOWN"
        mode = event.execution_mode or "unknown"
        return f"{event.event_type.name} {target} {mode}"


def _truncate(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    marker = "... [truncated]"
    if max_chars <= len(marker):
        return value[:max_chars]
    return value[: max_chars - len(marker)] + marker
