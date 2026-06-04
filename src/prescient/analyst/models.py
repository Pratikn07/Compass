from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    legacy_audit_trail,
)


ClaudeSuggestedExpression = Literal["CALL_OPTION", "STOCK", "NONE"]


class ClaudeRecommendation(StrEnum):
    GO = "go"
    NO_GO = "no_go"
    NEEDS_MORE_CONTEXT = "needs_more_context"


class ClaudeAnalysisStatus(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ClaudeAnalystSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "claude-3-5-sonnet-latest"
    temperature: float = 0.0
    max_tokens: int = 1_000


class ClaudeStrategyAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation: ClaudeRecommendation
    thesis: str
    reasoning: str
    conviction_score: int = Field(ge=0, le=100, strict=True)
    missing_context: list[str]
    contradictions: list[str]
    suggested_expression: ClaudeSuggestedExpression
    cited_citation_ids: list[str] = Field(default_factory=list)


class ClaudeAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ClaudeAnalysisStatus
    analysis: ClaudeStrategyAnalysis | None = None
    error_message: str | None = None
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.CLAUDE_ANALYSIS,
            decision_layer=DecisionLayer.ANALYST,
        )
    )


class SubAgentName(StrEnum):
    SENTIMENT = "sentiment"
    TECHNICAL = "technical"
    EXECUTION = "execution"


class SubAgentStatus(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"
    FAILED = "failed"


class SubAgentAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_name: SubAgentName
    status: SubAgentStatus
    summary: str
    supports_thesis: bool
    risks: list[str]
    missing_context: list[str]
    confidence: int = Field(ge=0, le=100, strict=True)
    cited_citation_ids: list[str] = Field(default_factory=list)


class SubAgentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_name: SubAgentName
    status: SubAgentStatus
    analysis: SubAgentAnalysis | None = None
    error_message: str | None = None


class SubAgentReviewPacket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    theme: str | None
    results: list[SubAgentResult]
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.SUB_AGENT_REVIEW,
            decision_layer=DecisionLayer.ANALYST,
        )
    )
