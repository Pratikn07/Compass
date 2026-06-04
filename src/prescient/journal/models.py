from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_CITATION_EXCERPT_CHARS = 500
_UNSAFE_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+|secret|account[_-]?id|raw[_-]?payload|"
    r"raw[_-]?prompt|\bprompt\s*:|-----begin)",
    re.IGNORECASE,
)


class CitationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class CitationUnavailableReason(StrEnum):
    CITATION_UNAVAILABLE_LEGACY_RECORD = "citation_unavailable_legacy_record"
    SOURCE_NOT_AVAILABLE = "source_not_available"
    INTERNAL_ONLY = "internal_only"
    NOT_APPLICABLE = "not_applicable"


class DecisionLayer(StrEnum):
    DATA = "data"
    SIGNAL = "signal"
    ANALYST = "analyst"
    ALERTS = "alerts"
    EVENT = "event"
    SCHEDULER = "scheduler"
    RUNTIME = "runtime"
    RISK = "risk"
    BROKER = "broker"
    LEARNING = "learning"
    JOURNAL = "journal"


class DecisionType(StrEnum):
    DATA_SNAPSHOT = "data_snapshot"
    STRATEGY_DECISION = "strategy_decision"
    CANDIDATE_BRIEF = "candidate_brief"
    CLAUDE_ANALYSIS = "claude_analysis"
    SUB_AGENT_REVIEW = "sub_agent_review"
    PIPELINE_JOURNAL_EVENT = "pipeline_journal_event"
    RISK_GATE = "risk_gate"
    TRADE_RISK = "trade_risk"
    POSITION_SIZING = "position_sizing"
    DAILY_HALT = "daily_halt"
    ACCOUNT_SIZE_POLICY = "account_size_policy"
    EXECUTION_QUALITY = "execution_quality"
    BROKER_ORDER = "broker_order"
    BROKER_ORDER_RESULT = "broker_order_result"
    TRADE_NOTIFICATION = "trade_notification"
    LEARNING_REPORT = "learning_report"


