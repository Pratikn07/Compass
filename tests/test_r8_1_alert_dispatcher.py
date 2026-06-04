from __future__ import annotations

from datetime import datetime, timezone

from prescient.alerts import (
    AlertAdapter,
    AlertChannelType,
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertDispatcher,
    AlertError,
    AlertErrorType,
    AlertEvent,
    AlertEventType,
    AlertProvider,
    AlertRecipient,
    AlertSeverity,
)


def _event(alert_id: str = "alert-1") -> AlertEvent:
    return AlertEvent(
        alert_id=alert_id,
        event_type=AlertEventType.SETUP_DETECTED,
        severity=AlertSeverity.INFO,
        run_id="run-1",
        decision_id="decision-1",
        journal_record_id="journal-1",
        target="NTNX",
        theme="AI_STORAGE",
        strategy_type="bullish_earnings_readthrough",
        execution_mode="paper",
        title="Setup detected",
        summary="Bullish setup detected.",
        created_at=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
    )


def _recipient(
    label: str,
    provider: AlertProvider,
    channel_type: AlertChannelType,
    *,
    enabled: bool = True,
) -> AlertRecipient:
    return AlertRecipient(
        channel_type=channel_type,
        provider=provider,
        destination_label=label,
        destination=f"dest-{label}",
        enabled=enabled,
    )


def test_dispatcher_sends_to_multiple_channels_and_keeps_failures_isolated() -> None:
    dispatcher = AlertDispatcher(
        adapters={
            AlertProvider.TELEGRAM: RecordingAdapter(AlertProvider.TELEGRAM),
            AlertProvider.DISCORD: RecordingAdapter(
                AlertProvider.DISCORD,
                error=AlertError(
                    provider=AlertProvider.DISCORD,
                    error_type=AlertErrorType.RATE_LIMITED,
                    message="429 rate limited",
                    retryable=True,
                ),
            ),
        }
    )
    recipients = [
        _recipient("telegram", AlertProvider.TELEGRAM, AlertChannelType.TELEGRAM),
        _recipient("discord", AlertProvider.DISCORD, AlertChannelType.DISCORD),
    ]

    results = dispatcher.dispatch([_event()], recipients)

    assert [result.status for result in results] == [
        AlertDeliveryStatus.SENT,
        AlertDeliveryStatus.FAILED,
    ]
    assert results[1].errors[0].retryable is True


def test_dispatcher_dedupes_by_alert_id_and_destination_and_skips_disabled() -> None:
    adapter = RecordingAdapter(AlertProvider.TELEGRAM)
    dispatcher = AlertDispatcher(adapters={AlertProvider.TELEGRAM: adapter})
    recipient = _recipient("telegram", AlertProvider.TELEGRAM, AlertChannelType.TELEGRAM)
    disabled = _recipient(
        "disabled",
        AlertProvider.TELEGRAM,
        AlertChannelType.TELEGRAM,
        enabled=False,
    )

    results = dispatcher.dispatch([_event(), _event()], [recipient, disabled])

    assert [result.status for result in results] == [
        AlertDeliveryStatus.SENT,
        AlertDeliveryStatus.SKIPPED,
    ]
    assert len(adapter.calls) == 1


def test_dispatcher_dry_run_does_not_call_adapters() -> None:
    adapter = RecordingAdapter(AlertProvider.TELEGRAM)
    dispatcher = AlertDispatcher(adapters={AlertProvider.TELEGRAM: adapter})

    results = dispatcher.dispatch(
        [_event()],
        [_recipient("telegram", AlertProvider.TELEGRAM, AlertChannelType.TELEGRAM)],
        dry_run=True,
    )

    assert results[0].status == AlertDeliveryStatus.DRY_RUN
    assert adapter.calls == []


class RecordingAdapter(AlertAdapter):
    def __init__(
        self,
        provider: AlertProvider,
        *,
        error: AlertError | None = None,
    ) -> None:
        self.provider = provider
        self.error = error
        self.calls: list[tuple[AlertEvent, AlertRecipient]] = []

    def send(
        self,
        event: AlertEvent,
        recipient: AlertRecipient,
    ) -> AlertDeliveryResult:
        self.calls.append((event, recipient))
        if self.error is not None:
            return AlertDeliveryResult(
                alert_id=event.alert_id,
                provider=self.provider,
                channel_type=recipient.channel_type,
                destination_label=recipient.destination_label,
                status=AlertDeliveryStatus.FAILED,
                errors=[self.error],
            )
        return AlertDeliveryResult(
            alert_id=event.alert_id,
            provider=self.provider,
            channel_type=recipient.channel_type,
            destination_label=recipient.destination_label,
            status=AlertDeliveryStatus.SENT,
        )
