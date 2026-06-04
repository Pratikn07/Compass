from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from json import JSONDecodeError

from pydantic import ValidationError

from prescient.analyst.claude import ClaudeCompletionClient
from prescient.analyst.models import (
    ClaudeAnalystSettings,
    SubAgentAnalysis,
    SubAgentName,
    SubAgentResult,
    SubAgentReviewPacket,
    SubAgentStatus,
)
from prescient.journal import DecisionLayer, DecisionType, audit_trail
from prescient.signal.models import CandidateBrief, StrategyDecision, StrategyStatus


SUB_AGENT_PROMPT_VERSION = "r2.6-v1"
DEFAULT_SUB_AGENTS = (
    SubAgentName.SENTIMENT,
    SubAgentName.TECHNICAL,
    SubAgentName.EXECUTION,
)
_DEFAULT_SETTINGS = ClaudeAnalystSettings()


def build_sub_agent_prompt(brief: CandidateBrief, agent_name: SubAgentName) -> str:
    candidate_json = brief.model_dump_json()
    title, scope = _agent_scope(agent_name)

    return (
        f"You are the {title} for prescient.\n"
        f"Sub-agent prompt version: {SUB_AGENT_PROMPT_VERSION}\n"
        "Read only the candidate brief JSON below and return strict JSON.\n\n"
        "Safety rules:\n"
        "- Do not request broker credentials, account data, or position state.\n"
        "- Do not place trades, choose position size, or override risk limits.\n"
        "- Do not fetch live data or inspect raw unbounded event/news streams.\n"
        "- Do not score peers, run target filters, or mutate deterministic decisions.\n"
        "- Do not suggest position_size, order_quantity, broker_action, or risk_override.\n\n"
        f"Focused scope:\n{scope}\n\n"
        "Return exactly this JSON shape with no extra fields:\n"
        "{\n"
        f'  "agent_name": "{agent_name.value}",\n'
        '  "status": "analyzed",\n'
        '  "summary": "short focused review based only on the candidate brief",\n'
        '  "supports_thesis": true,\n'
        '  "risks": ["material focused risk"],\n'
        '  "missing_context": ["structured context still needed"],\n'
        '  "confidence": 0,\n'
        '  "cited_citation_ids": ["candidate brief citation_id"]\n'
        "}\n\n"
        f"Candidate brief JSON:\n{candidate_json}"
    )


def analyze_sub_agent(
    brief: CandidateBrief,
    *,
    agent_name: SubAgentName,
    client: ClaudeCompletionClient,
    settings: ClaudeAnalystSettings = _DEFAULT_SETTINGS,
) -> SubAgentResult:
    prompt = build_sub_agent_prompt(brief, agent_name)
    raw_response = client.complete(prompt, settings)

    try:
        parsed_response = json.loads(raw_response)
    except JSONDecodeError:
        return SubAgentResult(
            agent_name=agent_name,
            status=SubAgentStatus.FAILED,
            analysis=None,
            error_message="Sub-agent response must be valid JSON.",
        )

    try:
        analysis = SubAgentAnalysis.model_validate(parsed_response)
    except ValidationError as exc:
        return SubAgentResult(
            agent_name=agent_name,
            status=SubAgentStatus.FAILED,
            analysis=None,
            error_message=_validation_error_message(exc),
        )

    if analysis.agent_name != agent_name:
        return SubAgentResult(
            agent_name=agent_name,
            status=SubAgentStatus.FAILED,
            analysis=None,
            error_message=(
                "Sub-agent response failed validation: agent_name did not match "
                f"{agent_name.value}."
            ),
        )

    unknown_citation_ids = _unknown_citation_ids(analysis.cited_citation_ids, brief)
    if unknown_citation_ids:
        return SubAgentResult(
            agent_name=agent_name,
            status=SubAgentStatus.FAILED,
            analysis=None,
            error_message=(
                "Sub-agent response cited unknown citation IDs: "
                f"{', '.join(unknown_citation_ids)}."
            ),
        )

    return SubAgentResult(
        agent_name=agent_name,
        status=analysis.status,
        analysis=analysis,
        error_message=None,
    )


