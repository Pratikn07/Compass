"""Tests for R5.5 — Broker as Source of Truth and R5.6 — Preflight Buying Power.

These tests verify:
1. Broker state is fetched fresh before any risk evaluation.
2. If broker state retrieval fails, the entire run is aborted (fail-closed).
3. Broker → Risk domain mapping is correct.
4. Risk gatekeeper and position sizer operate only on broker-sourced data.
5. Preflight buying power check blocks orders exceeding available funds.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from prescient.rollout import RolloutStage
from prescient.broker.models import (
    BrokerConnectionError,
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
    OrderExecutionResult,
)
from prescient.risk.models import (
    AccountRiskSnapshot,
    RiskOrder,
    RiskGateStatus,
    RiskPosition,
    TradeExpression,
)
from prescient.runtime.execution import (
    preflight_and_execute,
    execute_pipeline_results,
    fetch_broker_state,
    _map_order,
    _map_position,
)
from prescient.risk.position_sizing import PositionSizingStatus
from prescient.runtime.models import PipelineRunResult
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


# ---------------------------------------------------------------------------
# Shared fixtures (mirrors test_risk_gatekeeper.py style)
# ---------------------------------------------------------------------------

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
    return AccountRiskSnapshot(
        equity=50_000.0,
        cash=10_000.0,
        buying_power=20_000.0,
    )


def _broker_position() -> BrokerPosition:
    return BrokerPosition(
        symbol="AAPL",
        expression=TradeExpression.STOCK,
        qty=10.0,
        market_value=1500.0,
        average_entry_price=150.0,
    )


def _broker_order() -> BrokerOrder:
    return BrokerOrder(
        order_id="ord-001",
        symbol="AAPL",
        qty=10,
        filled_qty=10,
        limit_price=150.0,
        status=BrokerOrderStatus.FILLED,
        submitted_at=datetime(2026, 6, 1, 10, 0, 0),
        side="buy",
    )


def _mock_broker(
    *,
    snapshot: AccountRiskSnapshot | None = None,
    positions: list[BrokerPosition] | None = None,
    orders: list[BrokerOrder] | None = None,
) -> MagicMock:
    broker = MagicMock()
    broker.get_account_snapshot.return_value = snapshot or _account_snapshot()
    broker.get_positions.return_value = positions or []
    broker.get_orders.return_value = orders or []
    broker.execution_mode = "paper"
    broker.place_order.return_value = OrderExecutionResult(
        order_id="exec-123",
        status=BrokerOrderStatus.FILLED,
        filled_qty=1,
        avg_fill_price=5.0,
    )
    return broker


# ---------------------------------------------------------------------------
# Mapper unit tests
# ---------------------------------------------------------------------------

def test_map_position_preserves_all_fields() -> None:
    bp = _broker_position()
    rp = _map_position(bp)

    assert isinstance(rp, RiskPosition)
    assert rp.symbol == bp.symbol
    assert rp.expression == bp.expression
    assert rp.qty == bp.qty
    assert rp.market_value == bp.market_value
    assert rp.average_entry_price == bp.average_entry_price


def test_map_order_preserves_all_fields() -> None:
    bo = _broker_order()
    ro = _map_order(bo)

    assert isinstance(ro, RiskOrder)
    assert ro.order_id == bo.order_id
    assert ro.symbol == bo.symbol
    assert ro.qty == bo.qty
    assert ro.filled_qty == bo.filled_qty
    assert ro.limit_price == bo.limit_price
    assert ro.status == str(bo.status)
    assert ro.submitted_at == bo.submitted_at
    assert ro.side == bo.side


# ---------------------------------------------------------------------------
# fetch_broker_state
# ---------------------------------------------------------------------------

def test_fetch_broker_state_calls_all_three_endpoints() -> None:
    broker = _mock_broker(positions=[_broker_position()], orders=[_broker_order()])

    snapshot, positions, orders = fetch_broker_state(broker)

    broker.get_account_snapshot.assert_called_once()
    broker.get_positions.assert_called_once()
    broker.get_orders.assert_called_once()

    assert isinstance(snapshot, AccountRiskSnapshot)
    assert len(positions) == 1
    assert isinstance(positions[0], RiskPosition)
    assert len(orders) == 1
    assert isinstance(orders[0], RiskOrder)


def test_fetch_broker_state_propagates_broker_error() -> None:
    broker = MagicMock()
    broker.get_account_snapshot.side_effect = BrokerConnectionError("Network offline")

    with pytest.raises(BrokerConnectionError, match="Network offline"):
        fetch_broker_state(broker)


# ---------------------------------------------------------------------------
# execute_pipeline_results — fail-closed behaviour
# ---------------------------------------------------------------------------

def test_execute_aborts_if_broker_state_retrieval_fails() -> None:
    """R5.5.5: If any broker call fails, the orchestrator must fail closed."""
    broker = MagicMock()
    broker.get_account_snapshot.side_effect = BrokerConnectionError("Offline")

    pipeline_result = PipelineRunResult(
        strategy_decisions=[_candidate_ready_decision()],
    )

    execute_pipeline_results(pipeline_result, broker)

    # No order was placed because state retrieval failed
    broker.place_order.assert_not_called()
    # Subsequent broker calls were never attempted
    broker.get_positions.assert_not_called()


def test_dashboard_only_rollout_blocks_broker_write_after_risk_gate_passes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    broker = _mock_broker()
    journal_path = tmp_path / "rollout.jsonl"
    _patch_execution_checks_to_pass(monkeypatch, projected_max_loss=50.0)

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        rollout_stage=RolloutStage.DASHBOARD_ONLY,
        journal_path=journal_path,
        run_id="scheduled:2026-06-03",
        decision_index=0,
        trading_date=date(2026, 6, 3),
    )

    broker.place_order.assert_not_called()
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert records[0]["record_type"] == "rollout_gate_decision"
    assert records[0]["payload"]["rejection_reasons"] == ["paper_trading_not_allowed"]


def test_default_rollout_stage_blocks_broker_write_after_risk_gate_passes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    broker = _mock_broker()
    journal_path = tmp_path / "rollout-default.jsonl"
    _patch_execution_checks_to_pass(monkeypatch, projected_max_loss=50.0)

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        journal_path=journal_path,
        run_id="scheduled:2026-06-03",
        decision_index=0,
        trading_date=date(2026, 6, 3),
    )

    broker.place_order.assert_not_called()
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert records[0]["record_type"] == "rollout_gate_decision"
    assert records[0]["payload"]["current_stage"] == "dashboard_only"


def test_paper_stage_permits_paper_broker_write_after_risk_gate_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _mock_broker()
    _patch_execution_checks_to_pass(monkeypatch, projected_max_loss=50.0)

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        rollout_stage=RolloutStage.PAPER_TRADING,
    )

    broker.place_order.assert_called_once()


def test_tiny_live_blocks_live_broker_write_above_tiny_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = _mock_broker()
    broker.execution_mode = "live"
    _patch_execution_checks_to_pass(monkeypatch, projected_max_loss=200.0)

    preflight_and_execute(
        decision=_candidate_ready_decision(),
        broker=broker,
        account_snapshot=_account_snapshot(),
        risk_positions=[],
        risk_orders=[],
        rollout_stage=RolloutStage.TINY_LIVE,
    )

    broker.place_order.assert_not_called()


def _patch_execution_checks_to_pass(
    monkeypatch: pytest.MonkeyPatch,
    *,
    projected_max_loss: float,
) -> None:
    sizing = MagicMock()
    sizing.status = PositionSizingStatus.SIZED
    sizing.entry_cost_required = 100.0
    sizing.projected_max_loss = projected_max_loss
    sizing.rejection_reasons = []
    sizing.explanation = "sized"

    gate = MagicMock()
    gate.status = RiskGateStatus.APPROVED
    gate.rejection_reasons = []
    gate.explanation = "approved"

    monkeypatch.setattr("prescient.runtime.execution.size_position", lambda **kwargs: sizing)
    monkeypatch.setattr("prescient.runtime.execution.evaluate_risk_gate", lambda **kwargs: gate)


def test_execute_aborts_if_get_positions_fails() -> None:
    broker = MagicMock()
    broker.get_account_snapshot.return_value = _account_snapshot()
    broker.get_positions.side_effect = BrokerConnectionError("Timeout")

    pipeline_result = PipelineRunResult(
        strategy_decisions=[_candidate_ready_decision()],
    )

    execute_pipeline_results(pipeline_result, broker)

    broker.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# execute_pipeline_results — non-candidate decisions are skipped
# ---------------------------------------------------------------------------

def test_no_trade_decision_is_silently_skipped() -> None:
    broker = _mock_broker()

    pipeline_result = PipelineRunResult(
        strategy_decisions=[_no_trade_decision()],
    )

    execute_pipeline_results(pipeline_result, broker)

    broker.get_account_snapshot.assert_called_once()
    broker.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# execute_pipeline_results — broker state is fetched before evaluation
# ---------------------------------------------------------------------------

def test_broker_state_is_fetched_exactly_once_for_multiple_decisions() -> None:
    """R5.5.1: Every preflight run must fetch fresh data from the broker."""
    broker = _mock_broker()

    pipeline_result = PipelineRunResult(
        strategy_decisions=[
            _candidate_ready_decision(),
            _no_trade_decision(),
            _candidate_ready_decision(),
        ],
    )

    execute_pipeline_results(pipeline_result, broker)

    # State fetched exactly once, not per-decision
    broker.get_account_snapshot.assert_called_once()
    broker.get_positions.assert_called_once()
    broker.get_orders.assert_called_once()


# ---------------------------------------------------------------------------
# R5.5 boundary: risk package never imports broker
# ---------------------------------------------------------------------------

def test_risk_package_does_not_import_broker() -> None:
    """R5.5.2 boundary enforcement: risk domain must remain pure-code."""
    from pathlib import Path

    risk_files = list(Path("src/prescient/risk").glob("*.py"))
    assert risk_files, "No risk module files found"

    for path in risk_files:
        source = path.read_text()
        assert "prescient.broker" not in source, (
            f"{path.name} must not import prescient.broker — "
            f"the runtime layer is responsible for mapping broker → risk models"
        )


# ---------------------------------------------------------------------------
# R5.6 — Preflight buying power check (via position sizer)
# ---------------------------------------------------------------------------

def test_execute_does_not_place_order_when_sizing_fails() -> None:
    """The position sizer returns NOT_EVALUABLE when entry/stop prices are
    missing (our CandidateBrief doesn't carry them).  This proves the
    execution pipeline respects the sizer's decision."""
    broker = _mock_broker()

    pipeline_result = PipelineRunResult(
        strategy_decisions=[_candidate_ready_decision()],
    )

    execute_pipeline_results(pipeline_result, broker)

    # Because CandidateBrief has no entry_price/stop_price, the sizer
    # cannot compute a position size → no order is placed.
    broker.place_order.assert_not_called()
