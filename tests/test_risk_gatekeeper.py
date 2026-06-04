from __future__ import annotations

from datetime import date
from pathlib import Path

from prescient.risk import (
    AccountRiskSnapshot,
    RiskGateStatus,
    RiskOrderProposal,
    RiskRejectionReason,
    evaluate_risk_gate,
)
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


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


def _account_snapshot() -> AccountRiskSnapshot:
    return AccountRiskSnapshot(
        equity=5_000.0,
        cash=5_000.0,
        buying_power=5_000.0,
    )


def _order_proposal() -> RiskOrderProposal:
    return RiskOrderProposal(
        target="NTNX",
        expression="CALL_OPTION",
        estimated_entry_cost=100.0,
        maximum_loss=100.0,
    )


def test_no_trade_strategy_decision_is_blocked() -> None:
    decision = evaluate_risk_gate(_no_trade_decision())

    assert decision.status == RiskGateStatus.BLOCKED
    assert decision.rejection_reasons == [
        RiskRejectionReason.STRATEGY_NOT_CANDIDATE_READY
    ]
    assert decision.broker_execution_allowed is False
    assert decision.claude_present is False
    assert decision.claude_override_attempted is False


def test_candidate_ready_without_account_snapshot_is_not_evaluable() -> None:
    decision = evaluate_risk_gate(_candidate_ready_decision())

    assert decision.status == RiskGateStatus.NOT_EVALUABLE
    assert decision.rejection_reasons == [RiskRejectionReason.MISSING_ACCOUNT_SNAPSHOT]
    assert decision.broker_execution_allowed is False


def test_candidate_ready_with_account_but_no_order_proposal_is_not_evaluable() -> None:
    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
    )

    assert decision.status == RiskGateStatus.NOT_EVALUABLE
    assert decision.rejection_reasons == [RiskRejectionReason.MISSING_ORDER_PROPOSAL]
    assert decision.broker_execution_allowed is False


def test_candidate_ready_with_required_inputs_still_fails_closed_until_r3_2() -> None:
    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
    )

    assert decision.status == RiskGateStatus.NOT_EVALUABLE
    assert decision.rejection_reasons == [RiskRejectionReason.RISK_CHECKS_NOT_IMPLEMENTED]
    assert decision.broker_execution_allowed is False
    assert "R3.2" in decision.explanation


def test_unsafe_claude_advisory_blocks_as_override_attempt() -> None:
    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
        claude_advisory={
            "recommendation": "go",
            "nested": {"risk_override": True, "order_quantity": 5},
        },
    )

    assert decision.status == RiskGateStatus.BLOCKED
    assert decision.rejection_reasons == [
        RiskRejectionReason.CLAUDE_OVERRIDE_ATTEMPTED
    ]
    assert decision.claude_present is True
    assert decision.claude_override_attempted is True
    assert decision.broker_execution_allowed is False


def test_safe_claude_advisory_does_not_change_risk_outcome() -> None:
    base = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
    )
    with_advisory = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
        claude_advisory={
            "recommendation": "go",
            "thesis": "Structured thesis only.",
            "confidence": 80,
        },
    )

    assert with_advisory.status == base.status
    assert with_advisory.rejection_reasons == base.rejection_reasons
    assert with_advisory.broker_execution_allowed is False
    assert with_advisory.claude_present is True
    assert with_advisory.claude_override_attempted is False


def test_same_input_serializes_deterministically() -> None:
    first = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
        claude_advisory={"recommendation": "go"},
    )
    second = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
        claude_advisory={"recommendation": "go"},
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_risk_decision_is_journal_safe() -> None:
    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
        claude_advisory={"recommendation": "go"},
    )
    serialized = decision.model_dump(mode="json")

    assert serialized["target"] == "NTNX"
    assert serialized["theme"] == "AI_STORAGE"
    assert serialized["strategy_status"] == "candidate_ready_for_analyst"
    assert "broker_execution_allowed" in serialized
    assert "claude_present" in serialized
    assert "claude_override_attempted" in serialized
    assert "account_id" not in serialized
    assert "api_key" not in serialized
    assert "credential" not in serialized
    assert "prompt" not in serialized


def test_broker_execution_allowed_only_when_status_is_approved() -> None:
    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_order_proposal(),
    )

    assert decision.status != RiskGateStatus.APPROVED
    assert decision.broker_execution_allowed is False


def test_risk_package_has_no_forbidden_boundary_imports() -> None:
    risk_files = Path("src/prescient/risk").glob("*.py")
    forbidden_terms = [
        "prescient.analyst",
        "anthropic",
        "prescient.broker",
        "prescient.runtime",
        "prescient.events",
        "prescient.scheduler",
        "requests",
        "httpx",
        "urllib",
        "os.environ",
        "dotenv",
        "open(",
    ]

    offenders = [
        path
        for path in risk_files
        if any(term in path.read_text() for term in forbidden_terms)
    ]

    assert offenders == []
