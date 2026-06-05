from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from prescient.runtime.models import DecisionJournalRecord


DEFAULT_STORAGE_SCHEMA_VERSION = 1
_UNSAFE_ERROR_PATTERN = re.compile(
    r"(authorization|bearer\b|service[_-]?role|secret|api[_-]?key|raw[_-]?payload|"
    r"supabase[_-]?service[_-]?role[_-]?key|-----begin)",
    re.IGNORECASE,
)


class StorageWritePolicy(StrEnum):
    OPTIONAL = "optional"
    REQUIRED = "required"


class StorageErrorType(StrEnum):
    MISSING_CREDENTIALS = "missing_credentials"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    PAYMENT_REQUIRED = "payment_required"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    UNAVAILABLE = "unavailable"
    SCHEMA_MISMATCH = "schema_mismatch"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class StorageError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    error_type: StorageErrorType
    message: str
    source: str | None = None

    @field_validator("provider", "source")
    @classmethod
    def normalize_optional_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return _safe_error_text(normalized)

    @field_validator("message")
    @classmethod
    def redact_message(cls, value: str) -> str:
        return _safe_error_text(value.strip())


class StorageWriteRequiredError(RuntimeError):
    def __init__(self, errors: list[StorageError]) -> None:
        self.errors = errors
        providers = sorted({error.provider for error in errors}) or ["unknown"]
        super().__init__(
            "Required storage writes failed for provider(s): " + ", ".join(providers)
        )


class StorageConfigurationError(RuntimeError):
    def __init__(self, error: StorageError) -> None:
        self.error = error
        super().__init__(error.message)


class StorageReadError(RuntimeError):
    def __init__(self, error: StorageError) -> None:
        self.error = error
        super().__init__(error.message)


class StorageWriteResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    records_written: int = 0
    errors: list[StorageError] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_required(self) -> None:
        if self.errors:
            raise StorageWriteRequiredError(self.errors)


class DecisionAttentionStatus(StrEnum):
    NORMAL = "normal"
    NEEDS_ATTENTION = "needs_attention"


class RunStatusRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    trigger_type: str | None = None
    scheduled_date: date | None = None
    current_date: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    schema_version: int = DEFAULT_STORAGE_SCHEMA_VERSION

    @field_validator("run_id", "status")
    @classmethod
    def require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Run status text fields must not be empty.")
        return cleaned

    def to_row(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trigger_type": self.trigger_type,
            "scheduled_date": _format_date(self.scheduled_date),
            "current_date": _format_date(self.current_date),
            "window_start": _format_date(self.window_start),
            "window_end": _format_date(self.window_end),
            "status": self.status,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }


class ProviderSnapshotRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    target: str | None = None
    theme: str | None = None
    source_endpoint: str | None = None
    source_url: str | None = None
    source_id: str | None = None
    as_of: date | None = None
    retrieved_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    schema_version: int = DEFAULT_STORAGE_SCHEMA_VERSION

    @field_validator("provider", "source_endpoint")
    @classmethod
    def normalize_optional_lowercase(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @property
    def provider_snapshot_id(self) -> str:
        endpoint = self.source_endpoint or "unknown"
        source = self.source_id or self.target or "global"
        return f"{self.provider}:{endpoint}:{source}"

    def to_row(self) -> dict[str, Any]:
        created_at = self.created_at or self.retrieved_at or datetime.now(timezone.utc)
        return {
            "provider_snapshot_id": self.provider_snapshot_id,
            "provider": self.provider,
            "target": self.target,
            "theme": self.theme,
            "source_endpoint": self.source_endpoint,
            "source_url": self.source_url,
            "source_id": self.source_id,
            "as_of": _format_date(self.as_of),
            "retrieved_at": _format_datetime(self.retrieved_at)
            if self.retrieved_at is not None
            else None,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(created_at),
        }


class ProviderErrorRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    error_type: str
    run_id: str | None = None
    target: str | None = None
    source: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = DEFAULT_STORAGE_SCHEMA_VERSION

    @field_validator("provider", "error_type", "source")
    @classmethod
    def normalize_optional_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return _safe_error_text(normalized) or None

    @field_validator("target")
    @classmethod
    def normalize_optional_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("message")
    @classmethod
    def redact_message(cls, value: str) -> str:
        return _safe_error_text(value.strip())

    @property
    def provider_error_id(self) -> str:
        run = self.run_id or "global"
        source = self.source or "unknown"
        target = self.target or "global"
        return f"{run}:{self.provider}:{source}:{target}"

    def to_row(self) -> dict[str, Any]:
        return {
            "provider_error_id": self.provider_error_id,
            "provider": self.provider,
            "error_type": self.error_type,
            "run_id": self.run_id,
            "target": self.target,
            "source": self.source,
            "message": self.message,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }


class SystemHealthComponent(StrEnum):
    MARKET_DATA = "market_data"
    PROVIDER_HEALTH = "provider_health"
    PRICING_ENGINE = "pricing_engine"
    RISK_ENGINE = "risk_engine"


class SystemHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class SystemHealthRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    component: SystemHealthComponent
    status: SystemHealthStatus
    detail: str | None = None
    latency_seconds: float | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    schema_version: int = DEFAULT_STORAGE_SCHEMA_VERSION

    @property
    def system_health_id(self) -> str:
        run_part = self.run_id or "global"
        return f"{run_part}:{self.component.value}"

    def to_row(self) -> dict[str, Any]:
        return {
            "system_health_id": self.system_health_id,
            "component": self.component.value,
            "status": self.status.value,
            "detail": self.detail,
            "latency_seconds": self.latency_seconds,
            "run_id": self.run_id,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }


class StorageQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str | None = None
    decision_id: str | None = None
    target: str | None = None
    theme: str | None = None
    record_type: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    limit: int | None = 100

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class StorageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    storage_record_id: str
    record_type: str
    run_id: str
    decision_id: str | None = None
    decision_index: int | None = None
    trading_date: date | None = None
    created_at: datetime
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    strategy_status: str | None = None
    execution_mode: str | None = None
    source: str | None = None
    provider: str | None = None
    order_id: str | None = None
    parent_record_id: str | None = None
    duplicate_of_record_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = DEFAULT_STORAGE_SCHEMA_VERSION

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("record_type", "provider")
    @classmethod
    def normalize_optional_lowercase(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @classmethod
    def from_decision_journal_record(cls, record: DecisionJournalRecord) -> "StorageRecord":
        return cls(
            storage_record_id=record.journal_record_id,
            record_type=record.record_type.value,
            run_id=record.run_id,
            decision_id=record.decision_id,
            decision_index=record.decision_index,
            trading_date=record.trading_date,
            created_at=record.created_at,
            target=record.target,
            theme=record.theme,
            strategy_type=record.strategy_type,
            strategy_status=record.strategy_status,
            execution_mode=record.execution_mode,
            source=record.source,
            order_id=record.order_id,
            parent_record_id=record.parent_record_id,
            duplicate_of_record_id=record.duplicate_of_record_id,
            payload=record.payload,
        )

    def to_journal_record_row(self) -> dict[str, Any]:
        return {
            "journal_record_id": self.storage_record_id,
            "record_type": self.record_type,
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "decision_index": self.decision_index,
            "trading_date": self.trading_date.isoformat()
            if self.trading_date is not None
            else None,
            "created_at": _format_datetime(self.created_at),
            "target": self.target,
            "theme": self.theme,
            "strategy_type": self.strategy_type,
            "strategy_status": self.strategy_status,
            "execution_mode": self.execution_mode,
            "source": self.source,
            "provider": self.provider,
            "order_id": self.order_id,
            "parent_record_id": self.parent_record_id,
            "duplicate_of_record_id": self.duplicate_of_record_id,
            "payload": self.payload,
            "schema_version": self.schema_version,
        }

    def to_run_row(self, *, record_count: int = 1) -> dict[str, Any]:
        trading_date = (
            self.trading_date.isoformat() if self.trading_date is not None else None
        )
        return {
            "run_id": self.run_id,
            "trigger_type": _run_trigger_type(self.run_id),
            "scheduled_date": trading_date,
            "current_date": trading_date,
            "window_start": trading_date,
            "window_end": trading_date,
            "status": "recorded",
            "payload": {
                "source": "storage_projection",
                "execution_mode": self.execution_mode,
                "record_count": record_count,
            },
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }

    def to_decision_record_row(
        self,
        *,
        attention_status: DecisionAttentionStatus = DecisionAttentionStatus.NORMAL,
        attention_reasons: list[str] | None = None,
    ) -> dict[str, Any] | None:
        if self.record_type != "strategy_decision":
            return None
        if self.decision_id is None or self.trading_date is None:
            return None
        return {
            "decision_record_id": self.decision_id,
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "decision_index": self.decision_index,
            "trading_date": self.trading_date.isoformat(),
            "target": self.target,
            "theme": self.theme,
            "strategy_type": self.strategy_type,
            "strategy_status": self.strategy_status,
            "execution_mode": self.execution_mode,
            "attention_status": attention_status.value,
            "attention_reasons": attention_reasons or [],
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _run_trigger_type(run_id: str) -> str | None:
    prefix = run_id.split(":", 1)[0].strip().lower()
    return prefix or None


def _safe_error_text(value: str) -> str:
    if _UNSAFE_ERROR_PATTERN.search(value):
        return "Provider returned a storage error; sensitive details were redacted."
    return value
