from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    SourceCitation,
    audit_trail,
    internal_rule_citation,
)
from prescient.signal.models import StrategyStatus


_UNSAFE_TEXT_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\b|secret|credential|account[_-]?id|"
    r"account[_-]?number|raw[_-]?payload|raw[_-]?prompt|webhook|bot[_-]?token|"
    r"buying[_-]?power|balance)",
    re.IGNORECASE,
)


class TradeNotificationEventType(StrEnum):
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    PARTIAL_FILL = "partial_fill"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"


class NotificationDeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED_NATIVE_BROKER_NOTIFICATION_EXPECTED = (
        "suppressed_native_broker_notification_expected"
    )
    SKIPPED_NO_CHANNEL_CONFIGURED = "skipped_no_channel_configured"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"


class NotificationErrorType(StrEnum):
    ADAPTER_ERROR = "adapter_error"
    MESSAGE_UNSAFE = "message_unsafe"


class NotificationChannel(StrEnum):
    IN_MEMORY = "in_memory"
    BROKER_NATIVE = "broker_native"
    PUSH = "push"


class TradeNotificationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: NotificationChannel | None = None
    rely_on_robinhood_native_notifications: bool = True
    dedupe_enabled: bool = True


class NotificationError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    error_type: NotificationErrorType
    message: str
    retryable: bool = False

    @field_validator("message")
    @classmethod
    def redact_sensitive_message(cls, value: str) -> str:
        return safe_alert_text(value)


class TradeNotificationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    notification_id: str
    notification_key: str
    event_type: TradeNotificationEventType
    target: str
    theme: str | None = None
    broker: str
    execution_mode: str
    strategy_status: StrategyStatus
    recommended_expression: str | None = None
    expression: str
    side: str = "buy"
    quantity: int | None = None
    filled_quantity: int = 0
    limit_price: float | None = None
    average_fill_price: float | None = None
    order_id: str
    run_id: str
    decision_id: str
    decision_index: int
    is_virtual_execution: bool = False
    message: str
    source_citations: list[SourceCitation] = Field(default_factory=list)
    audit_trail: DecisionAuditTrail

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("broker", "execution_mode", "side")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("recommended_expression", "expression", "order_id", "run_id", "decision_id")
    @classmethod
    def validate_safe_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Notification text fields cannot be blank.")
        if _UNSAFE_TEXT_PATTERN.search(stripped):
            raise ValueError("Notification text contains unsafe content.")
        return stripped

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, value: str) -> str:
        return safe_alert_text(value.strip())

    @model_validator(mode="after")
    def validate_notification_identity(self) -> "TradeNotificationRequest":
        expected_id = deterministic_notification_id(self.notification_key)
        if self.notification_id != expected_id:
            raise ValueError("Notification ID must be deterministic from notification key.")
        return self


class TradeNotificationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    notification_id: str
    notification_key: str
    event_type: TradeNotificationEventType
    target: str
    broker: str
    execution_mode: str
    order_id: str
    decision_id: str
    run_id: str
    delivery_channel: NotificationChannel | None
    delivery_status: NotificationDeliveryStatus
    message: str
    request: TradeNotificationRequest
    error_type: NotificationErrorType | None = None
    error: NotificationError | None = None
    audit_trail: DecisionAuditTrail

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("broker", "execution_mode")
    @classmethod
    def normalize_lowercase(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, value: str) -> str:
        return safe_alert_text(value.strip())

    @model_validator(mode="after")
    def validate_failure_contract(self) -> "TradeNotificationResult":
        if self.delivery_status == NotificationDeliveryStatus.FAILED and self.error is None:
            raise ValueError("Failed notification results must include a structured error.")
        if self.error is not None and self.error_type != self.error.error_type:
            raise ValueError("Notification error_type must match the structured error.")
        return self


def deterministic_notification_key(
    *,
    broker: str,
    order_id: str,
    event_type: TradeNotificationEventType,
    status: str,
    filled_quantity: int,
    execution_mode: str,
) -> str:
    return "|".join(
        [
            broker.strip().lower(),
            order_id.strip(),
            event_type.value,
            status.strip().lower(),
            str(filled_quantity),
            execution_mode.strip().lower(),
        ]
    )


def deterministic_notification_id(notification_key: str) -> str:
    digest = hashlib.sha256(notification_key.encode("utf-8")).hexdigest()
    return f"ntf_{digest}"


def notification_audit_trail(
    *,
    request: TradeNotificationRequest | None = None,
    target: str | None = None,
    theme: str | None = None,
    run_id: str | None = None,
    decision_id: str | None = None,
    order_id: str | None = None,
    source_citations: list[SourceCitation] | None = None,
    seed: str | None = None,
) -> DecisionAuditTrail:
    active_target = request.target if request is not None else target
    active_theme = request.theme if request is not None else theme
    active_run_id = request.run_id if request is not None else run_id
    active_decision_id = request.decision_id if request is not None else decision_id
    active_order_id = request.order_id if request is not None else order_id
    rule = internal_rule_citation("alert-trade-notification")
    return audit_trail(
        decision_type=DecisionType.TRADE_NOTIFICATION,
        decision_layer=DecisionLayer.ALERTS,
        target=active_target,
        theme=active_theme,
        run_id=active_run_id,
        parent_decision_ids=[active_decision_id] if active_decision_id else [],
        related_order_ids=[active_order_id] if active_order_id else [],
        source_citations=[rule, *(source_citations or [])],
        seed=seed or (request.notification_key if request is not None else active_order_id),
    )


