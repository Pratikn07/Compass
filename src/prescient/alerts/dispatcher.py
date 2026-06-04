from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from prescient.alerts.builder import build_alert_events
from prescient.alerts.interfaces import AlertAdapter, NotificationAdapter
from prescient.alerts.models import (
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertError,
    AlertErrorType,
    AlertEvent,
    AlertProvider,
    AlertRecipient,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationError,
    NotificationErrorType,
    TradeNotificationRequest,
    TradeNotificationResult,
    TradeNotificationSettings,
    notification_audit_trail,
)


_DEFAULT_SETTINGS = TradeNotificationSettings()


def dispatch_trade_notification(
    request: TradeNotificationRequest,
    *,
    adapter: NotificationAdapter | None = None,
    settings: TradeNotificationSettings = _DEFAULT_SETTINGS,
    processed_notification_keys: set[str] | None = None,
) -> TradeNotificationResult:
    if (
        settings.dedupe_enabled
        and processed_notification_keys is not None
        and request.notification_key in processed_notification_keys
    ):
        return _result(
            request,
            delivery_channel=settings.channel,
            delivery_status=NotificationDeliveryStatus.DUPLICATE_SUPPRESSED,
        )

    if settings.dedupe_enabled and processed_notification_keys is not None:
        processed_notification_keys.add(request.notification_key)

    if (
        settings.rely_on_robinhood_native_notifications
        and request.broker == "robinhood"
    ):
        return _result(
            request,
            delivery_channel=NotificationChannel.BROKER_NATIVE,
            delivery_status=(
                NotificationDeliveryStatus.SUPPRESSED_NATIVE_BROKER_NOTIFICATION_EXPECTED
            ),
        )

    if adapter is None:
        return _result(
            request,
            delivery_channel=settings.channel,
            delivery_status=NotificationDeliveryStatus.SKIPPED_NO_CHANNEL_CONFIGURED,
        )

    try:
        return adapter.send_trade_notification(request)
    except Exception as exc:
        error = NotificationError(
            error_type=NotificationErrorType.ADAPTER_ERROR,
            message=str(exc),
            retryable=False,
        )
        return _result(
            request,
            delivery_channel=settings.channel,
            delivery_status=NotificationDeliveryStatus.FAILED,
            error=error,
        )


def _result(
    request: TradeNotificationRequest,
    *,
    delivery_channel: NotificationChannel | None,
    delivery_status: NotificationDeliveryStatus,
    error: NotificationError | None = None,
) -> TradeNotificationResult:
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
        delivery_channel=delivery_channel,
        delivery_status=delivery_status,
        message=request.message,
        request=request,
        error_type=error.error_type if error is not None else None,
        error=error,
        audit_trail=notification_audit_trail(request=request),
    )


class AlertDispatcher:
    def __init__(self, *, adapters: Mapping[AlertProvider, AlertAdapter]) -> None:
        self.adapters = dict(adapters)

    def dispatch_records(
        self,
        records: Iterable[object],
        recipients: Sequence[AlertRecipient],
        *,
        dry_run: bool = False,
    ) -> list[AlertDeliveryResult]:
        return self.dispatch(build_alert_events(records), recipients, dry_run=dry_run)

    def dispatch(
        self,
        events: Sequence[AlertEvent],
        recipients: Sequence[AlertRecipient],
        *,
        dry_run: bool = False,
    ) -> list[AlertDeliveryResult]:
        results: list[AlertDeliveryResult] = []
        dispatched_keys: set[tuple[str, str, str, str]] = set()

        for event in events:
            for recipient in recipients:
                key = (
                    event.alert_id,
                    recipient.channel_type.value,
                    recipient.destination_label,
                    recipient.destination,
                )
                if key in dispatched_keys:
                    continue
                dispatched_keys.add(key)

                if not recipient.enabled:
                    results.append(
                        AlertDeliveryResult(
                            alert_id=event.alert_id,
                            provider=recipient.provider,
                            channel_type=recipient.channel_type,
                            destination_label=recipient.destination_label,
                            status=AlertDeliveryStatus.SKIPPED,
                        )
                    )
                    continue

                if dry_run:
                    results.append(
                        AlertDeliveryResult.dry_run(
                            alert_id=event.alert_id,
                            provider=recipient.provider,
                            channel_type=recipient.channel_type,
                            destination_label=recipient.destination_label,
                        )
                    )
                    continue

                adapter = self.adapters.get(recipient.provider)
                if adapter is None:
                    results.append(
                        AlertDeliveryResult(
                            alert_id=event.alert_id,
                            provider=recipient.provider,
                            channel_type=recipient.channel_type,
                            destination_label=recipient.destination_label,
                            status=AlertDeliveryStatus.FAILED,
                            errors=[
                                AlertError(
                                    provider=recipient.provider,
                                    error_type=AlertErrorType.MISSING_CREDENTIALS,
                                    message="No alert adapter configured for provider.",
                                    retryable=False,
                                    source="dispatcher",
                                )
                            ],
                        )
                    )
                    continue

                results.append(adapter.send(event, recipient))

        return results
