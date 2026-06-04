from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from prescient.broker import (
    BrokerExecutionError,
    BrokerOrderStatus,
    get_broker_adapter,
)
from prescient.broker.execution_guard import (
    KillSwitchBrokerWrapper,
    PreflightCheckBrokerWrapper,
    ProposeOnlyBrokerWrapper,
)
from prescient.broker.mock import MockBrokerAdapter
from prescient.risk.models import (
    AccountRiskSnapshot,
    RiskOrderProposal,
)


def _proposal(cost: float = 10_000.0) -> RiskOrderProposal:
    return RiskOrderProposal(
        target="AAPL",
        expression="STOCK",
        estimated_entry_cost=cost,
        maximum_loss=cost * 0.03,
    )


# ---------------------------------------------------------------------------
# PreflightCheckBrokerWrapper tests (live/paper modes)
# ---------------------------------------------------------------------------


class TestPreflightCheckBrokerWrapper:
    def test_order_passes_when_buying_power_sufficient(self) -> None:
        inner = MagicMock()
        inner.get_account_snapshot.return_value = AccountRiskSnapshot(
            equity=20_000.0, cash=20_000.0, buying_power=20_000.0
        )
        inner.place_order.return_value = MagicMock(order_id="real-123")

        wrapper = PreflightCheckBrokerWrapper(inner, slippage_buffer_pct=0.01)
        result = wrapper.place_order(_proposal(9_000.0))  # required = 9090

        inner.place_order.assert_called_once()
        assert result.order_id == "real-123"

    def test_order_blocked_when_buying_power_insufficient(self) -> None:
        inner = MagicMock()
        inner.get_account_snapshot.return_value = AccountRiskSnapshot(
            equity=10_000.0, cash=10_000.0, buying_power=10_000.0
        )

        wrapper = PreflightCheckBrokerWrapper(inner, slippage_buffer_pct=0.01)

        with pytest.raises(BrokerExecutionError) as exc:
            wrapper.place_order(_proposal(10_000.0))  # required = 10100 > 10000

        assert "Insufficient buying power" in str(exc.value)
        assert "10100.00" in str(exc.value)
        assert "10000.00" in str(exc.value)
        inner.place_order.assert_not_called()

    def test_slippage_buffer_is_configurable(self) -> None:
        inner = MagicMock()
        # With 5% buffer: 9500 * 1.05 = 9975 <= 10000 => passes
        inner.get_account_snapshot.return_value = AccountRiskSnapshot(
            equity=10_000.0, cash=10_000.0, buying_power=10_000.0
        )
        inner.place_order.return_value = MagicMock(order_id="ok")

        wrapper = PreflightCheckBrokerWrapper(inner, slippage_buffer_pct=0.05)
        wrapper.place_order(_proposal(9_500.0))
        inner.place_order.assert_called_once()

        # With 5% buffer: 9600 * 1.05 = 10080 > 10000 => blocked
        inner.reset_mock()
        with pytest.raises(BrokerExecutionError):
            wrapper.place_order(_proposal(9_600.0))

    def test_delegations_pass_through(self) -> None:
        inner = MagicMock()
        inner.get_positions.return_value = ["pos1"]
        inner.get_orders.return_value = ["ord1"]
        inner.get_capabilities.return_value = "caps"

        wrapper = PreflightCheckBrokerWrapper(inner)
        assert wrapper.get_positions() == ["pos1"]
        assert wrapper.get_orders("all") == ["ord1"]
        assert wrapper.get_capabilities() == "caps"



# ---------------------------------------------------------------------------
# ProposeOnlyBrokerWrapper preflight tests
# ---------------------------------------------------------------------------


