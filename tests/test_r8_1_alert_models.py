from __future__ import annotations

from datetime import datetime, timezone

from prescient.alerts import (
    AlertChannelType,
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertError,
    AlertErrorType,
    AlertEvent,
    AlertEventType,
    AlertProvider,
    AlertSeverity,
    deterministic_alert_id,
)


def test_alert_event_normalizes_target_theme_and_uses_deterministic_id() -> None:
    first_id = deterministic_alert_id(
        event_type=AlertEventType.SETUP_DETECTED,
        run_id="scheduled:2026-06-03",
        decision_id="decision-1",
        journal_record_id="journal-1",
    )
    second_id = deterministic_alert_id(
        event_type=AlertEventType.SETUP_DETECTED,
        run_id="scheduled:2026-06-03",
        decision_id="decision-1",
        journal_record_id="journal-1",
    )

    event = AlertEvent(
        alert_id=first_id,
        event_type=AlertEventType.SETUP_DETECTED,
        severity=AlertSeverity.INFO,
        run_id="scheduled:2026-06-03",
        decision_id="decision-1",
        journal_record_id="journal-1",
        target="ntnx",
        theme="ai_storage",
        strategy_type="bullish_earnings_readthrough",
        execution_mode="paper",
        title="Setup detected",
        summary="Bullish setup detected.",
        created_at=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
    )

    assert first_id == second_id
    assert first_id.startswith("alert_")
    assert event.target == "NTNX"
    assert event.theme == "AI_STORAGE"
    assert event.model_dump(mode="json")["event_type"] == "setup_detected"


def test_alert_error_redacts_secret_like_provider_details() -> None:
    error = AlertError(
        provider=AlertProvider.DISCORD,
        error_type=AlertErrorType.UNAUTHORIZED,
        message="401 Authorization bearer abc webhook_url=https://discord.test/token",
        retryable=False,
        source="adapter",
    )

    serialized = error.model_dump_json().lower()
    assert "abc" not in serialized
    assert "authorization" not in serialized
    assert "webhook" not in serialized
    assert "provider returned an alert error" in serialized


def test_dry_run_delivery_result_shape_is_journal_safe() -> None:
    result = AlertDeliveryResult.dry_run(
        alert_id="alert_123",
        provider=AlertProvider.TELEGRAM,
        channel_type=AlertChannelType.TELEGRAM,
        destination_label="ops",
    )

    assert result.status == AlertDeliveryStatus.DRY_RUN
    assert result.provider == AlertProvider.TELEGRAM
    assert result.destination_label == "ops"
    assert result.errors == []

