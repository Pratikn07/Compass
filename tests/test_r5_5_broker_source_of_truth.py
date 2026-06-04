from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock


from prescient.broker.mock import MockBrokerAdapter
from prescient.broker.models import BrokerOrder, BrokerPosition, BrokerOrderStatus, BrokerError
from prescient.risk import (
    AccountRiskSnapshot,
    ConcentrationSettings,
    DailyHaltSettings,
    RiskGateStatus,
    RiskRejectionReason,
    PositionSizingStatus,
    PositionSizingRejectionReason,
    size_position,
    TradeExpression,
    TradeProposal,
)
from prescient.runtime import run_hot_cold_strategy_pipeline
from prescient.signal.models import (
    StrategyUniverse,
    ThemeConfig,
    EarningsCalendarEvent,
    PeerResult,
    EarningsEvent,
    OptionContractSnapshot,
    TargetMarketData,
    SignalValue,
)


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC"],
                drivers=["AI data center demand"],
            )
        ]
    )


def _upcoming_target() -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker="NTNX",
        earnings_date=date(2026, 6, 2),
        report_time="AMC",
    )


def _peer_result(
    ticker: str,
    *,
    eps_estimate: float | None = 1.0,
    eps_actual: float | None = 1.2,
    revenue_estimate: float | None = 1_000.0,
    revenue_actual: float | None = 1_100.0,
    price_reaction_pct: float | None = 4.0,
    guidance_signal: SignalValue = "positive",
    theme_driver_signal: SignalValue = "positive",
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2026, 5, 20),
            report_time="AMC",
            eps_estimate=eps_estimate,
            eps_actual=eps_actual,
            revenue_estimate=revenue_estimate,
            revenue_actual=revenue_actual,
        ),
        price_reaction_pct=price_reaction_pct,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )


def _positive_peer_results() -> list[PeerResult]:
    return [
        _peer_result("NTAP"),
        _peer_result("PSTG"),
        _peer_result("WDC"),
    ]


def _target_data() -> TargetMarketData:
    return TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=4.0,
    )


def _call_option() -> OptionContractSnapshot:
    return OptionContractSnapshot(
        ticker="NTNX",
        option_type="CALL",
        expiration_date=date(2026, 6, 12),
        bid=4.85,
        ask=5.15,
        open_interest=250,
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_risk_package_never_imports_broker() -> None:
    """1. AST scan of src/prescient/risk/*.py confirming zero imports from prescient.broker"""
    forbidden_roots = {"prescient.broker"}
    for path in Path("src/prescient/risk").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        imports.extend(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports a forbidden dependency: {imports}"


def test_pipeline_queries_broker_and_injects_to_gate() -> None:
    """2. Mock broker -> pipeline calls state methods -> gate and sizer receive and process it"""
    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=100000.0,
    )
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.APPROVED
    assert len(result.sizing_decisions) == 1
    assert result.sizing_decisions[0].status == PositionSizingStatus.SIZED


def test_pipeline_fail_closed_on_broker_error() -> None:
    """3. Mock broker raises BrokerError -> all gates return NOT_EVALUABLE with BROKER_STATE_UNAVAILABLE"""
    broker = MagicMock()
    broker.get_account_snapshot.side_effect = BrokerError("Connection failed")
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.NOT_EVALUABLE
    assert result.risk_gate_decisions[0].rejection_reasons == [RiskRejectionReason.BROKER_STATE_UNAVAILABLE]
    assert len(result.sizing_decisions) == 0


def test_gate_blocks_concentration_limit() -> None:
    """4. 5 existing positions -> 6th trade -> BLOCKED with CONCENTRATION_LIMIT_EXCEEDED"""
    pos_symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
    positions = [
        BrokerPosition(symbol=sym, expression=TradeExpression.STOCK, qty=10.0, market_value=1000.0, average_entry_price=100.0)
        for sym in pos_symbols
    ]
    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=100000.0,
        positions=positions,
    )
    settings = ConcentrationSettings(max_open_positions=5, max_single_ticker_exposure_pct=0.20)
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
        concentration_settings=settings,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.BLOCKED
    assert RiskRejectionReason.CONCENTRATION_LIMIT_EXCEEDED in result.risk_gate_decisions[0].rejection_reasons


def test_gate_blocks_averaging_down() -> None:
    """5. Existing NTNX position -> new NTNX buy -> BLOCKED with AVERAGING_DOWN_BLOCKED"""
    positions = [
        BrokerPosition(symbol="NTNX", expression=TradeExpression.CALL_OPTION, qty=1.0, market_value=500.0, average_entry_price=500.0)
    ]
    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=100000.0,
        positions=positions,
    )
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.BLOCKED
    assert RiskRejectionReason.AVERAGING_DOWN_BLOCKED in result.risk_gate_decisions[0].rejection_reasons


