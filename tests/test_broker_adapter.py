from __future__ import annotations

import pytest

from prescient.broker import (
    ConfigurationError,
    KillSwitchBrokerWrapper,
    PreflightCheckBrokerWrapper,
    UnsupportedCapabilityError,
    get_broker_adapter,
)
from prescient.broker.mock import MockBrokerAdapter
from prescient.risk.models import (
    ExecutionMode,
    RiskOrderProposal,
    TradeExpression,
)


def test_factory_resolves_mock_adapter() -> None:
    adapter = get_broker_adapter("mock", "paper")
    assert isinstance(adapter, KillSwitchBrokerWrapper)
    assert isinstance(adapter._inner, PreflightCheckBrokerWrapper)
    assert isinstance(adapter._inner._inner, MockBrokerAdapter)
    assert adapter.get_capabilities().broker_name == "mock"


def test_factory_raises_value_error_for_invalid_broker() -> None:
    with pytest.raises(ValueError) as exc:
        get_broker_adapter("nonexistent_broker", "live")
    assert "Unrecognized broker_name" in str(exc.value)


def test_factory_coerces_execution_mode_string() -> None:
    adapter = get_broker_adapter("mock", "live")
    assert isinstance(adapter, KillSwitchBrokerWrapper)
    inner = adapter._inner._inner
    assert inner.execution_mode == ExecutionMode.LIVE


def test_factory_fails_on_invalid_execution_mode_string() -> None:
    with pytest.raises(ValueError):
        get_broker_adapter("mock", "invalid_mode")


def test_factory_raises_config_error_when_broker_does_not_support_paper() -> None:
    # Instantiate custom mock that lacks paper support
    class LiveOnlyMock(MockBrokerAdapter):
        def get_capabilities(self):
            return super().get_capabilities().model_copy(
                update={"supports_paper_trading": False}
            )

    # Temporary registration
    from prescient.broker import register_broker
    register_broker("live_only_mock", LiveOnlyMock)

    try:
        with pytest.raises(ConfigurationError) as exc:
            get_broker_adapter("live_only_mock", ExecutionMode.PAPER)
        assert "does not support paper trading" in str(exc.value)

        # But it should resolve under live/propose_only mode
        adapter = get_broker_adapter("live_only_mock", ExecutionMode.LIVE)
        assert adapter is not None
    finally:
        # Restore registry
        from prescient.broker import _REGISTRY
        _REGISTRY.pop("live_only_mock", None)


def test_place_order_raises_unsupported_capability_error_on_options_unsupported() -> None:
    adapter = MockBrokerAdapter(supports_options=False)
    proposal = RiskOrderProposal(
        target="AAPL",
        expression="CALL_OPTION",
        estimated_entry_cost=150.0,
        maximum_loss=150.0,
    )

    with pytest.raises(UnsupportedCapabilityError) as exc:
        adapter.place_order(proposal)
    assert "does not support options trading" in str(exc.value)


def test_mock_adapter_account_state_and_orders() -> None:
    adapter = MockBrokerAdapter(
        account_equity=30000.0,
        account_cash=20000.0,
        account_buying_power=20000.0,
    )

    # 1. Snapshot Check
    snapshot = adapter.get_account_snapshot()
    assert snapshot.equity == 30000.0
    assert snapshot.cash == 20000.0
    assert snapshot.buying_power == 20000.0

    # 2. Open Positions (empty initially)
    assert len(adapter.get_positions()) == 0

    # 3. Place Valid Order
    proposal = RiskOrderProposal(
        target="MSFT",
        expression="STOCK",
        estimated_entry_cost=500.0,
        maximum_loss=100.0,
    )

    result = adapter.place_order(proposal)
    assert result.order_id is not None
    assert result.filled_qty == 1
    assert result.avg_fill_price == 500.0

    # 4. Cash deduction and position creation
    new_snapshot = adapter.get_account_snapshot()
    assert new_snapshot.cash == 19500.0
    assert new_snapshot.buying_power == 19500.0

    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "MSFT"
    assert positions[0].expression == TradeExpression.STOCK
    assert positions[0].average_entry_price == 500.0

    # 5. Verify Orders List
    orders = adapter.get_orders()
    assert len(orders) == 1
    assert orders[0].symbol == "MSFT"
    assert orders[0].filled_qty == 1
