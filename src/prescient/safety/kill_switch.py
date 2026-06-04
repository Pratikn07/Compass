from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prescient.safety.models import (
    KillSwitchActivationResult,
    KillSwitchActivationSource,
    KillSwitchEvent,
    KillSwitchEventType,
    KillSwitchState,
    KillSwitchStatus,
)


DEFAULT_KILL_SWITCH_PATH = Path(".prescient/kill-switch.json")
ACTIVE_ENV_VALUES = {"1", "true", "active", "yes", "on"}


class FileKillSwitchProvider:
    def __init__(
        self,
        path: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else DEFAULT_KILL_SWITCH_PATH
        self._env = env

    def read_state(self) -> KillSwitchState:
        env_state = self._read_env_state()
        file_state = self._read_file_state()

        if env_state is not None and env_state.status == KillSwitchStatus.ACTIVE:
            warnings = list(env_state.warnings)
            if file_state is not None and file_state.status == KillSwitchStatus.INACTIVE:
                warnings.append("environment kill switch overrides inactive file state")
            return env_state.model_copy(update={"warnings": warnings})

        if file_state is not None:
            return file_state

        return KillSwitchState(status=KillSwitchStatus.INACTIVE)

    def activate(
        self,
        *,
        reason: str,
        actor: str,
        source: KillSwitchActivationSource,
        cancel_open_orders: bool = False,
        broker: Any | None = None,
        now: datetime | None = None,
    ) -> KillSwitchActivationResult:
        timestamp = now or datetime.now(timezone.utc)
        cleaned_reason = _required_text(reason, "Kill switch activation reason is required.")
        cleaned_actor = _required_text(actor, "Kill switch activation actor is required.")
        state = KillSwitchState(
            status=KillSwitchStatus.ACTIVE,
            activated_at=timestamp,
            activated_by=cleaned_actor,
            activation_source=source,
            reason=cleaned_reason,
        )
        self._write_state(state)

        events = [
            KillSwitchEvent(
                event_type=KillSwitchEventType.ACTIVATED,
                created_at=timestamp,
                actor=cleaned_actor,
                source=source,
                reason=cleaned_reason,
                message="Kill switch activated.",
            )
        ]
        attempted = 0
        succeeded = 0
        failed = 0
        warnings: list[str] = []

        if cancel_open_orders:
            if broker is None:
                warnings.append("cancel_open_orders requires broker context")
            else:
                cancel_events = _cancel_open_orders(
                    broker=broker,
                    actor=cleaned_actor,
                    source=source,
                    reason=cleaned_reason,
                    timestamp=timestamp,
                )
                events.extend(cancel_events)
                attempted = sum(
                    event.event_type == KillSwitchEventType.CANCEL_ATTEMPTED
                    for event in cancel_events
                )
                succeeded = sum(
                    event.event_type == KillSwitchEventType.CANCEL_SUCCEEDED
                    for event in cancel_events
                )
                failed = sum(
                    event.event_type == KillSwitchEventType.CANCEL_FAILED
                    for event in cancel_events
                )

        return KillSwitchActivationResult(
            state=state,
            events=events,
            cancel_attempted_count=attempted,
            cancel_succeeded_count=succeeded,
            cancel_failed_count=failed,
            warnings=warnings,
        )

    def reset(
        self,
        *,
        reason: str,
        actor: str,
        source: KillSwitchActivationSource,
        now: datetime | None = None,
    ) -> KillSwitchState:
        timestamp = now or datetime.now(timezone.utc)
        state = KillSwitchState(
            status=KillSwitchStatus.INACTIVE,
            reset_at=timestamp,
            reset_by=_required_text(actor, "Kill switch reset actor is required."),
            reset_reason=_required_text(reason, "Kill switch reset reason is required."),
            activation_source=source,
        )
        self._write_state(state)
        return state

    def _read_env_state(self) -> KillSwitchState | None:
        env = self._env if self._env is not None else os.environ
        value = env.get("PRESCIENT_KILL_SWITCH")
        if value is None or value.strip().lower() not in ACTIVE_ENV_VALUES:
            return None
        return KillSwitchState(
            status=KillSwitchStatus.ACTIVE,
            activated_at=datetime.now(timezone.utc),
            activation_source=KillSwitchActivationSource.ENVIRONMENT,
            reason="PRESCIENT_KILL_SWITCH environment override is active.",
        )

    def _read_file_state(self) -> KillSwitchState | None:
        if not self.path.exists():
            return None

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return KillSwitchState.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return KillSwitchState(
                status=KillSwitchStatus.ACTIVE,
                activated_at=datetime.now(timezone.utc),
                activation_source=KillSwitchActivationSource.FILE_SENTINEL,
                reason="Kill switch state file was unreadable; failing closed.",
                warnings=[f"kill switch state unreadable at {self.path}"],
            )

    def _write_state(self, state: KillSwitchState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f".{self.path.name}.tmp")
        tmp_path.write_text(state.model_dump_json(), encoding="utf-8")
        os.replace(tmp_path, self.path)


def get_kill_switch_state(
    *,
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> KillSwitchState:
    return FileKillSwitchProvider(path=path, env=env).read_state()


def activate_kill_switch(
    *,
    reason: str,
    actor: str,
    source: KillSwitchActivationSource,
    cancel_open_orders: bool = False,
    broker: Any | None = None,
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> KillSwitchActivationResult:
    return FileKillSwitchProvider(path=path, env=env).activate(
        reason=reason,
        actor=actor,
        source=source,
        cancel_open_orders=cancel_open_orders,
        broker=broker,
        now=now,
    )


def reset_kill_switch(
    *,
    reason: str,
    actor: str,
    source: KillSwitchActivationSource,
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> KillSwitchState:
    return FileKillSwitchProvider(path=path, env=env).reset(
        reason=reason,
        actor=actor,
        source=source,
        now=now,
    )


def _cancel_open_orders(
    *,
    broker: Any,
    actor: str,
    source: KillSwitchActivationSource,
    reason: str,
    timestamp: datetime,
) -> list[KillSwitchEvent]:
    from prescient.broker.models import OrderStatusFilter

    events: list[KillSwitchEvent] = []
    try:
        open_orders = broker.get_orders(status=OrderStatusFilter.OPEN)
    except Exception:
        return [
            KillSwitchEvent(
                event_type=KillSwitchEventType.CANCEL_FAILED,
                created_at=timestamp,
                actor=actor,
                source=source,
                reason=reason,
                message="Unable to query open orders during kill switch activation.",
                warnings=["open_order_query_failed"],
            )
        ]

    for order in open_orders:
        order_id = getattr(order, "order_id", None)
        target = getattr(order, "symbol", None)
        events.append(
            KillSwitchEvent(
                event_type=KillSwitchEventType.CANCEL_ATTEMPTED,
                created_at=timestamp,
                actor=actor,
                source=source,
                reason=reason,
                order_id=order_id,
                target=target,
                message=f"Attempting to cancel open order {order_id}.",
            )
        )
        try:
            broker.cancel_order(order_id)
        except Exception:
            events.append(
                KillSwitchEvent(
                    event_type=KillSwitchEventType.CANCEL_FAILED,
                    created_at=timestamp,
                    actor=actor,
                    source=source,
                    reason=reason,
                    order_id=order_id,
                    target=target,
                    message=f"Failed to cancel open order {order_id}.",
                    warnings=["cancel_failed"],
                )
            )
            continue

        events.append(
            KillSwitchEvent(
                event_type=KillSwitchEventType.CANCEL_SUCCEEDED,
                created_at=timestamp,
                actor=actor,
                source=source,
                reason=reason,
                order_id=order_id,
                target=target,
                message=f"Cancelled open order {order_id}.",
            )
        )

    return events


def _required_text(value: str, message: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(message)
    return cleaned
