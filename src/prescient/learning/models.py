from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LearningTriggerType(StrEnum):
    SCHEDULED_MORNING = "scheduled_morning"
    MANUAL = "manual"
    BACKFILL = "backfill"


class LearningMode(StrEnum):
    REPORT_ONLY = "report_only"
    SHADOW_OVERLAY = "shadow_overlay"
    AUTO_APPLY_SAFE = "auto_apply_safe"


class LearningRecordType(StrEnum):
    STRATEGY_DECISION = "strategy_decision"
    RISK_DECISION = "risk_decision"
    POSITION_SIZING = "position_sizing"
    EXECUTION_PROPOSAL = "execution_proposal"
    ORDER_FILL = "order_fill"
    TRADE_OUTCOME = "trade_outcome"
    DATA_PROVIDER_ERROR = "data_provider_error"
    LEARNING_REPORT = "learning_report"


class OutcomeClassification(StrEnum):
    WIN = "win"
    LOSS = "loss"
    FLAT = "flat"
    OPEN = "open"
    UNKNOWN = "unknown"
    NOT_TRADEABLE = "not_tradeable"


class ParameterProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"
    REVIEW_ONLY = "review_only"
    NO_OP = "no_op"


class ParameterProposalReason(StrEnum):
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    OUTSIDE_ALLOWLIST = "outside_allowlist"
    OUTSIDE_BOUNDS = "outside_bounds"
    DAILY_DELTA_EXCEEDED = "daily_delta_exceeded"
    LIVE_MODE_BLOCKED = "live_mode_blocked"
    SAFETY_PARAMETER_FORBIDDEN = "safety_parameter_forbidden"
    AMBIGUOUS_OUTCOME_DATA = "ambiguous_outcome_data"
    EVIDENCE_SUPPORTED = "evidence_supported"
    DATA_QUALITY_ISSUE = "data_quality_issue"
    CURRENT_VALUE_MISSING = "current_value_missing"


class LearningRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    trigger_type: LearningTriggerType
    run_date: date
    prior_trading_date: date
    lookback_start: date
    lookback_end: date
    journal_paths: list[str] = Field(default_factory=list)
    settings_snapshot_path: str | None = None
    mode: LearningMode = LearningMode.REPORT_ONLY
    execution_mode: str = "paper"
    journal_output_path: str | None = None
    overlay_output_path: str | None = None
    malformed_record_tolerance: int = 0
    allow_overwrite: bool = False

    @field_validator("run_id")
    @classmethod
    def require_run_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Learning run ID must not be empty.")
        return cleaned

    @field_validator("execution_mode")
    @classmethod
    def normalize_execution_mode(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("malformed_record_tolerance")
    @classmethod
    def require_non_negative_tolerance(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Malformed record tolerance cannot be negative.")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "LearningRunRequest":
        if self.lookback_start > self.lookback_end:
            raise ValueError("Learning lookback start cannot be after lookback end.")
        return self


class LearningJournalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_type: LearningRecordType
    run_id: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    trading_date: date | None = None
    created_at: datetime | None = None
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None and value.strip() else None

    @field_validator("run_id", "decision_id", "order_id", "strategy_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None and value.strip() else None


class LearningJournalReadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    records: list[LearningJournalRecord] = Field(default_factory=list)
    records_read: int = 0
    records_skipped: int = 0
    malformed_record_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class LearningJournalReader(Protocol):
    def read_records(
        self,
        *,
        start_date: date,
        end_date: date,
        paths: Sequence[str],
    ) -> LearningJournalReadResult:
        ...


class LearnableParameterPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    min_value: float | int | bool
    max_value: float | int | bool
    max_daily_delta: float | int | None = None
    min_closed_outcomes: int = 10
    min_distinct_trading_days: int = 5
    auto_apply_allowed: bool = False

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Learnable parameter path must not be empty.")
        return cleaned

    @field_validator("min_closed_outcomes", "min_distinct_trading_days")
    @classmethod
    def require_non_negative_gate(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Learning sample gates cannot be negative.")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> "LearnableParameterPolicy":
        if isinstance(self.min_value, bool) or isinstance(self.max_value, bool):
            return self
        if float(self.min_value) > float(self.max_value):
            raise ValueError("Learnable parameter minimum cannot exceed maximum.")
        if self.max_daily_delta is not None and self.max_daily_delta < 0:
            raise ValueError("Maximum daily delta cannot be negative.")
        return self


DEFAULT_LEARNABLE_PARAMETERS: tuple[LearnableParameterPolicy, ...] = (
    LearnableParameterPolicy(
        path="strategy.min_positive_peer_ratio",
        min_value=0.50,
        max_value=0.90,
        max_daily_delta=0.05,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.min_average_peer_score",
        min_value=1.0,
        max_value=3.5,
        max_daily_delta=0.25,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.max_target_runup_pct",
        min_value=5.0,
        max_value=15.0,
        max_daily_delta=1.0,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.peer_result_window_days",
        min_value=7,
        max_value=45,
        max_daily_delta=7,
        min_closed_outcomes=15,
        min_distinct_trading_days=7,
        auto_apply_allowed=False,
    ),
    LearnableParameterPolicy(
        path="strategy.min_reported_peers",
        min_value=2,
        max_value=5,
        max_daily_delta=1,
        min_closed_outcomes=20,
        min_distinct_trading_days=10,
        auto_apply_allowed=False,
    ),
)


DEFAULT_LEARNABLE_PARAMETER_PATHS = {
    policy.path for policy in DEFAULT_LEARNABLE_PARAMETERS
}


FORBIDDEN_AUTO_TUNED_PARAMETER_PATHS = {
    "risk.max_trade_loss_pct",
    "account_size_policy.absolute_trade_loss_pct_ceiling",
    "account_size_policy.tier_default_trade_loss_pct",
    "daily_halt.max_daily_realized_loss_pct",
    "daily_halt.max_losing_trades_per_day",
    "concentration.max_open_positions",
    "concentration.max_single_ticker_exposure_pct",
    "execution_mode",
    "broker.adapter",
    "broker.credentials",
    "broker.api_key",
    "order.quantity",
    "order.order_type",
    "order.limit_price",
    "order.stop_price",
    "claude.model",
    "claude.prompt",
    "sub_agents.enabled",
    "data_provider.credentials",
}


class ParameterProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    current_value: float | int | bool | str
    proposed_value: float | int | bool | str
    status: ParameterProposalStatus
    reasons: list[ParameterProposalReason] = Field(default_factory=list)
    evidence_summary: str
    sample_size: int
    distinct_trading_days: int
    confidence: float
    auto_apply_allowed: bool
    applied: bool = False
    min_value: float | int | bool | None = None
    max_value: float | int | bool | None = None
    max_daily_delta: float | int | None = None


class LearningAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluated_decision_count: int = 0
    candidate_ready_count: int = 0
    executed_count: int = 0
    closed_outcome_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    flat_count: int = 0
    unknown_outcome_count: int = 0
    average_realized_pnl: float | None = None
    median_realized_pnl: float | None = None
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    payoff_ratio: float | None = None
    largest_loss: float | None = None
    decision_to_execution_dropoff_count: int = 0
    rejection_counts: dict[str, int] = Field(default_factory=dict)
    data_provider_error_counts: dict[str, int] = Field(default_factory=dict)
    excluded_from_tuning: dict[str, int] = Field(default_factory=dict)
    tunable_decisions: list[LearningJournalRecord] = Field(default_factory=list)
    tunable_outcomes: list[LearningJournalRecord] = Field(default_factory=list)
    tunable_outcome_classifications: list[OutcomeClassification] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    operational_recommendations: list[str] = Field(default_factory=list)


class LearningRunReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    run_date: date
    prior_trading_date: date
    lookback_start: date
    lookback_end: date
    created_at: datetime
    mode: LearningMode
    records_read: int
    records_skipped: int
    malformed_record_count: int
    evaluated_decision_count: int
    closed_outcome_count: int
    win_count: int
    loss_count: int
    flat_count: int
    unknown_outcome_count: int
    proposals: list[ParameterProposal] = Field(default_factory=list)
    operational_recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    settings_overlay_path: str | None = None
    candidate_ready_count: int = 0
    executed_count: int = 0
    average_realized_pnl: float | None = None
    median_realized_pnl: float | None = None
    win_rate: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    payoff_ratio: float | None = None
    largest_loss: float | None = None
    decision_to_execution_dropoff_count: int = 0
    rejection_counts: dict[str, int] = Field(default_factory=dict)
    data_provider_error_counts: dict[str, int] = Field(default_factory=dict)
    excluded_from_tuning: dict[str, int] = Field(default_factory=dict)
