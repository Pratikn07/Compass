from __future__ import annotations

import json
from datetime import date

import pytest

from prescient.analyst import (
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    ClaudeRecommendation,
    analyze_candidate_brief,
    analyze_strategy_decision,
    build_claude_strategy_prompt,
)
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


class FakeClaudeClient:
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


def _valid_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from strong peer earnings.",
      "reasoning": "Peer read-through is strong and contradictions are limited.",
      "conviction_score": 82,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """


def test_prompt_contains_candidate_brief_json_and_prd_safety_rules() -> None:
    prompt = build_claude_strategy_prompt(_candidate_brief())

    assert '"target":"NTNX"' in prompt
    assert '"theme":"AI_STORAGE"' in prompt
    assert '"strategy_status":"candidate_ready_for_analyst"' in prompt
    assert "Prompt version: r2.5-v1" in prompt
    assert "Claude must not override deterministic filters or risk limits." in prompt
    assert (
        "Do not suggest position_size, order_quantity, broker_action, limit_price, "
        "stop_loss, take_profit, account_allocation, risk_override, or execute_trade."
        in prompt
    )
    assert (
        "Do not use conviction_score as a position size, risk budget, or trading "
        "authorization." in prompt
    )
    assert "Only suggest CALL_OPTION, STOCK, or NONE." in prompt
    assert '"thesis": "short analyst thesis based only on the candidate brief"' in prompt
    assert '"conviction_score": 0' in prompt
    assert "integer from 0 to 100" in prompt
    assert "rejection_reasons" not in prompt
    assert "audit" not in prompt


def test_valid_fake_claude_response_returns_analyzed_result() -> None:
    client = FakeClaudeClient(_valid_response())

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.ANALYZED
    assert result.analysis is not None
    assert result.analysis.recommendation == ClaudeRecommendation.GO
    assert result.analysis.thesis == (
        "NTNX has a bullish AI_STORAGE read-through from strong peer earnings."
    )
    assert result.analysis.conviction_score == 82
    assert result.analysis.suggested_expression == "CALL_OPTION"
    assert result.analysis.reasoning == (
        "Peer read-through is strong and contradictions are limited."
    )
    assert result.error_message is None
    assert len(client.calls) == 1


def test_no_trade_strategy_decision_returns_skipped_without_client_call() -> None:
    client = FakeClaudeClient(_valid_response())

    result = analyze_strategy_decision(_no_trade_decision(), client=client)

    assert result.status == ClaudeAnalysisStatus.SKIPPED
    assert result.analysis is None
    assert result.error_message == "Strategy decision is not ready for Claude analysis."
    assert client.calls == []


def test_malformed_json_returns_failed_result() -> None:
    client = FakeClaudeClient("{not valid json")

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "valid JSON" in result.error_message


def test_unsafe_extra_fields_are_rejected() -> None:
    client = FakeClaudeClient(
        """
        {
          "recommendation": "go",
          "thesis": "NTNX has a bullish AI_STORAGE read-through from strong peer earnings.",
          "reasoning": "Looks good.",
          "conviction_score": 75,
          "missing_context": [],
          "contradictions": [],
          "suggested_expression": "CALL_OPTION",
          "position_size": "10%",
          "order_quantity": 5,
          "broker_action": "buy",
          "limit_price": 1.25,
          "stop_loss": 0.8,
          "take_profit": 2.0,
          "account_allocation": "5%",
          "risk_override": true,
          "execute_trade": true
        }
        """
    )

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "extra fields" in result.error_message


def test_invalid_suggested_expression_is_rejected() -> None:
    client = FakeClaudeClient(
        """
        {
          "recommendation": "go",
          "thesis": "NTNX has a bullish AI_STORAGE read-through from strong peer earnings.",
          "reasoning": "Use puts despite bullish setup.",
          "conviction_score": 70,
          "missing_context": [],
          "contradictions": [],
          "suggested_expression": "PUT_OPTION"
        }
        """
    )

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "suggested_expression" in result.error_message


def test_needs_more_context_supports_missing_context_items() -> None:
    client = FakeClaudeClient(
        """
        {
          "recommendation": "needs_more_context",
          "thesis": "NTNX has a plausible AI_STORAGE read-through but needs one more structured check.",
          "reasoning": "Need one more structured confirmation before go/no-go.",
          "conviction_score": 55,
          "missing_context": ["latest management commentary summary"],
          "contradictions": ["target already moved before earnings"],
          "suggested_expression": "NONE"
        }
        """
    )

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.ANALYZED
    assert result.analysis is not None
    assert result.analysis.recommendation == ClaudeRecommendation.NEEDS_MORE_CONTEXT
    assert result.analysis.thesis == (
        "NTNX has a plausible AI_STORAGE read-through but needs one more structured check."
    )
    assert result.analysis.conviction_score == 55
    assert result.analysis.missing_context == ["latest management commentary summary"]
    assert result.analysis.suggested_expression == "NONE"


@pytest.mark.parametrize("missing_field", ["thesis", "conviction_score"])
def test_missing_r2_5_required_fields_are_rejected(missing_field: str) -> None:
    response = {
        "recommendation": "go",
        "thesis": "NTNX has a bullish AI_STORAGE read-through from strong peer earnings.",
        "reasoning": "Peer read-through is strong.",
        "conviction_score": 80,
        "missing_context": [],
        "contradictions": [],
        "suggested_expression": "CALL_OPTION",
    }
    response.pop(missing_field)
    client = FakeClaudeClient(json.dumps(response))

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert missing_field in result.error_message


@pytest.mark.parametrize("conviction_score", [-1, 101, "80", 80.5, True])
def test_invalid_conviction_scores_are_rejected(conviction_score: object) -> None:
    client = FakeClaudeClient(
        json.dumps(
            {
                "recommendation": "go",
                "thesis": (
                    "NTNX has a bullish AI_STORAGE read-through from strong peer earnings."
                ),
                "reasoning": "Peer read-through is strong.",
                "conviction_score": conviction_score,
                "missing_context": [],
                "contradictions": [],
                "suggested_expression": "CALL_OPTION",
            }
        )
    )

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "conviction_score" in result.error_message


def test_same_input_and_fake_response_produce_equal_serialized_output() -> None:
    brief = _candidate_brief()
    first = analyze_candidate_brief(brief, client=FakeClaudeClient(_valid_response()))
    second = analyze_candidate_brief(brief, client=FakeClaudeClient(_valid_response()))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