def safe_alert_text(value: str) -> str:
    if _UNSAFE_TEXT_PATTERN.search(value):
        return "Notification text redacted because sensitive details were redacted."
    return value


def _safe_alert_error_text(value: str) -> str:
    if _UNSAFE_TEXT_PATTERN.search(value):
        return "Provider returned an alert error; sensitive details were redacted."
    return value


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


class AlertEventType(StrEnum):
    SETUP_DETECTED = "setup_detected"
    SETUP_BLOCKED = "setup_blocked"
    DAILY_HALT_ACTIVE = "daily_halt_active"
    TRADE_PROPOSED = "trade_proposed"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    TRADE_EXITED = "trade_exited"
    TRADE_OUTCOME_RECORDED = "trade_outcome_recorded"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannelType(StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"


class AlertProvider(StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"


class AlertDeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class AlertErrorType(StrEnum):
    MISSING_CREDENTIALS = "missing_credentials"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    PAYMENT_REQUIRED = "payment_required"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK_UNAVAILABLE = "network_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    RECIPIENT_UNAVAILABLE = "recipient_unavailable"
    MESSAGE_TOO_LONG = "message_too_long"
    INVALID_FORMATTING = "invalid_formatting"
    UNKNOWN = "unknown"


class AlertError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: AlertProvider
    error_type: AlertErrorType
    message: str
    retryable: bool = False
    source: str | None = None

    @field_validator("message")
    @classmethod
    def redact_provider_details(cls, value: str) -> str:
        return safe_provider_error_text(value)

    @field_validator("source")
    @classmethod
    def redact_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return safe_provider_error_text(value)


class AlertRecipient(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_type: AlertChannelType
    provider: AlertProvider
    destination_label: str
    destination: str
    enabled: bool = True

    @field_validator("destination_label")
    @classmethod
    def normalize_destination_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Alert recipient destination_label is required.")
        return normalized

    @field_validator("destination")
    @classmethod
    def normalize_destination(cls, value: str) -> str:
        return value.strip()


class AlertEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: str
    event_type: AlertEventType
    severity: AlertSeverity
    run_id: str
    decision_id: str
    journal_record_id: str
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    execution_mode: str | None = None
    title: str
    summary: str
    created_at: datetime
    order_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("alert_id", "run_id", "decision_id", "journal_record_id", "title")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Alert event text fields cannot be blank.")
        return normalized

    @field_validator("summary")
    @classmethod
    def redact_unsafe_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Alert event summary is required.")
        return safe_provider_error_text(normalized)

    @field_validator("strategy_type", "execution_mode", "order_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AlertDeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alert_id: str
    provider: AlertProvider
    channel_type: AlertChannelType
    destination_label: str
    status: AlertDeliveryStatus
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    errors: list[AlertError] = Field(default_factory=list)

    @classmethod
    def dry_run(
        cls,
        *,
        alert_id: str,
        provider: AlertProvider,
        channel_type: AlertChannelType,
        destination_label: str,
    ) -> "AlertDeliveryResult":
        return cls(
            alert_id=alert_id,
            provider=provider,
            channel_type=channel_type,
            destination_label=destination_label,
            status=AlertDeliveryStatus.DRY_RUN,
        )

    @model_validator(mode="after")
    def validate_failure_contract(self) -> "AlertDeliveryResult":
        if self.status == AlertDeliveryStatus.FAILED and not self.errors:
            raise ValueError("Failed alert delivery results must include structured errors.")
        return self


def deterministic_alert_id(
    *,
    event_type: AlertEventType,
    run_id: str,
    decision_id: str,
    journal_record_id: str,
) -> str:
    seed = {
        "event_type": event_type.value,
        "run_id": run_id,
        "decision_id": decision_id,
        "journal_record_id": journal_record_id,
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True).encode("utf-8")).hexdigest()
    return f"alert_{digest[:24]}"


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def safe_provider_error_text(value: str) -> str:
    if _UNSAFE_TEXT_PATTERN.search(value):
        return "Provider returned an alert error; sensitive details were redacted."
    return value


def error_from_exception(
    *,
    provider: AlertProvider,
    exc: Exception,
    source: str,
) -> AlertError:
    error_type = AlertErrorType.UNKNOWN
    retryable = False
    class_name = exc.__class__.__name__.lower()
    if "timeout" in class_name:
        error_type = AlertErrorType.TIMEOUT
        retryable = True
    elif "connect" in class_name or "network" in class_name:
        error_type = AlertErrorType.NETWORK_UNAVAILABLE
        retryable = True
    return AlertError(
        provider=provider,
        error_type=error_type,
        message=str(exc) or exc.__class__.__name__,
        retryable=retryable,
        source=source,
    )
