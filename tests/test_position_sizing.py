from __future__ import annotations

from datetime import date

from prescient.risk import (
    AccountRiskSnapshot,
    PositionSizingRejectionReason,
    PositionSizingStatus,
    RiskReviewFlag,
    RiskSettings,
    TradeExpression,
    TradeProposal,
    size_position,
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
        supporting_evidence=["2 of 2 peers had positive scores."],
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


def _account(
    *,
    equity: float = 5_000.0,
    cash: float = 5_000.0,
    buying_power: float = 5_000.0,
) -> AccountRiskSnapshot:
    return AccountRiskSnapshot(equity=equity, cash=cash, buying_power=buying_power)


def _call_proposal(entry_price: float = 0.60) -> TradeProposal:
    return TradeProposal(
        target="ntnx",
        expression=TradeExpression.CALL_OPTION,
        entry_price=entry_price,
        stop_price=None,
        contract_multiplier=100,
        minimum_quantity=1,
    )


def _stock_proposal(
    *,
    entry_price: float = 25.0,
    stop_price: float | None = 13.0,
) -> TradeProposal:
    return TradeProposal(
        target="ntnx",
        expression=TradeExpression.STOCK,
        entry_price=entry_price,
        stop_price=stop_price,
        minimum_quantity=1,
    )


def test_candidate_ready_call_option_sizes_to_floor_quantity() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
    )

    assert decision.status == PositionSizingStatus.SIZED
    assert decision.target == "NTNX"
    assert decision.theme == "AI_STORAGE"
    assert decision.expression == TradeExpression.CALL_OPTION
    assert decision.account_equity == 5_000.0
    assert decision.risk_budget == 150.0
    assert decision.unit_max_loss == 60.0
    assert decision.approved_quantity == 2
    assert decision.projected_max_loss == 120.0
    assert decision.entry_cost_required == 120.0
    assert decision.rejection_reasons == []
    assert RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW in decision.warnings


def test_candidate_ready_stock_sizes_to_floor_quantity() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_stock_proposal(entry_price=25.0, stop_price=13.0),
    )

    assert decision.status == PositionSizingStatus.SIZED
    assert decision.expression == TradeExpression.STOCK
    assert decision.risk_budget == 150.0
    assert decision.unit_max_loss == 12.0
    assert decision.approved_quantity == 12
    assert decision.projected_max_loss == 144.0
    assert decision.entry_cost_required == 300.0


def test_option_contract_larger_than_budget_is_blocked() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=2.00),
    )

    assert decision.status == PositionSizingStatus.BLOCKED
    assert decision.risk_budget == 150.0
    assert decision.unit_max_loss == 200.0
    assert decision.approved_quantity == 0
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.SMALLEST_TRADE_EXCEEDS_RISK_BUDGET
    ]


def test_stock_without_stop_is_not_evaluable() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_stock_proposal(stop_price=None),
    )

    assert decision.status == PositionSizingStatus.NOT_EVALUABLE
    assert decision.unit_max_loss is None
    assert decision.approved_quantity == 0
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.STOP_PRICE_MISSING,
        PositionSizingRejectionReason.MAX_LOSS_NOT_COMPUTABLE,
    ]


def test_non_candidate_strategy_decision_is_blocked() -> None:
    decision = size_position(_no_trade_decision())

    assert decision.status == PositionSizingStatus.BLOCKED
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.STRATEGY_NOT_CANDIDATE_READY
    ]
    assert decision.approved_quantity == 0


def test_missing_account_snapshot_is_not_evaluable() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        proposal=_call_proposal(),
    )

    assert decision.status == PositionSizingStatus.NOT_EVALUABLE
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.MISSING_ACCOUNT_SNAPSHOT
    ]


def test_missing_order_proposal_is_not_evaluable() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(),
    )

    assert decision.status == PositionSizingStatus.NOT_EVALUABLE
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.MISSING_ORDER_PROPOSAL
    ]


def test_insufficient_cash_or_buying_power_blocks_after_quantity_math() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0, cash=100.0, buying_power=500.0),
        proposal=_call_proposal(entry_price=0.60),
    )

    assert decision.status == PositionSizingStatus.BLOCKED
    assert decision.approved_quantity == 0
    assert decision.risk_budget == 150.0
    assert decision.unit_max_loss == 60.0
    assert decision.projected_max_loss is None
    assert decision.entry_cost_required == 120.0
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.INSUFFICIENT_CASH_OR_BUYING_POWER
    ]


def test_unsafe_claude_sizing_fields_block_as_override_attempt() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(),
        proposal=_call_proposal(entry_price=0.60),
        claude_advisory={
            "recommendation": "go",
            "nested": {"shares": 100, "risk_override": True},
        },
    )

    assert decision.status == PositionSizingStatus.BLOCKED
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.CLAUDE_SIZING_OVERRIDE_ATTEMPTED
    ]
    assert decision.claude_present is True
    assert decision.claude_sizing_override_attempted is True


def test_safe_claude_metadata_does_not_change_position_size() -> None:
    base = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
    )
    with_claude = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
        claude_advisory={
            "recommendation": "go",
            "thesis": "Structured advisory text only.",
            "conviction_score": 80,
        },
    )

    assert with_claude.status == base.status
    assert with_claude.approved_quantity == base.approved_quantity
    assert with_claude.projected_max_loss == base.projected_max_loss
    assert with_claude.entry_cost_required == base.entry_cost_required
    assert with_claude.claude_present is True
    assert with_claude.claude_sizing_override_attempted is False


def test_same_input_serializes_deterministically() -> None:
    first = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
        settings=RiskSettings(max_trade_loss_pct=0.03),
        claude_advisory={"recommendation": "go"},
    )
    second = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
        settings=RiskSettings(max_trade_loss_pct=0.03),
        claude_advisory={"recommendation": "go"},
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_sizing_output_is_journal_safe() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account(equity=5_000.0),
        proposal=_call_proposal(entry_price=0.60),
        claude_advisory={"recommendation": "go"},
    )
    serialized = decision.model_dump(mode="json")

    assert serialized["target"] == "NTNX"
    assert serialized["theme"] == "AI_STORAGE"
    assert serialized["strategy_status"] == "candidate_ready_for_analyst"
    assert serialized["approved_quantity"] == 2
    assert "account_id" not in serialized
    assert "api_key" not in serialized
    assert "credential" not in serialized
    assert "prompt" not in serialized
