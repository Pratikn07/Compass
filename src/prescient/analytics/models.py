from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetricsEvaluationStatus(StrEnum):
    EVALUABLE = "evaluable"
    NOT_EVALUABLE = "not_evaluable"


class PerformanceObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    ticker: str
    entry_date: date
    exit_date: date
    allocated_capital: float
    strategy_net_pnl: float | None = None
    benchmark_entry_price: float | None = None
    benchmark_exit_price: float | None = None

    @field_validator("observation_id")
    @classmethod
    def require_observation_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Performance observation ID must not be empty.")
        return cleaned

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Performance observation ticker must not be empty.")
        return cleaned


class PerformanceAnalyticsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: list[PerformanceObservation] = Field(default_factory=list)
    starting_equity: float = 10_000.0
    annual_risk_free_rate: float = 0.0
    periods_per_year: int = 252


class PerformanceMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MetricsEvaluationStatus
    total_observation_count: int = 0
    closed_evaluable_outcome_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    flat_count: int = 0
    win_rate: float | None = None
    total_net_pnl: float | None = None
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_drawdown_status: MetricsEvaluationStatus = MetricsEvaluationStatus.NOT_EVALUABLE
    sharpe_ratio: float | None = None
    sharpe_status: MetricsEvaluationStatus = MetricsEvaluationStatus.NOT_EVALUABLE
    daily_return_count: int = 0
    excluded_counts: dict[str, int] = Field(default_factory=dict)


class BuyHoldBenchmark(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MetricsEvaluationStatus
    observation_count: int = 0
    total_net_pnl: float | None = None
    total_return_pct: float | None = None
    excluded_counts: dict[str, int] = Field(default_factory=dict)


class BenchmarkComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MetricsEvaluationStatus
    strategy_total_return_pct: float | None = None
    buy_hold_total_return_pct: float | None = None
    excess_return_pct: float | None = None
    beats_buy_and_hold: bool | None = None
    benchmark_status: MetricsEvaluationStatus = MetricsEvaluationStatus.NOT_EVALUABLE
    strategy_metrics: PerformanceMetrics
    buy_hold_benchmark: BuyHoldBenchmark
    excluded_counts: dict[str, int] = Field(default_factory=dict)
