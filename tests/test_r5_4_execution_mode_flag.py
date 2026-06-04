from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from prescient.broker import (
    BrokerCapabilities,
    BrokerExecutionError,
    BrokerOrderStatus,
    OrderExecutionResult,
    get_broker_adapter,
)
from prescient.broker.execution_guard import (
    KillSwitchBrokerWrapper,
    PreflightCheckBrokerWrapper,
    ProposeOnlyBrokerWrapper,
    print_execution_mode_banner,
)
from prescient.broker.mock import MockBrokerAdapter
from prescient.risk import (
    AccountSnapshot,
    evaluate_account_size_policy,
)
from prescient.risk.account_policy import _coerce_execution_mode
from prescient.risk.models import ExecutionMode, RiskOrderProposal


def test_safe_default_coercion() -> None:
    # Coercing None must result in ExecutionMode.PROPOSE_ONLY
    assert _coerce_execution_mode(None) == ExecutionMode.PROPOSE_ONLY
    # Standard string/enum coercion should still work
    assert _coerce_execution_mode("paper") == ExecutionMode.PAPER
    assert _coerce_execution_mode("propose_only") == ExecutionMode.PROPOSE_ONLY
    assert _coerce_execution_mode(ExecutionMode.LIVE) == ExecutionMode.LIVE


def test_propose_only_broker_wrapper_delegation() -> None:
    # Create mock inner adapter
    inner = MagicMock()
    inner.get_account_snapshot.return_value = "snapshot"
    inner.get_positions.return_value = ["position1"]
    inner.get_orders.return_value = ["order1"]
    inner.get_capabilities.return_value = BrokerCapabilities(
        supports_options=True,
        supports_paper_trading=True,
        broker_name="mock_test",
    )

    wrapper = ProposeOnlyBrokerWrapper(inner)

    # Assert delegations are called and return values passed through
    assert wrapper.get_account_snapshot() == "snapshot"
    inner.get_account_snapshot.assert_called_once()

    assert wrapper.get_positions() == ["position1"]
    inner.get_positions.assert_called_once()

    assert wrapper.get_orders("open") == ["order1"]
    inner.get_orders.assert_called_once_with("open")

    wrapper.cancel_order("order_id_123")
    inner.cancel_order.assert_called_once_with("order_id_123")

    caps = wrapper.get_capabilities()
    assert caps.broker_name == "mock_test"
    inner.get_capabilities.assert_called_once()


def test_propose_only_broker_wrapper_intercepts_place_order() -> None:
    inner = MagicMock()
    from prescient.risk.models import AccountRiskSnapshot
    inner.get_account_snapshot.return_value = AccountRiskSnapshot(
        equity=100_000.0, cash=100_000.0, buying_power=100_000.0
    )
    wrapper = ProposeOnlyBrokerWrapper(inner)

    proposal = RiskOrderProposal(
        target="AAPL",
        expression="STOCK",
        estimated_entry_cost=150.0,
        maximum_loss=150.0,
    )

    result = wrapper.place_order(proposal)

    # Verify inner adapter place_order was never called
    inner.place_order.assert_not_called()

    # Verify virtual result properties
    assert isinstance(result, OrderExecutionResult)
    assert result.order_id.startswith("propose-only-")
    assert result.status == BrokerOrderStatus.OPEN
    assert result.filled_qty == 0
    assert result.avg_fill_price is None
    assert "Order intercepted: propose-only mode active" in result.message


def test_factory_integration() -> None:
    # 1. propose_only mode -> kill switch outside ProposeOnlyBrokerWrapper
    adapter_po = get_broker_adapter("mock", "propose_only")
    assert isinstance(adapter_po, KillSwitchBrokerWrapper)
    assert isinstance(adapter_po._inner, ProposeOnlyBrokerWrapper)

    # 2. paper mode -> kill switch outside PreflightCheckBrokerWrapper
    adapter_paper = get_broker_adapter("mock", "paper")
    assert isinstance(adapter_paper, KillSwitchBrokerWrapper)
    assert isinstance(adapter_paper._inner, PreflightCheckBrokerWrapper)
    assert not isinstance(adapter_paper._inner, ProposeOnlyBrokerWrapper)

    # 3. live mode -> kill switch outside PreflightCheckBrokerWrapper
    adapter_live = get_broker_adapter("mock", "live")
    assert isinstance(adapter_live, KillSwitchBrokerWrapper)
    assert isinstance(adapter_live._inner, PreflightCheckBrokerWrapper)
    assert not isinstance(adapter_live._inner, ProposeOnlyBrokerWrapper)


def test_mock_broker_adapter_defense_in_depth() -> None:
    # Direct instantiation with propose_only
    adapter = MockBrokerAdapter(execution_mode="propose_only")
    proposal = RiskOrderProposal(
        target="AAPL",
        expression="STOCK",
        estimated_entry_cost=150.0,
        maximum_loss=150.0,
    )

    with pytest.raises(BrokerExecutionError) as exc:
        adapter.place_order(proposal)
    assert "Cannot place orders in propose-only mode" in str(exc.value)

    # Direct instantiation with paper should succeed
    adapter_paper = MockBrokerAdapter(execution_mode="paper")
    result = adapter_paper.place_order(proposal)
    assert result.status == BrokerOrderStatus.FILLED


def test_print_execution_mode_banner(capsys: pytest.CaptureFixture[str]) -> None:
    # Clear any previous stdout output
    capsys.readouterr()

    # Print LIVE banner
    print_execution_mode_banner(ExecutionMode.LIVE)
    captured = capsys.readouterr().out
    assert "WARNING" in captured
    assert "LIVE" in captured

    # Print PAPER banner
    print_execution_mode_banner(ExecutionMode.PAPER)
    captured = capsys.readouterr().out
    assert "PAPER" in captured

    # Print PROPOSE_ONLY banner
    print_execution_mode_banner(ExecutionMode.PROPOSE_ONLY)
    captured = capsys.readouterr().out
    assert "PROPOSE-ONLY" in captured


def test_account_size_policy_default_mode() -> None:
    # Check that evaluating account policy defaults to ExecutionMode.PROPOSE_ONLY
    decision = evaluate_account_size_policy(
        AccountSnapshot(account_equity=10_000.0),
        requested_mode=None,
    )
    assert decision.requested_mode == ExecutionMode.PROPOSE_ONLY
