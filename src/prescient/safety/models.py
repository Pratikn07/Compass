from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KillSwitchStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class KillSwitchActivationSource(StrEnum):
    CLI = "cli"
    API = "api"
    ENVIRONMENT = "environment"
    FILE_SENTINEL = "file_sentinel"
    TEST = "test"


class KillSwitchEventType(StrEnum):
    ACTIVATED = "activated"
    BLOCKED_ORDER = "blocked_order"
    CANCEL_ATTEMPTED = "cancel_attempted"
    CANCEL_SUCCEEDED = "cancel_succeeded"
    CANCEL_FAILED = "cancel_failed"
    RESET = "reset"


class KillSwitchState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: KillSwitchStatus
    activated_at: datetime | None = None
    activated_by: str | None = None
    activation_source: KillSwitchActivationSource | None = None
    reason: str | None = None
    reset_at: datetime | None = None
    reset_by: str | None = None
    reset_reason: str | None = None
    state_version: int = 1
    warnings: list[str] = Field(default_factory=list)

    @field_validator("activated_by", "reason", "reset_by", "reset_reason")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None and value.strip() else None


class KillSwitchEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: KillSwitchEventType
    created_at: datetime
    run_id: str | None = None
    actor: str | None = None
    source: KillSwitchActivationSource
    reason: str | None = None
    order_id: str | None = None
    target: str | None = None
    broker: str | None = None
    message: str
    warnings: list[str] = Field(default_factory=list)

    @field_validator("actor", "reason", "order_id", "target", "broker", "message")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None and value.strip() else value


class KillSwitchActivationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: KillSwitchState
    events: list[KillSwitchEvent] = Field(default_factory=list)
    cancel_attempted_count: int = 0
    cancel_succeeded_count: int = 0
    cancel_failed_count: int = 0
    warnings: list[str] = Field(default_factory=list)