class SourceCitation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    citation_id: str
    provider: str
    source_type: str
    title: str | None = None
    url: str | None = None
    source_endpoint: str | None = None
    source_id: str | None = None
    as_of: date | datetime | None = None
    retrieved_at: datetime | None = None
    excerpt: str | None = None
    confidence: CitationConfidence = CitationConfidence.UNKNOWN

    @field_validator("provider", "source_type")
    @classmethod
    def normalize_required_slug(cls, value: str) -> str:
        normalized = _normalize_slug(value)
        if not normalized:
            raise ValueError("Citation provider and source type are required.")
        _reject_unsafe_text(normalized)
        return normalized

    @field_validator(
        "citation_id",
        "title",
        "url",
        "source_endpoint",
        "source_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        _reject_unsafe_text(stripped)
        return stripped

    @field_validator("excerpt")
    @classmethod
    def validate_excerpt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        _reject_unsafe_text(stripped)
        if len(stripped) > MAX_CITATION_EXCERPT_CHARS:
            return stripped[:MAX_CITATION_EXCERPT_CHARS]
        return stripped


class RuleAuditFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_name: str
    passed: bool | None = None
    threshold: str | int | float | bool | None = None
    observed_value: str | int | float | bool | None = None
    reason: str | None = None
    citation_ids: list[str] = Field(default_factory=list)

    @field_validator("rule_name")
    @classmethod
    def normalize_rule_name(cls, value: str) -> str:
        normalized = _normalize_slug(value)
        if not normalized:
            raise ValueError("Rule fact requires a rule name.")
        return normalized

    @field_validator("reason")
    @classmethod
    def reject_unsafe_reason(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_unsafe_text(value)
        return value


class DecisionAuditTrail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str | None = None
    decision_id: str
    decision_type: DecisionType
    decision_layer: DecisionLayer
    target: str | None = None
    theme: str | None = None
    parent_decision_ids: list[str] = Field(default_factory=list)
    related_order_ids: list[str] = Field(default_factory=list)
    related_event_ids: list[str] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)
    citation_unavailable_reasons: list[CitationUnavailableReason] = Field(
        default_factory=list
    )
    rule_facts: list[RuleAuditFact] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("run_id", "decision_id", mode="before")
    @classmethod
    def validate_ids(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        _reject_unsafe_text(stripped)
        return stripped

    @model_validator(mode="after")
    def validate_audit_evidence(self) -> "DecisionAuditTrail":
        if (
            not self.source_citations
            and not self.citation_unavailable_reasons
            and not self.rule_facts
        ):
            raise ValueError(
                "Decision audit trails require citations, unavailable reasons, or rule facts."
            )
        return self


def deterministic_citation_id(
    *,
    provider: str | StrEnum,
    source_type: str | StrEnum,
    title: str | None = None,
    url: str | None = None,
    source_endpoint: str | None = None,
    source_id: str | None = None,
    as_of: date | datetime | None = None,
) -> str:
    payload = {
        "provider": _enum_value(provider).strip().lower(),
        "source_type": _enum_value(source_type).strip().lower(),
        "title": title.strip() if title else None,
        "url": url.strip() if url else None,
        "source_endpoint": source_endpoint.strip() if source_endpoint else None,
        "source_id": source_id.strip() if source_id else None,
        "as_of": as_of.isoformat() if as_of is not None else None,
    }
    return f"cit_{_stable_hash(payload)}"


def deterministic_decision_id(
    *,
    decision_type: DecisionType | str,
    decision_layer: DecisionLayer | str,
    target: str | None = None,
    theme: str | None = None,
    seed: str | None = None,
) -> str:
    payload = {
        "decision_type": _enum_value(decision_type),
        "decision_layer": _enum_value(decision_layer),
        "target": target.strip().upper() if target else None,
        "theme": theme.strip().upper() if theme else None,
        "seed": seed,
    }
    return f"dec_{_stable_hash(payload)}"


def internal_rule_citation(rule_name: str, *, title: str | None = None) -> SourceCitation:
    normalized_rule = _normalize_slug(rule_name)
    return SourceCitation(
        citation_id=deterministic_citation_id(
            provider="prescient",
            source_type="risk_rule" if normalized_rule.startswith("risk") else "strategy_rule",
            source_id=normalized_rule,
        ),
        provider="prescient",
        source_type="risk_rule" if normalized_rule.startswith("risk") else "strategy_rule",
        title=title or rule_name.strip(),
        source_id=normalized_rule,
        confidence=CitationConfidence.HIGH,
    )


def internal_config_citation(
    config_name: str,
    *,
    title: str | None = None,
) -> SourceCitation:
    normalized_config = _normalize_slug(config_name)
    return SourceCitation(
        citation_id=deterministic_citation_id(
            provider="prescient",
            source_type="internal_config",
            source_id=normalized_config,
        ),
        provider="prescient",
        source_type="internal_config",
        title=title or normalized_config,
        source_id=normalized_config,
        confidence=CitationConfidence.HIGH,
    )


def url_citation(
    *,
    provider: str | StrEnum,
    source_type: str | StrEnum,
    url: str,
    title: str | None = None,
    source_endpoint: str | None = None,
    source_id: str | None = None,
    as_of: date | datetime | None = None,
    retrieved_at: datetime | None = None,
    excerpt: str | None = None,
    confidence: CitationConfidence = CitationConfidence.UNKNOWN,
) -> SourceCitation:
    return SourceCitation(
        citation_id=deterministic_citation_id(
            provider=provider,
            source_type=source_type,
            title=title,
            url=url,
            source_endpoint=source_endpoint,
            source_id=source_id,
            as_of=as_of,
        ),
        provider=_enum_value(provider),
        source_type=_enum_value(source_type),
        title=title,
        url=url,
        source_endpoint=source_endpoint,
        source_id=source_id,
        as_of=as_of,
        retrieved_at=retrieved_at,
        excerpt=excerpt,
        confidence=confidence,
    )


def merge_source_citations(
    *citation_groups: SourceCitation | Sequence[SourceCitation] | None,
) -> list[SourceCitation]:
    merged: list[SourceCitation] = []
    seen: set[str] = set()
    for group in citation_groups:
        for citation in _iter_citations(group):
            if citation.citation_id in seen:
                continue
            seen.add(citation.citation_id)
            merged.append(citation)
    return merged


def rule_fact(
    rule_name: str,
    *,
    passed: bool | None = None,
    threshold: str | int | float | bool | None = None,
    observed_value: str | int | float | bool | None = None,
    reason: str | None = None,
    citation_ids: Sequence[str] | None = None,
) -> RuleAuditFact:
    return RuleAuditFact(
        rule_name=rule_name,
        passed=passed,
        threshold=threshold,
        observed_value=observed_value,
        reason=reason,
        citation_ids=list(citation_ids or []),
    )


def legacy_audit_trail(
    decision_type: DecisionType,
    decision_layer: DecisionLayer,
    *,
    target: str | None = None,
    theme: str | None = None,
    run_id: str | None = None,
) -> DecisionAuditTrail:
    return DecisionAuditTrail(
        run_id=run_id,
        decision_id=deterministic_decision_id(
            decision_type=decision_type,
            decision_layer=decision_layer,
            target=target,
            theme=theme,
            seed="legacy",
        ),
        decision_type=decision_type,
        decision_layer=decision_layer,
        target=target,
        theme=theme,
        citation_unavailable_reasons=[
            CitationUnavailableReason.CITATION_UNAVAILABLE_LEGACY_RECORD
        ],
    )


def audit_trail(
    *,
    decision_type: DecisionType,
    decision_layer: DecisionLayer,
    target: str | None = None,
    theme: str | None = None,
    run_id: str | None = None,
    seed: str | None = None,
    source_citations: Sequence[SourceCitation] | None = None,
    citation_unavailable_reasons: Sequence[CitationUnavailableReason] | None = None,
    rule_facts: Sequence[RuleAuditFact] | None = None,
    parent_decision_ids: Sequence[str] | None = None,
    related_order_ids: Sequence[str] | None = None,
    related_event_ids: Sequence[str] | None = None,
) -> DecisionAuditTrail:
    citations = merge_source_citations(source_citations)
    unavailable = list(citation_unavailable_reasons or [])
    facts = list(rule_facts or [])
    if not citations and not unavailable and not facts:
        unavailable = [CitationUnavailableReason.CITATION_UNAVAILABLE_LEGACY_RECORD]

    return DecisionAuditTrail(
        run_id=run_id,
        decision_id=deterministic_decision_id(
            decision_type=decision_type,
            decision_layer=decision_layer,
            target=target,
            theme=theme,
            seed=seed,
        ),
        decision_type=decision_type,
        decision_layer=decision_layer,
        target=target,
        theme=theme,
        parent_decision_ids=list(parent_decision_ids or []),
        related_order_ids=list(related_order_ids or []),
        related_event_ids=list(related_event_ids or []),
        source_citations=citations,
        citation_unavailable_reasons=unavailable,
        rule_facts=facts,
    )


def _iter_citations(
    group: SourceCitation | Sequence[SourceCitation] | None,
) -> Iterable[SourceCitation]:
    if group is None:
        return []
    if isinstance(group, SourceCitation):
        return [group]
    return group


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _enum_value(value: str | StrEnum) -> str:
    return value.value if isinstance(value, StrEnum) else str(value)


def _normalize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _reject_unsafe_text(value: str) -> None:
    if _UNSAFE_PATTERN.search(value):
        raise ValueError("Citation fields cannot include secrets, raw payloads, prompts, or account IDs.")
