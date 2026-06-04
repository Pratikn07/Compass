from __future__ import annotations

from argparse import _StoreAction
from datetime import date
from unittest.mock import MagicMock

import pytest

from prescient.broker import get_broker_adapter
from prescient.broker.execution_guard import KillSwitchBrokerWrapper, ProposeOnlyBrokerWrapper
from prescient.broker.mock import MockBrokerAdapter
from prescient.broker.models import BrokerExecutionError, BrokerOrderStatus, BrokerSettings
from prescient.main import _build_parser
from prescient.risk import (
    AccountRiskSnapshot,
    PositionSizingDecision,
    PositionSizingRejectionReason,
    PositionSizingStatus,
    RiskGateStatus,
    RiskOrderProposal,
    RiskRejectionReason,
    RiskReviewFlag,
    TradeExpression,
    TradeProposal,
    evaluate_risk_gate,
    size_position,
)
from prescient.risk.account_policy import _coerce_execution_mode
from prescient.risk.models import ExecutionMode
from prescient.risk.safety import UNSAFE_CLAUDE_KEYS, contains_unsafe_claude_key
from prescient.runtime.execution import preflight_and_execute
from prescient.safety import KillSwitchState, KillSwitchStatus
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


def _account_snapshot() -> AccountRiskSnapshot:
    return AccountRiskSnapshot(equity=5_000.0, cash=5_000.0, buying_power=5_000.0)


def _risk_order_proposal() -> RiskOrderProposal:
    return RiskOrderProposal(
        target="NTNX",
        expression="CALL_OPTION",
        estimated_entry_cost=120.0,
        maximum_loss=120.0,
    )


def _call_trade_proposal() -> TradeProposal:
    return TradeProposal(
        target="NTNX",
        expression=TradeExpression.CALL_OPTION,
        entry_price=0.60,
        stop_price=None,
        contract_multiplier=100,
        minimum_quantity=1,
    )


def _unsafe_claude_advisory() -> dict[str, object]:
    return {
        "recommendation": "go",
        "risk_override": True,
        "execute_trade": True,
        "nested": {
            "broker_action": "buy",
            "order_quantity": 5,
        },
    }


def _safe_claude_advisory() -> dict[str, object]:
    return {
        "summary": "Strong peer read-through, advisory only.",
        "conviction_score": 82,
        "citations": ["candidate-brief"],
        "recommendation": "go",
    }


def _provider(status: KillSwitchStatus) -> MagicMock:
    provider = MagicMock()
    provider.read_state.return_value = KillSwitchState(status=status)
    return provider


def _sized_decision() -> PositionSizingDecision:
    return PositionSizingDecision(
        status=PositionSizingStatus.SIZED,
        target="NTNX",
        theme="AI_STORAGE",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        expression=TradeExpression.CALL_OPTION,
        account_equity=5_000.0,
        risk_budget=150.0,
        unit_max_loss=60.0,
        approved_quantity=2,
        projected_max_loss=120.0,
        entry_cost_required=120.0,
        rejection_reasons=[],
        warnings=[RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW],
        explanation="Sized only to prove unsafe Claude advisory is blocked downstream.",
        claude_present=False,
        claude_sizing_override_attempted=False,
    )


def _find_action(parser, option: str) -> _StoreAction | None:
    for action in parser._actions:
        if option in action.option_strings:
            assert isinstance(action, _StoreAction)
            return action
        for choice_parser in (getattr(action, "choices", None) or {}).values():
            found = _find_action(choice_parser, option)
            if found is not None:
                return found
    return None


def test_unsafe_claude_keys_are_detected_case_insensitively_and_recursively() -> None:
    for unsafe_key in UNSAFE_CLAUDE_KEYS:
        advisory = {
            "summary": "advisory text",
            "nested": [
                {"safe": "value"},
                {unsafe_key.upper(): "unsafe value"},
            ],
        }

        assert contains_unsafe_claude_key(advisory) is True

    assert contains_unsafe_claude_key(_safe_claude_advisory()) is False


def test_unsafe_claude_payload_blocks_risk_gate_even_when_trade_would_otherwise_be_approvable() -> None:
    base = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_risk_order_proposal(),
        broker_positions=[],
    )

    decision = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_risk_order_proposal(),
        claude_advisory=_unsafe_claude_advisory(),
        broker_positions=[],
    )

    assert base.status == RiskGateStatus.APPROVED
    assert decision.status == RiskGateStatus.BLOCKED
    assert decision.broker_execution_allowed is False
    assert decision.claude_override_attempted is True
    assert decision.rejection_reasons == [RiskRejectionReason.CLAUDE_OVERRIDE_ATTEMPTED]


def test_unsafe_claude_payload_blocks_position_sizing_before_quantity_approval() -> None:
    decision = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        proposal=_call_trade_proposal(),
        claude_advisory=_unsafe_claude_advisory(),
    )

    assert decision.status == PositionSizingStatus.BLOCKED
    assert decision.approved_quantity == 0
    assert decision.claude_sizing_override_attempted is True
    assert decision.rejection_reasons == [
        PositionSizingRejectionReason.CLAUDE_SIZING_OVERRIDE_ATTEMPTED
    ]


