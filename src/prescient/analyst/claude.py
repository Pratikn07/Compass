from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Protocol

from pydantic import ValidationError

from prescient.analyst.models import (
    ClaudeAnalysisResult,
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    ClaudeStrategyAnalysis,
)
from prescient.analyst.prompt import build_claude_strategy_prompt
from prescient.journal import DecisionLayer, DecisionType, audit_trail
from prescient.signal.models import CandidateBrief, StrategyDecision, StrategyStatus


class ClaudeCompletionClient(Protocol):
    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        pass


_DEFAULT_SETTINGS = ClaudeAnalystSettings()


def analyze_candidate_brief(
    brief: CandidateBrief,
    client: ClaudeCompletionClient,
    settings: ClaudeAnalystSettings = _DEFAULT_SETTINGS,
) -> ClaudeAnalysisResult:
    prompt = build_claude_strategy_prompt(brief)
    raw_response = client.complete(prompt, settings)

    try:
        parsed_response = json.loads(raw_response)
    except JSONDecodeError:
        return ClaudeAnalysisResult(
            status=ClaudeAnalysisStatus.FAILED,
            analysis=None,
            error_message="Claude response must be valid JSON.",
        )

    try:
        analysis = ClaudeStrategyAnalysis.model_validate(parsed_response)
    except ValidationError as exc:
        return ClaudeAnalysisResult(
            status=ClaudeAnalysisStatus.FAILED,
            analysis=None,
            error_message=_validation_error_message(exc),
        )

    unknown_citation_ids = _unknown_citation_ids(analysis.cited_citation_ids, brief)
    if unknown_citation_ids:
        return ClaudeAnalysisResult(
            status=ClaudeAnalysisStatus.FAILED,
            analysis=None,
            error_message=(
                "Claude response cited unknown citation IDs: "
                f"{', '.join(unknown_citation_ids)}."
            ),
            audit_trail=_analysis_audit_trail(brief),
        )

    return ClaudeAnalysisResult(
        status=ClaudeAnalysisStatus.ANALYZED,
        analysis=analysis,
        error_message=None,
        audit_trail=_analysis_audit_trail(brief),
    )


def analyze_strategy_decision(
    decision: StrategyDecision,
    client: ClaudeCompletionClient,
    settings: ClaudeAnalystSettings = _DEFAULT_SETTINGS,
) -> ClaudeAnalysisResult:
    if (
        decision.status != StrategyStatus.CANDIDATE_READY_FOR_ANALYST
        or decision.candidate is None
        or not decision.claude_analysis_allowed
    ):
        return ClaudeAnalysisResult(
            status=ClaudeAnalysisStatus.SKIPPED,
            analysis=None,
            error_message="Strategy decision is not ready for Claude analysis.",
        )

    return analyze_candidate_brief(
        brief=decision.candidate,
        client=client,
        settings=settings,
    )


def _validation_error_message(error: ValidationError) -> str:
    if any(item["type"] == "extra_forbidden" for item in error.errors()):
        return "Claude response failed validation: extra fields are not allowed."

    return f"Claude response failed validation: {error}"


def _unknown_citation_ids(cited_ids: list[str], brief: CandidateBrief) -> list[str]:
    known_ids = {citation.citation_id for citation in brief.source_citations}
    return [citation_id for citation_id in cited_ids if citation_id not in known_ids]


def _analysis_audit_trail(brief: CandidateBrief):
    return audit_trail(
        decision_type=DecisionType.CLAUDE_ANALYSIS,
        decision_layer=DecisionLayer.ANALYST,
        target=brief.target,
        theme=brief.theme,
        source_citations=brief.source_citations,
        seed=brief.model_dump_json(),
    )
