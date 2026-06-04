from __future__ import annotations

from datetime import UTC, date, datetime

from prescient.broker import BrokerOrderStatus, OrderExecutionResult
from prescient.journal import DecisionLayer, DecisionType
from prescient.risk import (
    AccountRiskSnapshot,
    AccountSnapshot,
    DailyRiskAction,
    DailyRiskState,
    ExecutionQuoteSnapshot,
    MarketSessionSnapshot,
    MarketSessionStatus,
    RewardRiskProposal,
    RiskDecisionStatus,
    RiskSettings,
    TradeExpression,
    TradeProposal,
    evaluate_account_size_policy,
    evaluate_daily_halt,
    evaluate_execution_quality,
    evaluate_risk_gate,
    evaluate_trade_risk,
    size_position,
)
from prescient.signal import DecisionAudit, StrategyDecision, StrategyStatus
from prescient.signal import CandidateBrief, PeerScore


def _candidate_decision() -> StrategyDecision:
    candidate = CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 10),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=3.0,
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
    )
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=candidate,
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
            target="NTNX",
            theme="AI_STORAGE",
            peer_scores=[],
            thresholds={},
            missing_peer_factor_count=0,
            all_peer_data_missing=False,
            target_market_data_present=True,
            option_contract_count=0,
        ),
        claude_analysis_allowed=True,
    )


def test_trade_risk_and_position_sizing_include_internal_rule_audits() -> None:
    account = AccountSnapshot(account_equity=5_000.0)
    proposal = TradeProposal(
        target="NTNX",
        expression=TradeExpression.CALL_OPTION,
        entry_price=0.60,
        contract_multiplier=100,
    )

    trade_risk = evaluate_trade_risk(account, proposal, RiskSettings(max_trade_loss_pct=0.03))
    sizing = size_position(
        _candidate_decision(),
        account_snapshot=AccountRiskSnapshot(equity=5_000, cash=5_000, buying_power=5_000),
        proposal=proposal,
    )

    assert trade_risk.status == RiskDecisionStatus.REVIEW_REQUIRED
    assert trade_risk.audit_trail.decision_layer == DecisionLayer.RISK
    assert any(c.source_type == "risk_rule" for c in trade_risk.audit_trail.source_citations)
    assert sizing.audit_trail.decision_type == DecisionType.POSITION_SIZING
    assert sizing.audit_trail.source_citations


def test_risk_gate_daily_halt_execution_quality_and_account_policy_have_audits() -> None:
    gate = evaluate_risk_gate(
        _candidate_decision(),
        account_snapshot=AccountRiskSnapshot(equity=5_000, cash=5_000, buying_power=5_000),
        order_proposal=None,
    )
    halt = evaluate_daily_halt(
        DailyRiskState(
            account_equity=5_000,
            trading_day=date(2026, 6, 2),
            realized_pnl=-100,
            losing_trade_count=0,
        )
    )
    quality = evaluate_execution_quality(
        DailyRiskAction.NEW_ENTRY,
        session=MarketSessionSnapshot(
            market_date=date(2026, 6, 2),
            session_status=MarketSessionStatus.REGULAR_OPEN,
            minutes_to_close=60,
        ),
        quote=ExecutionQuoteSnapshot(
            target="NTNX",
            expression=TradeExpression.STOCK,
            bid=100.0,
            ask=100.2,
            avg_daily_volume=2_000_000,
            quote_age_seconds=2,
        ),
        reward_risk=RewardRiskProposal(expected_reward=4.0, maximum_loss=2.0),
    )
    policy = evaluate_account_size_policy(AccountSnapshot(account_equity=12_000))

    for dumped in [
        gate.model_dump_json(),
        halt.model_dump_json(),
        quality.model_dump_json(),
        policy.model_dump_json(),
    ]:
        assert "api_key" not in dumped
        assert "account_id" not in dumped
    assert gate.audit_trail.source_citations
    assert halt.audit_trail.source_citations
    assert quality.audit_trail.source_citations
    assert policy.audit_trail.source_citations


def test_broker_execution_result_has_journal_safe_audit_trail() -> None:
    result = OrderExecutionResult(
        broker="alpaca",
        status=BrokerOrderStatus.SUBMITTED,
        order_id="order-123",
        submitted_at=datetime(2026, 6, 2, 14, 30, tzinfo=UTC),
        message="paper order accepted",
    )

    assert result.audit_trail.decision_layer == DecisionLayer.BROKER
    assert result.audit_trail.decision_type == DecisionType.BROKER_ORDER_RESULT
    dumped = result.model_dump_json()
    assert "paper order accepted" in dumped
    assert "Authorization" not in dumped
