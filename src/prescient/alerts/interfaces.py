from __future__ import annotations

from typing import Protocol

from prescient.alerts.models import (
    AlertDeliveryResult,
    AlertEvent,
    AlertRecipient,
    NotificationChannel,
    NotificationDeliveryStatus,
    TradeNotificationRequest,
    TradeNotificationResult,
    notification_audit_trail,
)


class NotificationAdapter(Protocol):
    def send_trade_notification(
        self,
        request: TradeNotificationRequest,
    ) -> TradeNotificationResult:
        ...


class InMemoryNotificationAdapter:
    def __init__(self) -> None:
        self.sent_requests: list[TradeNotificationRequest] = []

    def send_trade_notification(
        self,
        request: TradeNotificationRequest,
    ) -> TradeNotificationResult:
        self.sent_requests.append(request)
        return TradeNotificationResult(
            notification_id=request.notification_id,
            notification_key=request.notification_key,
            event_type=request.event_type,
            target=request.target,
            broker=request.broker,
            execution_mode=request.execution_mode,
            order_id=request.order_id,
            decision_id=request.decision_id,
            run_id=request.run_id,
            delivery_channel=NotificationChannel.IN_MEMORY,
            delivery_status=NotificationDeliveryStatus.SENT,
            message=request.message,
            request=request,
            error_type=None,
            error=None,
            audit_trail=notification_audit_trail(request=request),
        )


class AlertAdapter(Protocol):
    def send(self, event: AlertEvent, recipient: AlertRecipient) -> AlertDeliveryResult:
        ...


class AlertFormatter(Protocol):
    def format_text(self, event: AlertEvent) -> str:
        ...

    def format_email_subject(self, event: AlertEvent) -> str:
        ...


class AlertDispatcherProtocol(Protocol):
    def dispatch_records(
        self,
        records: list[object],
        recipients: list[AlertRecipient],
        *,
        dry_run: bool = False,
    ) -> list[AlertDeliveryResult]:
        ...
