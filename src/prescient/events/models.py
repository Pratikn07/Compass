from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prescient.runtime.models import PipelineRunResult


PayloadValue = str | int | float | bool | None


class EventSourceType(StrEnum):
    WEBSOCKET = "websocket"
    WEBHOOK = "webhook"
    FAST_POLL = "fast_poll"
    MANUAL = "manual"


class MarketEventType(StrEnum):
    EARNINGS_RESULT = "earnings_result"
    GUIDANCE_UPDATE = "guidance_update"
    MAJOR_NEWS = "major_news"
    PRICE_MOVE = "price_move"
    VOLUME_SPIKE = "volume_spike"
    OPTIONS_LIQUIDITY_CHANGE = "options_liquidity_change"
    QUOTE = "quote"
    UNSUPPORTED = "unsupported"


class EventImportance(StrEnum):
    IGNORED = "ignored"
    JOURNAL_ONLY = "journal_only"
    STRATEGY_REFRESH = "strategy_refresh"
    CANDIDATE_REVIEW = "candidate_review"


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: str
    source_type: EventSourceType
    event_type: MarketEventType
    ticker: str | None
    source_name: str
    payload_summary: dict[str, PayloadValue] = Field(default_factory=dict)
    event_time: datetime | None = None
    received_time: datetime | None = None
    event_id: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None and value.strip() else None


class EventClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: str
    source_type: EventSourceType
    event_type: MarketEventType
    ticker: str | None
    theme: str | None
    is_relevant: bool
    importance: EventImportance
    reason: str
    should_refresh_strategy: bool
    claude_analysis_allowed: bool
    is_duplicate: bool = False

    @field_validator("ticker", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class EventTriggerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    classification: EventClassification
    runtime_result: PipelineRunResult | None = None


class FastPollPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    window_start: datetime
    window_end: datetime
    max_attempts: int
    interval_seconds: int
    max_duration_seconds: int

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("max_attempts", "interval_seconds", "max_duration_seconds")
    @classmethod
    def require_positive_bounds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Fast poll bounds must be positive.")
        return value
