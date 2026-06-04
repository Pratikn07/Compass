from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.analyst.models import ClaudeAnalysisResult, SubAgentReviewPacket
from prescient.alerts.models import TradeNotificationResult
from prescient.broker.models import OrderExecutionResult
from prescient.journal import (
    DecisionLayer,
    DecisionType,
    SourceCitation,
    deterministic_decision_id,
)
from prescient.risk import DailyHaltDecision, PositionSizingDecision, RiskGateDecision
from prescient.signal.models import StrategyDecision, StrategyStatus


class PipelineJournalEventType(StrEnum):
    HOT_PATH_DECISION = "hot_path_decision"
    SUB_AGENT_REVIEW = "sub_agent_review"
    COLD_PATH_ANALYSIS = "cold_path_analysis"


class DecisionJournalRecordType(StrEnum):
    STRATEGY_DECISION = "strategy_decision"
    ANALYST_REVIEW = "analyst_review"
    SUB_AGENT_REVIEW = "sub_agent_review"
    RISK_DECISION = "risk_decision"
    POSITION_SIZING = "position_sizing"
    ROLLOUT_GATE_DECISION = "rollout_gate_decision"
    ROLLOUT_PROMOTION = "rollout_promotion"
    EXECUTION_PROPOSAL = "execution_proposal"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILL = "order_fill"
    ORDER_CANCELLED = "order_cancelled"
    BROKER_REJECTION = "broker_rejection"
    TRADE_EXIT = "trade_exit"
    TRADE_OUTCOME = "trade_outcome"
    TRADE_NOTIFICATION = "trade_notification"
    OUTCOME_CORRECTION = "outcome_correction"


class DecisionOutcomeType(StrEnum):
    PENDING = "pending"
    REJECTED = "rejected"
    NO_TRADE = "no_trade"
    RISK_BLOCKED = "risk_blocked"
    PROPOSED = "proposed"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    BROKER_REJECTED = "broker_rejected"
    CLOSED_WIN = "closed_win"
    CLOSED_LOSS = "closed_loss"
    CLOSED_FLAT = "closed_flat"
    UNKNOWN = "unknown"


class DecisionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome_type: DecisionOutcomeType
    net_realized_pnl: float | None = None
    gross_realized_pnl: float | None = None
    fees: float | None = None
    pnl_currency: str = "USD"
    open_quantity: float | None = None
    closed_quantity: float | None = None
    outcome_reasons: list[str] = Field(default_factory=list)
    ambiguous: bool = False


class DecisionJournalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    journal_record_id: str
    record_type: DecisionJournalRecordType
    run_id: str
    decision_id: str
    decision_index: int | None = None
    trading_date: date
    created_at: datetime
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    strategy_status: str | None = None
    execution_mode: str | None = None
    source: str
    order_id: str | None = None
    parent_record_id: str | None = None
    duplicate_of_record_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("source")
    @classmethod
    def require_source(cls, value: str) -> str:
        source = value.strip()
        if not source:
            raise ValueError("Decision journal record source is required.")
        return source


class PipelineJournalEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: PipelineJournalEventType
    run_id: str = "runtime:unknown"
    decision_id: str | None = None
    decision_type: DecisionType = DecisionType.PIPELINE_JOURNAL_EVENT
    decision_layer: DecisionLayer = DecisionLayer.RUNTIME
    parent_decision_ids: list[str] = Field(default_factory=list)
    related_order_ids: list[str] = Field(default_factory=list)
    related_event_ids: list[str] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)
    decision_index: int
    target: str | None
    theme: str | None
    strategy_status: StrategyStatus
    strategy_decision: StrategyDecision | None = None
    sub_agent_packet: SubAgentReviewPacket | None = None
    claude_result: ClaudeAnalysisResult | None = None

    @model_validator(mode="before")
    @classmethod
    def add_default_decision_id(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("decision_id") is not None:
            return data

        event_type = data.get("event_type")
        event_value = event_type.value if isinstance(event_type, StrEnum) else str(event_type)
        run_id = data.get("run_id", "runtime:unknown")
        decision_type = data.get("decision_type", DecisionType.PIPELINE_JOURNAL_EVENT)
        decision_layer = data.get("decision_layer", DecisionLayer.RUNTIME)
        return {
            **data,
            "decision_id": deterministic_decision_id(
                decision_type=decision_type,
                decision_layer=decision_layer,
                target=data.get("target"),
                theme=data.get("theme"),
                seed=f"{run_id}:{event_value}:{data.get('decision_index')}",
            ),
        }

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_event_payload(self) -> "PipelineJournalEvent":
        if self.event_type == PipelineJournalEventType.HOT_PATH_DECISION:
            if self.strategy_decision is None:
                raise ValueError("Hot-path journal events must include a strategy decision.")
            if self.claude_result is not None:
                raise ValueError("Hot-path journal events must not include a Claude result.")
            if self.sub_agent_packet is not None:
                raise ValueError("Hot-path journal events must not include a sub-agent packet.")

        if self.event_type == PipelineJournalEventType.SUB_AGENT_REVIEW:
            if self.sub_agent_packet is None:
                raise ValueError("Sub-agent journal events must include a review packet.")
            if self.strategy_decision is not None:
                raise ValueError("Sub-agent journal events must not include a strategy decision.")
            if self.claude_result is not None:
                raise ValueError("Sub-agent journal events must not include a Claude result.")

        if self.event_type == PipelineJournalEventType.COLD_PATH_ANALYSIS:
            if self.claude_result is None:
                raise ValueError("Cold-path journal events must include a Claude result.")
            if self.sub_agent_packet is not None:
                raise ValueError("Cold-path journal events must not include a sub-agent packet.")

        return self


class PipelineRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_decisions: list[StrategyDecision] = Field(default_factory=list)
    sub_agent_packets: list[SubAgentReviewPacket] = Field(default_factory=list)
    claude_results: list[ClaudeAnalysisResult] = Field(default_factory=list)
    journal_events: list[PipelineJournalEvent] = Field(default_factory=list)
    decision_journal_records: list[DecisionJournalRecord] = Field(default_factory=list)
    storage_errors: list[Any] = Field(default_factory=list)
    alert_delivery_results: list[Any] = Field(default_factory=list)
    risk_gate_decisions: list[RiskGateDecision] = Field(default_factory=list)
    sizing_decisions: list[PositionSizingDecision] = Field(default_factory=list)
    daily_halt_decision: DailyHaltDecision | None = None


class ExecutionDecisionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_index: int
    target: str
    theme: str | None = None
    order_result: OrderExecutionResult
    notification_result: TradeNotificationResult | None = None
    decision_journal_records: list[DecisionJournalRecord] = Field(default_factory=list)

    @field_validator("target", "theme")
    @classmethod
    def normalize_optional_uppercase(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class ExecutionPipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_results: list[ExecutionDecisionResult] = Field(default_factory=list)
    notification_results: list[TradeNotificationResult] = Field(default_factory=list)
    decision_journal_records: list[DecisionJournalRecord] = Field(default_factory=list)
