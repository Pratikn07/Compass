from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from prescient.analyst import (
    ClaudeAnalystSettings,
    SubAgentName,
    SubAgentStatus,
    analyze_strategy_decision_with_sub_agents,
    analyze_sub_agent,
    build_sub_agent_prompt,
)
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


class FakeSubAgentClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, ClaudeAnalystSettings]] = []

    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        self.calls.append((prompt, settings))
        return self.response


def _peer_scores() -> list[PeerScore]:
    return [
        PeerScore(ticker="NTAP", score=5, positive_factors=["revenue_beat"]),
        PeerScore(ticker="PSTG", score=4, positive_factors=["positive_guidance"]),
    ]


def _candidate_brief() -> CandidateBrief:
    return CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 2),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=4.5,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP", "PSTG"],
        peer_scores=_peer_scores(),
        main_thesis="Bullish AI_STORAGE read-through for NTNX.",
        supporting_evidence=[
            "2 of 2 peers had positive scores.",
            "1 peer beat revenue estimates.",
        ],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
    )


def _audit() -> DecisionAudit:
    return DecisionAudit(
        target="NTNX",
        theme="AI_STORAGE",
        peer_scores=_peer_scores(),
        thresholds={
            "min_positive_peer_ratio": 0.67,
            "min_average_peer_score": 2.0,
            "min_avg_daily_volume": 1_000_000,
            "max_target_runup_pct": 10.0,
            "allow_stock_fallback": True,
        },
        missing_peer_factor_count=0,
        all_peer_data_missing=False,
        target_market_data_present=True,
        option_contract_count=1,
    )


def _candidate_ready_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=_candidate_brief(),
        rejection_reasons=[],
        rejection_details=[],
        audit=_audit(),
        claude_analysis_allowed=True,
    )


def _no_trade_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.NO_TRADE,
        candidate=None,
        rejection_reasons=[],
        rejection_details=[],
        audit=_audit(),
        claude_analysis_allowed=False,
    )


def _sub_agent_response(agent_name: SubAgentName) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "status": "analyzed",
            "summary": f"{agent_name.value} review supports the candidate.",
            "supports_thesis": True,
            "risks": [],
            "missing_context": [],
            "confidence": 78,
        }
    )


def test_sub_agent_prompt_contains_bounded_brief_and_scope_rules() -> None:
    prompt = build_sub_agent_prompt(_candidate_brief(), SubAgentName.SENTIMENT)

    assert "Sub-agent prompt version: r2.6-v1" in prompt
    assert "Sentiment Agent" in prompt
    assert '"target":"NTNX"' in prompt
    assert '"theme":"AI_STORAGE"' in prompt
    assert '"strategy_status":"candidate_ready_for_analyst"' in prompt
    assert "Do not request broker credentials, account data, or position state." in prompt
    assert "Do not place trades, choose position size, or override risk limits." in prompt
    assert '"agent_name": "sentiment"' in prompt
    assert "rejection_reasons" not in prompt
    assert "audit" not in prompt


def test_valid_sub_agent_response_returns_analyzed_result() -> None:
    client = FakeSubAgentClient(_sub_agent_response(SubAgentName.TECHNICAL))

    result = analyze_sub_agent(
        _candidate_brief(),
        agent_name=SubAgentName.TECHNICAL,
        client=client,
    )

    assert result.agent_name == SubAgentName.TECHNICAL
    assert result.status == SubAgentStatus.ANALYZED
    assert result.analysis is not None
    assert result.analysis.summary == "technical review supports the candidate."
    assert result.analysis.confidence == 78
    assert result.error_message is None
    assert len(client.calls) == 1


def test_malformed_sub_agent_json_returns_failed_result() -> None:
    client = FakeSubAgentClient("{not valid json")

    result = analyze_sub_agent(
        _candidate_brief(),
        agent_name=SubAgentName.SENTIMENT,
        client=client,
    )

    assert result.status == SubAgentStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "valid JSON" in result.error_message


def test_unsafe_sub_agent_extra_fields_are_rejected() -> None:
    response = {
        "agent_name": "execution",
        "status": "analyzed",
        "summary": "Looks executable.",
        "supports_thesis": True,
        "risks": [],
        "missing_context": [],
        "confidence": 80,
        "position_size": "10%",
        "order_quantity": 5,
        "broker_action": "buy",
        "risk_override": True,
    }
    client = FakeSubAgentClient(json.dumps(response))

    result = analyze_sub_agent(
        _candidate_brief(),
        agent_name=SubAgentName.EXECUTION,
        client=client,
    )

    assert result.status == SubAgentStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "extra fields" in result.error_message


