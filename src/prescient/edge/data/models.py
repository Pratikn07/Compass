from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ReportTime = Literal["BMO", "AMC", "UNKNOWN"]


def _norm_ticker(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("Ticker must not be empty.")
    return cleaned


def _norm_report_time(value: str) -> str:
    cleaned = str(value).strip().upper()
    return cleaned if cleaned in ("BMO", "AMC", "UNKNOWN") else "UNKNOWN"


class EarningsAnnouncement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    report_date: date
    report_time: ReportTime = "UNKNOWN"
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)

    @field_validator("report_time", mode="before")
    @classmethod
    def normalize_report_time(cls, value: str) -> str:
        return _norm_report_time(value)


class AssembledEdgeDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # event_contexts and dataset hold edge types; kept as objects to avoid importing
    # frozen scoring models into this layer's public schema.
    event_contexts: list[object]
    dataset: object
    events_total: int
    events_dropped: int
    drop_reasons: dict[str, int]
    errors: list[str]
