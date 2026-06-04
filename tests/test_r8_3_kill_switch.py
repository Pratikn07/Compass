from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from prescient.broker.models import BrokerOrder, BrokerOrderStatus, OrderStatusFilter
from prescient.safety import (
    FileKillSwitchProvider,
    KillSwitchActivationSource,
    KillSwitchEventType,
    KillSwitchStatus,
    activate_kill_switch,
    get_kill_switch_state,
    reset_kill_switch,
)


def _now() -> datetime:
    return datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc)


def _order(order_id: str, status: BrokerOrderStatus = BrokerOrderStatus.OPEN) -> BrokerOrder:
    return BrokerOrder(
        order_id=order_id,
        symbol="NTNX",
        qty=1,
        filled_qty=0,
        limit_price=5.0,
        status=status,
        submitted_at=_now(),
    )


def test_file_provider_activates_persists_and_resets_state(tmp_path: Path) -> None:
    state_path = tmp_path / "kill-switch.json"
    provider = FileKillSwitchProvider(path=state_path, env={})

    inactive = provider.read_state()
    assert inactive.status == KillSwitchStatus.INACTIVE

    activation = provider.activate(
        reason="unexpected live activity",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        now=_now(),
    )

    assert activation.state.status == KillSwitchStatus.ACTIVE
    assert activation.events[0].event_type == KillSwitchEventType.ACTIVATED
    assert state_path.exists()

    restarted_provider = FileKillSwitchProvider(path=state_path, env={})
    assert restarted_provider.read_state().status == KillSwitchStatus.ACTIVE

    reset = restarted_provider.reset(
        reason="manual review complete",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        now=_now(),
    )

    assert reset.status == KillSwitchStatus.INACTIVE
    assert FileKillSwitchProvider(path=state_path, env={}).read_state().status == (
        KillSwitchStatus.INACTIVE
    )


def test_environment_active_overrides_inactive_file(tmp_path: Path) -> None:
    state_path = tmp_path / "kill-switch.json"
    provider = FileKillSwitchProvider(path=state_path, env={})
    provider.reset(
        reason="review complete",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        now=_now(),
    )

    active_from_env = FileKillSwitchProvider(
        path=state_path,
        env={"PRESCIENT_KILL_SWITCH": "active"},
    ).read_state()

    assert active_from_env.status == KillSwitchStatus.ACTIVE
    assert active_from_env.activation_source == KillSwitchActivationSource.ENVIRONMENT


def test_corrupted_state_file_reads_as_active_fail_closed(tmp_path: Path) -> None:
    state_path = tmp_path / "kill-switch.json"
    state_path.write_text("{not-json", encoding="utf-8")

    state = FileKillSwitchProvider(path=state_path, env={}).read_state()

    assert state.status == KillSwitchStatus.ACTIVE
    assert any("unreadable" in warning for warning in state.warnings)
    serialized = state.model_dump_json()
    assert "{not-json" not in serialized


def test_activation_with_cancel_open_orders_journals_each_result(tmp_path: Path) -> None:
    state_path = tmp_path / "kill-switch.json"
    provider = FileKillSwitchProvider(path=state_path, env={})
    broker = MagicMock()
    broker.get_orders.return_value = [_order("open-1"), _order("open-2")]
    broker.cancel_order.side_effect = [None, RuntimeError("broker timeout")]

    result = provider.activate(
        reason="stop now",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        cancel_open_orders=True,
        broker=broker,
        now=_now(),
    )

    broker.get_orders.assert_called_once_with(status=OrderStatusFilter.OPEN)
    assert broker.cancel_order.call_count == 2
    assert result.state.status == KillSwitchStatus.ACTIVE
    assert result.cancel_attempted_count == 2
    assert result.cancel_succeeded_count == 1
    assert result.cancel_failed_count == 1
    assert [event.event_type for event in result.events] == [
        KillSwitchEventType.ACTIVATED,
        KillSwitchEventType.CANCEL_ATTEMPTED,
        KillSwitchEventType.CANCEL_SUCCEEDED,
        KillSwitchEventType.CANCEL_ATTEMPTED,
        KillSwitchEventType.CANCEL_FAILED,
    ]
    assert "broker timeout" not in json.dumps([event.model_dump(mode="json") for event in result.events])


def test_top_level_helpers_accept_custom_path(tmp_path: Path) -> None:
    state_path = tmp_path / "kill-switch.json"

    activated = activate_kill_switch(
        reason="operator stop",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        path=state_path,
        now=_now(),
    )
    assert activated.state.status == KillSwitchStatus.ACTIVE
    assert get_kill_switch_state(path=state_path, env={}).status == KillSwitchStatus.ACTIVE

    reset = reset_kill_switch(
        reason="review complete",
        actor="operator",
        source=KillSwitchActivationSource.TEST,
        path=state_path,
        now=_now(),
    )
    assert reset.status == KillSwitchStatus.INACTIVE