def test_gate_allows_new_ticker_under_limit() -> None:
    """6. 3 existing positions -> 4th different ticker -> APPROVED"""
    pos_symbols = ["AAPL", "MSFT", "GOOG"]
    positions = [
        BrokerPosition(symbol=sym, expression=TradeExpression.STOCK, qty=10.0, market_value=1000.0, average_entry_price=100.0)
        for sym in pos_symbols
    ]
    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=100000.0,
        positions=positions,
    )
    settings = ConcentrationSettings(max_open_positions=5, max_single_ticker_exposure_pct=0.20)
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
        concentration_settings=settings,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.APPROVED


def test_sizer_blocks_concentration_over_exposure() -> None:
    """7. Single-ticker exposure would exceed 20% of equity -> BLOCKED"""
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=None,
    )
    decision = result.strategy_decisions[0]
    
    proposal = TradeProposal(
        target="NTNX",
        expression=TradeExpression.CALL_OPTION,
        entry_price=5.15,
        stop_price=None,
        contract_multiplier=100,
        minimum_quantity=1,
    )
    
    # entry cost required for option is $515.0 which is 0.515% of equity (exceeds 0.5%)
    sizing = size_position(
        decision,
        account_snapshot=AccountRiskSnapshot(equity=100000.0, cash=100000.0, buying_power=100000.0),
        proposal=proposal,
        broker_positions=[],
        concentration_settings=ConcentrationSettings(max_open_positions=5, max_single_ticker_exposure_pct=0.005),
    )
    
    assert sizing.status == PositionSizingStatus.BLOCKED
    assert PositionSizingRejectionReason.CONCENTRATION_LIMIT_EXCEEDED in sizing.rejection_reasons


def test_daily_halt_computed_from_broker_orders() -> None:
    """8. 2 losing fills today -> daily halt triggers -> all candidates blocked"""
    # 2 losing trades on today's date
    order1 = BrokerOrder(
        order_id="1",
        symbol="NTNX",
        qty=10,
        filled_qty=10,
        limit_price=100.0,
        status=BrokerOrderStatus.FILLED,
        submitted_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        side="buy",
    )
    order2 = BrokerOrder(
        order_id="2",
        symbol="NTNX",
        qty=10,
        filled_qty=10,
        limit_price=90.0,
        status=BrokerOrderStatus.FILLED,
        submitted_at=datetime(2026, 6, 1, 10, 5, 0, tzinfo=timezone.utc),
        side="sell",
    )
    order3 = BrokerOrder(
        order_id="3",
        symbol="AAPL",
        qty=10,
        filled_qty=10,
        limit_price=150.0,
        status=BrokerOrderStatus.FILLED,
        submitted_at=datetime(2026, 6, 1, 10, 10, 0, tzinfo=timezone.utc),
        side="buy",
    )
    order4 = BrokerOrder(
        order_id="4",
        symbol="AAPL",
        qty=10,
        filled_qty=10,
        limit_price=140.0,
        status=BrokerOrderStatus.FILLED,
        submitted_at=datetime(2026, 6, 1, 10, 15, 0, tzinfo=timezone.utc),
        side="sell",
    )

    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=100000.0,
        orders=[order1, order2, order3, order4],
    )
    halt_settings = DailyHaltSettings(max_losing_trades_per_day=2)
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
        daily_halt_settings=halt_settings,
    )
    assert len(result.risk_gate_decisions) == 1
    assert result.risk_gate_decisions[0].status == RiskGateStatus.BLOCKED
    assert "Daily halt is active" in result.risk_gate_decisions[0].explanation


def test_pipeline_without_broker_adapter_unchanged() -> None:
    """9. broker_adapter=None -> pipeline behavior identical to current (backward compat)"""
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=None,
    )
    assert len(result.risk_gate_decisions) == 0
    assert len(result.sizing_decisions) == 0
    assert result.daily_halt_decision is None


def test_zero_buying_power_blocks_sizing() -> None:
    """10. Broker returns $0 buying power -> sizer blocks with INSUFFICIENT_CASH_OR_BUYING_POWER"""
    broker = MockBrokerAdapter(
        account_equity=100000.0,
        account_cash=100000.0,
        account_buying_power=0.0,  # No buying power
    )
    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        broker_adapter=broker,
    )
    assert len(result.sizing_decisions) == 1
    assert result.sizing_decisions[0].status == PositionSizingStatus.BLOCKED
    assert PositionSizingRejectionReason.INSUFFICIENT_CASH_OR_BUYING_POWER in result.sizing_decisions[0].rejection_reasons