def test_safe_claude_metadata_does_not_change_gate_or_sizing_outcomes() -> None:
    base_gate = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_risk_order_proposal(),
        broker_positions=[],
    )
    advisory_gate = evaluate_risk_gate(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_risk_order_proposal(),
        claude_advisory=_safe_claude_advisory(),
        broker_positions=[],
    )
    base_sizing = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        proposal=_call_trade_proposal(),
    )
    advisory_sizing = size_position(
        _candidate_ready_decision(),
        account_snapshot=_account_snapshot(),
        proposal=_call_trade_proposal(),
        claude_advisory=_safe_claude_advisory(),
    )

    assert advisory_gate.status == base_gate.status
    assert advisory_gate.rejection_reasons == base_gate.rejection_reasons
    assert advisory_gate.broker_execution_allowed == base_gate.broker_execution_allowed
    assert advisory_gate.claude_override_attempted is False
    assert advisory_sizing.status == base_sizing.status
    assert advisory_sizing.approved_quantity == base_sizing.approved_quantity
    assert advisory_sizing.projected_max_loss == base_sizing.projected_max_loss
    assert advisory_sizing.claude_sizing_override_attempted is False


def test_claude_cannot_promote_non_candidate_strategy_decision() -> None:
    advisory = {"recommendation": "go", "analyst_decision": "approved"}
    gate = evaluate_risk_gate(
        _no_trade_decision(),
        account_snapshot=_account_snapshot(),
        order_proposal=_risk_order_proposal(),
        claude_advisory=advisory,
        broker_positions=[],
    )
    sizing = size_position(
        _no_trade_decision(),
        account_snapshot=_account_snapshot(),
        proposal=_call_trade_proposal(),
        claude_advisory=advisory,
    )

    assert gate.status == RiskGateStatus.BLOCKED
    assert gate.rejection_reasons == [RiskRejectionReason.STRATEGY_NOT_CANDIDATE_READY]
    assert gate.broker_execution_allowed is False
    assert sizing.status == PositionSizingStatus.BLOCKED
    assert sizing.rejection_reasons == [
        PositionSizingRejectionReason.STRATEGY_NOT_CANDIDATE_READY
    ]
    assert sizing.approved_quantity == 0


def test_unsafe_claude_advisory_does_not_reach_broker_order_placement(monkeypatch) -> None:
    broker = MagicMock()
    monkeypatch.setattr("prescient.runtime.execution.size_position", lambda *a, **k: _sized_decision())

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        claude_advisory=_unsafe_claude_advisory(),
    )

    broker.place_order.assert_not_called()


def test_execution_mode_defaults_remain_propose_only() -> None:
    execution_mode_action = _find_action(_build_parser(), "--execution-mode")

    assert execution_mode_action is not None
    assert _coerce_execution_mode(None) == ExecutionMode.PROPOSE_ONLY
    assert BrokerSettings().execution_mode == ExecutionMode.PROPOSE_ONLY
    assert execution_mode_action.default == "propose_only"


def test_live_mode_requires_explicit_input() -> None:
    assert _coerce_execution_mode("live") == ExecutionMode.LIVE
    assert _coerce_execution_mode(None) != ExecutionMode.LIVE

    with pytest.raises(ValueError):
        _coerce_execution_mode("")

    with pytest.raises(ValueError):
        _coerce_execution_mode("LIVE")


def test_propose_only_factory_intercepts_order_without_mutating_inner_broker() -> None:
    adapter = get_broker_adapter(
        "mock",
        "propose_only",
        kill_switch_provider=_provider(KillSwitchStatus.INACTIVE),
    )

    assert isinstance(adapter, KillSwitchBrokerWrapper)
    assert isinstance(adapter._inner, ProposeOnlyBrokerWrapper)
    assert isinstance(adapter._inner._inner, MockBrokerAdapter)
    inner = adapter._inner._inner
    before_cash = inner.account_cash
    before_buying_power = inner.account_buying_power
    before_positions = list(inner.positions_list)
    before_orders = list(inner.orders_list)

    result = adapter.place_order(_risk_order_proposal())

    assert result.status == BrokerOrderStatus.OPEN
    assert result.order_id.startswith("propose-only-")
    assert inner.account_cash == before_cash
    assert inner.account_buying_power == before_buying_power
    assert inner.positions_list == before_positions
    assert inner.orders_list == before_orders


def test_active_kill_switch_blocks_propose_only_order_before_virtual_result() -> None:
    adapter = get_broker_adapter(
        "mock",
        "propose_only",
        kill_switch_provider=_provider(KillSwitchStatus.ACTIVE),
    )
    inner = adapter._inner._inner
    before_cash = inner.account_cash
    before_buying_power = inner.account_buying_power
    before_positions = list(inner.positions_list)
    before_orders = list(inner.orders_list)

    with pytest.raises(BrokerExecutionError, match="Kill switch active"):
        adapter.place_order(_risk_order_proposal())

    assert inner.account_cash == before_cash
    assert inner.account_buying_power == before_buying_power
    assert inner.positions_list == before_positions
    assert inner.orders_list == before_orders