class TestProposeOnlyBrokerWrapperPreflight:
    def test_virtual_rejection_when_buying_power_insufficient(self) -> None:
        inner = MagicMock()
        inner.get_account_snapshot.return_value = AccountRiskSnapshot(
            equity=10_000.0, cash=10_000.0, buying_power=10_000.0
        )

        wrapper = ProposeOnlyBrokerWrapper(inner, slippage_buffer_pct=0.01)
        result = wrapper.place_order(_proposal(10_000.0))  # 10100 > 10000

        assert result.status == BrokerOrderStatus.REJECTED
        assert "Insufficient buying power" in result.message
        inner.place_order.assert_not_called()

    def test_virtual_success_when_buying_power_sufficient(self) -> None:
        inner = MagicMock()
        inner.get_account_snapshot.return_value = AccountRiskSnapshot(
            equity=20_000.0, cash=20_000.0, buying_power=20_000.0
        )

        wrapper = ProposeOnlyBrokerWrapper(inner, slippage_buffer_pct=0.01)
        result = wrapper.place_order(_proposal(9_000.0))  # 9090 <= 20000

        assert result.status == BrokerOrderStatus.OPEN
        assert result.order_id.startswith("propose-only-")
        assert "Order intercepted" in result.message
        inner.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# MockBrokerAdapter direct preflight tests
# ---------------------------------------------------------------------------


class TestMockBrokerAdapterPreflight:
    def test_order_blocked_when_buying_power_insufficient(self) -> None:
        adapter = MockBrokerAdapter(
            account_buying_power=10_000.0,
            slippage_buffer_pct=0.01,
        )
        with pytest.raises(BrokerExecutionError) as exc:
            adapter.place_order(_proposal(10_000.0))  # 10100 > 10000
        assert "Insufficient buying power" in str(exc.value)

    def test_order_succeeds_when_buying_power_sufficient(self) -> None:
        adapter = MockBrokerAdapter(
            account_buying_power=20_000.0,
            slippage_buffer_pct=0.01,
        )
        result = adapter.place_order(_proposal(9_000.0))  # 9090 <= 20000
        assert result.status == BrokerOrderStatus.FILLED

    def test_custom_slippage_buffer(self) -> None:
        adapter = MockBrokerAdapter(
            account_buying_power=10_000.0,
            slippage_buffer_pct=0.05,  # 5% buffer
        )
        # 9500 * 1.05 = 9975 <= 10000 => passes
        result = adapter.place_order(_proposal(9_500.0))
        assert result.status == BrokerOrderStatus.FILLED

        # Reset buying power (was deducted)
        adapter.account_buying_power = 10_000.0
        # 9600 * 1.05 = 10080 > 10000 => blocked
        with pytest.raises(BrokerExecutionError):
            adapter.place_order(_proposal(9_600.0))


# ---------------------------------------------------------------------------
# Factory integration tests
# ---------------------------------------------------------------------------


class TestFactoryIntegration:
    def test_paper_mode_wraps_with_preflight(self) -> None:
        adapter = get_broker_adapter("mock", "paper")
        assert isinstance(adapter, KillSwitchBrokerWrapper)
        assert isinstance(adapter._inner, PreflightCheckBrokerWrapper)

    def test_live_mode_wraps_with_preflight(self) -> None:
        adapter = get_broker_adapter("mock", "live")
        assert isinstance(adapter, KillSwitchBrokerWrapper)
        assert isinstance(adapter._inner, PreflightCheckBrokerWrapper)

    def test_propose_only_mode_wraps_with_propose_only(self) -> None:
        adapter = get_broker_adapter("mock", "propose_only")
        assert isinstance(adapter, KillSwitchBrokerWrapper)
        assert isinstance(adapter._inner, ProposeOnlyBrokerWrapper)

    def test_factory_passes_slippage_buffer(self) -> None:
        adapter = get_broker_adapter("mock", "paper", slippage_buffer_pct=0.05)
        assert isinstance(adapter, KillSwitchBrokerWrapper)
        assert isinstance(adapter._inner, PreflightCheckBrokerWrapper)
        assert adapter._inner.slippage_buffer_pct == 0.05

    def test_factory_preflight_blocks_insufficient_funds(self) -> None:
        adapter = get_broker_adapter(
            "mock", "paper",
            account_buying_power=10_000.0,
            slippage_buffer_pct=0.01,
        )
        with pytest.raises(BrokerExecutionError) as exc:
            adapter.place_order(_proposal(10_000.0))
        assert "Insufficient buying power" in str(exc.value)

    def test_factory_preflight_allows_sufficient_funds(self) -> None:
        adapter = get_broker_adapter(
            "mock", "paper",
            account_buying_power=20_000.0,
            slippage_buffer_pct=0.01,
        )
        result = adapter.place_order(_proposal(9_000.0))
        assert result.status == BrokerOrderStatus.FILLED
