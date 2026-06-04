from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from prescient.broker import get_broker_adapter
from prescient.broker.execution_guard import (
    KillSwitchBrokerWrapper,
    PreflightCheckBrokerWrapper,
    ProposeOnlyBrokerWrapper,
)
from prescient.broker.models import BrokerCapabilities, BrokerExecutionError, BrokerOrderStatus
from prescient.risk.models import AccountRiskSnapshot, RiskOrderProposal
from prescient.safety import (
    FileKillSwitchProvider,
    KillSwitchActivationSource,
    KillSwitchState,
    KillSwitchStatus,
)


def _proposal() -> RiskOrderProposal:
    return RiskOrderProposal(
        target="NTNX",
        expression="STOCK",
        estimated_entry_cost=100.0,
        maximum_loss=100.0,
    )


def _provider(status: KillSwitchStatus) -> MagicMock:
    provider = MagicMock()
    provider.read_state.return_value = KillSwitchState(status=status)
    return provider


def _inner_broker() -> MagicMock:
    inner = MagicMock()
    inner.get_account_snapshot.return_value = AccountRiskSnapshot(
        equity=10_000.0,
        cash=10_000.0,
        buying_power=10_000.0,
    )
    inner.get_positions.return_value = ["position"]
    inner.get_orders.return_value = ["order"]
    inner.get_capabilities.return_value = BrokerCapabilities(
        supports_options=True,
        supports_paper_trading=True,
        broker_name="mock",
    )
    return inner


def test_wrapper_blocks_place_order_when_active_and_allows_cancel() -> None:
    inner = _inner_broker()
    wrapper = KillSwitchBrokerWrapper(inner, provider=_provider(KillSwitchStatus.ACTIVE))

    with pytest.raises(BrokerExecutionError, match="Kill switch active"):
        wrapper.place_order(_proposal())

    inner.place_order.assert_not_called()
    wrapper.cancel_order("order-1")
    inner.cancel_order.assert_called_once_with("order-1")


def test_wrapper_delegates_reads_and_orders_when_inactive() -> None:
    inner = _inner_broker()
    inner.place_order.return_value.status = BrokerOrderStatus.FILLED
    wrapper = KillSwitchBrokerWrapper(inner, provider=_provider(KillSwitchStatus.INACTIVE))

    assert wrapper.get_account_snapshot().equity == 10_000.0
    assert wrapper.get_positions() == ["position"]
    assert wrapper.get_orders("open") == ["order"]
    assert wrapper.get_capabilities().broker_name == "mock"

    wrapper.place_order(_proposal())
    inner.place_order.assert_called_once()


def test_wrapper_blocks_when_provider_cannot_be_read() -> None:
    inner = _inner_broker()
    provider = MagicMock()
    provider.read_state.side_effect = RuntimeError("disk unreadable")
    wrapper = KillSwitchBrokerWrapper(inner, provider=provider)

    with pytest.raises(BrokerExecutionError, match="Kill switch state unavailable"):
        wrapper.place_order(_proposal())

    inner.place_order.assert_not_called()


def test_factory_wraps_all_execution_modes_with_kill_switch(tmp_path: Path) -> None:
    provider = FileKillSwitchProvider(path=tmp_path / "kill-switch.json", env={})

    propose_only = get_broker_adapter(
        "mock",
        "propose_only",
        kill_switch_provider=provider,
    )
    paper = get_broker_adapter("mock", "paper", kill_switch_provider=provider)
    live = get_broker_adapter("mock", "live", kill_switch_provider=provider)

    assert isinstance(propose_only, KillSwitchBrokerWrapper)
    assert isinstance(propose_only._inner, ProposeOnlyBrokerWrapper)
    assert isinstance(paper, KillSwitchBrokerWrapper)
    assert isinstance(paper._inner, PreflightCheckBrokerWrapper)
    assert isinstance(live, KillSwitchBrokerWrapper)
    assert isinstance(live._inner, PreflightCheckBrokerWrapper)


def test_active_kill_switch_overrides_paper_and_live_modes(tmp_path: Path) -> None:
    provider = FileKillSwitchProvider(path=tmp_path / "kill-switch.json", env={})
    provider.activate(
        reason="stop",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        now=datetime(2026, 6, 3, 14, 30),
    )

    for mode in ["paper", "live", "propose_only"]:
        adapter = get_broker_adapter("mock", mode, kill_switch_provider=provider)
        with pytest.raises(BrokerExecutionError, match="Kill switch active"):
            adapter.place_order(_proposal())

