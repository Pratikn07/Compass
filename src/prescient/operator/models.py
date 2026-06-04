from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prescient.risk.models import ExecutionMode
from prescient.safety.models import KillSwitchState


class ModeAuthorizationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ModeAuthorizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_mode: ExecutionMode
    actor: str
    reason: str
    confirmation_text: str | None = None

    @field_validator("actor", "reason", "confirmation_text")
    @classmethod
    def clean_text(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned and info.field_name in {"actor", "reason"}:
            raise ValueError(f"{info.field_name} is required.")
        return cleaned or None


class ModeAuthorizationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ModeAuthorizationStatus
    requested_mode: ExecutionMode
    previous_mode: ExecutionMode
    active_mode: ExecutionMode
    actor: str
    reason: str
    created_at: datetime
    rejection_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OperatorStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_mode: ExecutionMode
    mode_source: str
    kill_switch: KillSwitchState
    latest_mode_authorization: ModeAuthorizationResult | None = None
    warnings: list[str] = Field(default_factory=list)
