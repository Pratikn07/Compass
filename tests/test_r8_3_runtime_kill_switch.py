from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from prescient.broker.models import BrokerExecutionError
from prescient.risk.models import AccountRiskSnapshot
from prescient.runtime.execution import preflight_and_execute
from prescient.safety import KillSwitchState, KillSwitchStatus
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


def _account_snapshot() -> AccountRiskSnapshot:
    return AccountRiskSnapshot(
        equity=50_000.0,
        cash=10_000.0,
        buying_power=20_000.0,
    )


def _peer_scores() -> list[PeerScore]:
    return [
        PeerScore(ticker="NTAP", score=5, positive_factors=["revenue_beat"]),
        PeerScore(ticker="PSTG", score=4, positive_factors=["positive_guidance"]),
    ]


def _candidate_ready_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=CandidateBrief(
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
        ),
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
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
        ),
        claude_analysis_allowed=True,
    )


def test_runtime_skips_order_when_kill_switch_is_active() -> None:
    broker = MagicMock()
    provider = MagicMock()
    provider.read_state.return_value = KillSwitchState(status=KillSwitchStatus.ACTIVE)

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        kill_switch_provider=provider,
    )

    broker.place_order.assert_not_called()


def test_runtime_fails_closed_when_kill_switch_state_cannot_be_read() -> None:
    broker = MagicMock()
    provider = MagicMock()
    provider.read_state.side_effect = BrokerExecutionError("state unavailable")

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        kill_switch_provider=provider,
    )

    broker.place_order.assert_not_called()
