from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.learning.models import LearningRunReport


class RolloutStage(StrEnum):
    DASHBOARD_ONLY = "dashboard_only"
    ALERTS_ONLY = "alerts_only"
    PAPER_TRADING = "paper_trading"
    TINY_LIVE = "tiny_live"


class RolloutGateStatus(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"


class RolloutRejectionReason(StrEnum):
    STAGE_SKIP_NOT_ALLOWED = "stage_skip_not_allowed"
    MANUAL_APPROVAL_REQUIRED = "manual_approval_required"
    PAPER_EVIDENCE_MISSING = "paper_evidence_missing"
    PAPER_TRADING_DAYS_BELOW_MINIMUM = "paper_trading_days_below_minimum"
    CLOSED_PAPER_TRADES_BELOW_MINIMUM = "closed_paper_trades_below_minimum"
    PAPER_NET_PNL_NOT_POSITIVE = "paper_net_pnl_not_positive"
    PAPER_EXPECTANCY_NOT_POSITIVE = "paper_expectancy_not_positive"
    PAPER_DRAWDOWN_MISSING = "paper_drawdown_missing"
    PAPER_DRAWDOWN_EXCEEDED = "paper_drawdown_exceeded"
    UNRESOLVED_CRITICAL_WARNINGS = "unresolved_critical_warnings"
    JOURNAL_COVERAGE_INCOMPLETE = "journal_coverage_incomplete"
    PAPER_TRADING_NOT_ALLOWED = "paper_trading_not_allowed"
    LIVE_TRADING_NOT_ALLOWED = "live_trading_not_allowed"
    TINY_LIVE_RISK_CAP_MISSING = "tiny_live_risk_cap_missing"
    TINY_LIVE_RISK_CAP_EXCEEDED = "tiny_live_risk_cap_exceeded"
    UNSUPPORTED_EXECUTION_MODE = "unsupported_execution_mode"


class RolloutSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_stage: RolloutStage = RolloutStage.DASHBOARD_ONLY
    min_paper_trading_days: int = 90
    min_closed_paper_trades: int = 20
    require_positive_net_pnl: bool = True
    require_positive_expectancy: bool = True
    max_paper_drawdown_pct: float = 0.05
    require_complete_journal_coverage: bool = True
    require_manual_approval: bool = True
    tiny_live_max_trade_loss_pct: float = 0.0025

    @field_validator(
        "min_paper_trading_days",
        "min_closed_paper_trades",
    )
    @classmethod
    def require_non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Rollout sample gates cannot be negative.")
        return value

    @field_validator("max_paper_drawdown_pct", "tiny_live_max_trade_loss_pct")
    @classmethod
    def require_positive_pct(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Rollout percentage settings must be positive.")
        return value


class RolloutCapabilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: RolloutStage
    dashboard_allowed: bool
    alerts_allowed: bool
    paper_orders_allowed: bool
    live_orders_allowed: bool
    broker_writes_allowed: bool
    tiny_live_cap_pct: float


class PaperPerformanceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_trading_days: int
    closed_trade_count: int
    net_realized_pnl: float | None = None
    average_realized_pnl: float | None = None
    max_drawdown_pct: float | None = None
    unresolved_critical_warnings: list[str] = Field(default_factory=list)
    journal_coverage_complete: bool = True

    @field_validator("paper_trading_days", "closed_trade_count")
    @classmethod
    def require_non_negative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Paper performance counts cannot be negative.")
        return value

    @classmethod
    def from_learning_report(
        cls,
        report: LearningRunReport,
        *,
        max_drawdown_pct: float | None = None,
    ) -> "PaperPerformanceSnapshot":
        paper_days = (report.lookback_end - report.lookback_start).days + 1
        average_pnl = report.average_realized_pnl
        net_pnl = (
            average_pnl * report.closed_outcome_count
            if average_pnl is not None
            else None
        )
        return cls(
            paper_trading_days=paper_days,
            closed_trade_count=report.closed_outcome_count,
            net_realized_pnl=net_pnl,
            average_realized_pnl=average_pnl,
            max_drawdown_pct=max_drawdown_pct,
            unresolved_critical_warnings=list(report.warnings),
            journal_coverage_complete=(
                report.malformed_record_count == 0 and report.records_skipped == 0
            ),
        )


class RolloutPromotionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_stage: RolloutStage
    to_stage: RolloutStage
    requested_by: str
    manual_approval: bool = False
    requested_at: datetime | None = None
    paper_performance: PaperPerformanceSnapshot | LearningRunReport | None = None

    @field_validator("requested_by")
    @classmethod
    def require_requested_by(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Rollout promotion requested_by is required.")
        return cleaned

    @model_validator(mode="after")
    def normalize_learning_report_evidence(self) -> "RolloutPromotionRequest":
        if isinstance(self.paper_performance, LearningRunReport):
            return self.model_copy(
                update={
                    "paper_performance": PaperPerformanceSnapshot.from_learning_report(
                        self.paper_performance
                    )
                }
            )
        return self


class RolloutGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RolloutGateStatus
    current_stage: RolloutStage
    requested_stage: RolloutStage | None = None
    approved_stage: RolloutStage | None = None
    requested_execution_mode: str | None = None
    proposed_max_loss_pct: float | None = None
    tiny_live_cap_pct: float
    broker_execution_allowed: bool = False
    rejection_reasons: list[RolloutRejectionReason] = Field(default_factory=list)
    explanation: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requested_execution_mode")
    @classmethod
    def normalize_optional_mode(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None and value.strip() else None

    @model_validator(mode="after")
    def validate_status_contract(self) -> "RolloutGateDecision":
        if self.status == RolloutGateStatus.APPROVED and self.rejection_reasons:
            raise ValueError("Approved rollout decisions must not include rejection reasons.")
        if self.status == RolloutGateStatus.BLOCKED and not self.rejection_reasons:
            raise ValueError("Blocked rollout decisions must include rejection reasons.")
        if self.status == RolloutGateStatus.BLOCKED and self.broker_execution_allowed:
            raise ValueError("Blocked rollout decisions cannot allow broker execution.")
        return self
