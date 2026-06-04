from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prescient.runtime import PipelineRunResult


class ScheduleTriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    CATCH_UP = "catch_up"


class ScheduledRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    trigger_type: ScheduleTriggerType
    scheduled_date: date
    current_date: date
    window_start: date
    window_end: date
    relevant_tickers: list[str] = Field(default_factory=list)

    @field_validator("relevant_tickers")
    @classmethod
    def normalize_relevant_tickers(cls, values: list[str]) -> list[str]:
        return sorted({ticker.strip().upper() for ticker in values if ticker.strip()})


class ScheduledRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    trigger_type: ScheduleTriggerType
    scheduled_date: date
    current_date: date
    window_start: date
    window_end: date
    upcoming_event_count: int
    total_decision_count: int
    candidate_ready_count: int
    rejected_count: int
    no_trade_count: int
    journal_path: str | None
    claude_analysis_enabled: bool


class ScheduledPipelineRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ScheduledRunRequest
    runtime_result: PipelineRunResult
    summary: ScheduledRunSummary