@pytest.mark.parametrize("confidence", [-1, 101, "80", 80.5, True])
def test_invalid_sub_agent_confidence_is_rejected(confidence: object) -> None:
    response = {
        "agent_name": "sentiment",
        "status": "analyzed",
        "summary": "Sentiment is supportive.",
        "supports_thesis": True,
        "risks": [],
        "missing_context": [],
        "confidence": confidence,
    }
    client = FakeSubAgentClient(json.dumps(response))

    result = analyze_sub_agent(
        _candidate_brief(),
        agent_name=SubAgentName.SENTIMENT,
        client=client,
    )

    assert result.status == SubAgentStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "confidence" in result.error_message


def test_mismatched_sub_agent_name_is_rejected() -> None:
    client = FakeSubAgentClient(_sub_agent_response(SubAgentName.SENTIMENT))

    result = analyze_sub_agent(
        _candidate_brief(),
        agent_name=SubAgentName.TECHNICAL,
        client=client,
    )

    assert result.status == SubAgentStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "agent_name" in result.error_message


def test_non_candidate_decision_skips_sub_agents_without_client_calls() -> None:
    client = FakeSubAgentClient(_sub_agent_response(SubAgentName.SENTIMENT))

    packet = analyze_strategy_decision_with_sub_agents(
        _no_trade_decision(),
        clients={SubAgentName.SENTIMENT: client},
    )

    assert packet.target == "NTNX"
    assert packet.theme == "AI_STORAGE"
    assert [result.agent_name for result in packet.results] == [
        SubAgentName.SENTIMENT,
        SubAgentName.TECHNICAL,
        SubAgentName.EXECUTION,
    ]
    assert {result.status for result in packet.results} == {SubAgentStatus.SKIPPED}
    assert client.calls == []


def test_candidate_ready_decision_runs_enabled_sub_agents_in_order() -> None:
    clients = {
        SubAgentName.SENTIMENT: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.SENTIMENT)
        ),
        SubAgentName.TECHNICAL: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.TECHNICAL)
        ),
        SubAgentName.EXECUTION: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.EXECUTION)
        ),
    }

    packet = analyze_strategy_decision_with_sub_agents(
        _candidate_ready_decision(),
        clients=clients,
    )

    assert [result.agent_name for result in packet.results] == [
        SubAgentName.SENTIMENT,
        SubAgentName.TECHNICAL,
        SubAgentName.EXECUTION,
    ]
    assert {result.status for result in packet.results} == {SubAgentStatus.ANALYZED}
    assert [len(client.calls) for client in clients.values()] == [1, 1, 1]


def test_missing_enabled_sub_agent_client_is_skipped() -> None:
    client = FakeSubAgentClient(_sub_agent_response(SubAgentName.SENTIMENT))

    packet = analyze_strategy_decision_with_sub_agents(
        _candidate_ready_decision(),
        clients={SubAgentName.SENTIMENT: client},
        enabled_agents=[SubAgentName.SENTIMENT, SubAgentName.TECHNICAL],
    )

    assert [result.status for result in packet.results] == [
        SubAgentStatus.ANALYZED,
        SubAgentStatus.SKIPPED,
    ]
    assert packet.results[1].error_message == "No sub-agent client was provided."
    assert len(client.calls) == 1


def test_partial_sub_agent_failure_preserves_other_results() -> None:
    clients = {
        SubAgentName.SENTIMENT: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.SENTIMENT)
        ),
        SubAgentName.TECHNICAL: FakeSubAgentClient("{not valid json"),
    }

    packet = analyze_strategy_decision_with_sub_agents(
        _candidate_ready_decision(),
        clients=clients,
        enabled_agents=[SubAgentName.SENTIMENT, SubAgentName.TECHNICAL],
    )

    assert [result.status for result in packet.results] == [
        SubAgentStatus.ANALYZED,
        SubAgentStatus.FAILED,
    ]
    assert packet.results[0].analysis is not None
    assert packet.results[1].analysis is None
    assert packet.results[1].error_message is not None


def test_same_sub_agent_input_and_response_serializes_deterministically() -> None:
    decision = _candidate_ready_decision()
    clients = {
        SubAgentName.SENTIMENT: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.SENTIMENT)
        )
    }
    second_clients = {
        SubAgentName.SENTIMENT: FakeSubAgentClient(
            _sub_agent_response(SubAgentName.SENTIMENT)
        )
    }

    first = analyze_strategy_decision_with_sub_agents(
        decision,
        clients=clients,
        enabled_agents=[SubAgentName.SENTIMENT],
    )
    second = analyze_strategy_decision_with_sub_agents(
        decision,
        clients=second_clients,
        enabled_agents=[SubAgentName.SENTIMENT],
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_sub_agent_package_has_no_execution_side_effect_imports() -> None:
    analyst_files = Path("src/prescient/analyst").glob("*.py")
    forbidden_terms = [
        "prescient.broker",
        "prescient.risk",
        "place_order",
        "cancel_order",
        "time.sleep",
        "asyncio.sleep",
    ]

    offenders = [
        path
        for path in analyst_files
        if any(term in path.read_text() for term in forbidden_terms)
    ]

    assert offenders == []
