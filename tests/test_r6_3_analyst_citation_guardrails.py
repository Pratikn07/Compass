from __future__ import annotations

import json
from datetime import date

from prescient.analyst import (
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    SubAgentName,
    SubAgentStatus,
    analyze_candidate_brief,
    analyze_sub_agent,
    build_claude_strategy_prompt,
    build_sub_agent_prompt,
)
from prescient.journal import SourceCitation
from prescient.signal import CandidateBrief, PeerScore, StrategyStatus


class FakeClaude:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        return json.dumps(self.payload)


def _brief() -> CandidateBrief:
    return CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 10),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=4.5,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP"],
        peer_scores=[
            PeerScore(
                ticker="NTAP",
                score=5,
                positive_factors=["eps_beat"],
                negative_factors=[],
                missing_factors=[],
            )
        ],
        main_thesis="Positive peer read-through.",
        supporting_evidence=["NTAP beat."],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        source_citations=[
            SourceCitation(
                citation_id="peer-ntap",
                provider="fixture",
                source_type="earnings_result",
                excerpt="bounded source excerpt",
            )
        ],
    )


def _analysis_payload(cited_ids: list[str]) -> dict[str, object]:
    return {
        "recommendation": "go",
        "thesis": "The source-cited peer setup is supportive.",
        "reasoning": "The cited candidate brief evidence is positive.",
        "conviction_score": 70,
        "missing_context": [],
        "contradictions": [],
        "suggested_expression": "CALL_OPTION",
        "cited_citation_ids": cited_ids,
    }


def test_candidate_prompt_includes_only_bounded_citation_metadata() -> None:
    prompt = build_claude_strategy_prompt(_brief())

    assert '"citation_id":"peer-ntap"' in prompt
    assert "bounded source excerpt" in prompt
    assert "raw_payload" not in prompt
    assert "account_id" not in prompt
    assert "broker credentials" in prompt


def test_claude_output_can_cite_known_candidate_citation_ids() -> None:
    result = analyze_candidate_brief(
        _brief(),
        client=FakeClaude(_analysis_payload(["peer-ntap"])),
    )

    assert result.status == ClaudeAnalysisStatus.ANALYZED
    assert result.analysis is not None
    assert result.analysis.cited_citation_ids == ["peer-ntap"]


def test_claude_output_with_unknown_citation_id_fails() -> None:
    result = analyze_candidate_brief(
        _brief(),
        client=FakeClaude(_analysis_payload(["invented-id"])),
    )

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert "unknown citation IDs" in (result.error_message or "")


def test_sub_agent_output_citation_ids_are_guarded() -> None:
    prompt = build_sub_agent_prompt(_brief(), SubAgentName.TECHNICAL)
    assert '"citation_id":"peer-ntap"' in prompt

    valid = analyze_sub_agent(
        _brief(),
        agent_name=SubAgentName.TECHNICAL,
        client=FakeClaude(
            {
                "agent_name": "technical",
                "status": "analyzed",
                "summary": "Technicals do not contradict the brief.",
                "supports_thesis": True,
                "risks": [],
                "missing_context": [],
                "confidence": 60,
                "cited_citation_ids": ["peer-ntap"],
            }
        ),
    )
    invalid = analyze_sub_agent(
        _brief(),
        agent_name=SubAgentName.TECHNICAL,
        client=FakeClaude(
            {
                "agent_name": "technical",
                "status": "analyzed",
                "summary": "Invented source.",
                "supports_thesis": True,
                "risks": [],
                "missing_context": [],
                "confidence": 60,
                "cited_citation_ids": ["invented-id"],
            }
        ),
    )

    assert valid.status == SubAgentStatus.ANALYZED
    assert valid.analysis is not None
    assert valid.analysis.cited_citation_ids == ["peer-ntap"]
    assert invalid.status == SubAgentStatus.FAILED
    assert "unknown citation IDs" in (invalid.error_message or "")