def analyze_strategy_decision_with_sub_agents(
    decision: StrategyDecision,
    *,
    clients: Mapping[SubAgentName, ClaudeCompletionClient] | None = None,
    enabled_agents: Sequence[SubAgentName] = DEFAULT_SUB_AGENTS,
    settings: ClaudeAnalystSettings = _DEFAULT_SETTINGS,
) -> SubAgentReviewPacket:
    target, theme = _target_and_theme(decision)
    if (
        decision.status != StrategyStatus.CANDIDATE_READY_FOR_ANALYST
        or decision.candidate is None
        or not decision.claude_analysis_allowed
    ):
        return SubAgentReviewPacket(
            target=target,
            theme=theme,
            results=[
                _skipped_result(
                    agent_name=agent_name,
                    reason="Strategy decision is not ready for sub-agent analysis.",
                )
                for agent_name in enabled_agents
            ],
            audit_trail=_packet_audit_trail(decision),
        )

    sub_agent_clients = clients or {}
    results: list[SubAgentResult] = []
    for agent_name in enabled_agents:
        client = sub_agent_clients.get(agent_name)
        if client is None:
            results.append(
                _skipped_result(
                    agent_name=agent_name,
                    reason="No sub-agent client was provided.",
                )
            )
            continue

        results.append(
            analyze_sub_agent(
                decision.candidate,
                agent_name=agent_name,
                client=client,
                settings=settings,
            )
        )

    return SubAgentReviewPacket(
        target=target,
        theme=theme,
        results=results,
        audit_trail=_packet_audit_trail(decision),
    )


def _skipped_result(*, agent_name: SubAgentName, reason: str) -> SubAgentResult:
    return SubAgentResult(
        agent_name=agent_name,
        status=SubAgentStatus.SKIPPED,
        analysis=None,
        error_message=reason,
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme

    return decision.audit.target, decision.audit.theme


def _agent_scope(agent_name: SubAgentName) -> tuple[str, str]:
    if agent_name == SubAgentName.SENTIMENT:
        return (
            "Sentiment Agent",
            "- Review only structured evidence, supporting text, and contradictions.\n"
            "- Identify whether sentiment supports, weakens, or contradicts the thesis.\n"
            "- Do not score peers, size trades, or recommend broker actions.",
        )

    if agent_name == SubAgentName.TECHNICAL:
        return (
            "Technical Agent",
            "- Review only structured price, volume, run-up, and liquidity context in the brief.\n"
            "- Identify whether the technical setup supports or weakens the thesis.\n"
            "- Do not compute hidden indicators from raw price streams.",
        )

    return (
        "Execution Agent",
        "- Review only the deterministic recommended expression and structured readiness context.\n"
        "- Flag missing context, unsupported expression, or future risk/broker gate needs.\n"
        "- Do not place or cancel orders and do not convert review into execution.",
    )


def _validation_error_message(error: ValidationError) -> str:
    if any(item["type"] == "extra_forbidden" for item in error.errors()):
        return "Sub-agent response failed validation: extra fields are not allowed."

    return f"Sub-agent response failed validation: {error}"


def _unknown_citation_ids(cited_ids: list[str], brief: CandidateBrief) -> list[str]:
    known_ids = {citation.citation_id for citation in brief.source_citations}
    return [citation_id for citation_id in cited_ids if citation_id not in known_ids]


def _packet_audit_trail(decision: StrategyDecision):
    target, theme = _target_and_theme(decision)
    source_citations = (
        decision.candidate.source_citations if decision.candidate is not None else []
    )
    parent_ids = [decision.audit_trail.decision_id]
    return audit_trail(
        decision_type=DecisionType.SUB_AGENT_REVIEW,
        decision_layer=DecisionLayer.ANALYST,
        target=target,
        theme=theme,
        parent_decision_ids=parent_ids,
        source_citations=source_citations,
        seed=decision.audit_trail.decision_id,
    )
