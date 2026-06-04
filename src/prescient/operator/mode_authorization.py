from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from prescient.operator.mode_state_store import (
    DEFAULT_MODE_AUTHORIZATION_PATH,
    ModeStateStore,
    build_mode_state_store,
)
from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
    OperatorStatus,
)
from prescient.risk.models import ExecutionMode
from prescient.safety import get_kill_switch_state

LIVE_CONFIRMATION_TEXT = "AUTHORIZE LIVE TRADING"

__all__ = [
    "DEFAULT_MODE_AUTHORIZATION_PATH",
    "LIVE_CONFIRMATION_TEXT",
    "authorize_execution_mode",
    "read_operator_status",
]


def read_operator_status(
    *,
    mode_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    store: ModeStateStore | None = None,
) -> OperatorStatus:
    active_env = env if env is not None else os.environ
    active_store = store or build_mode_state_store(env=active_env, mode_path=mode_path)
    warnings: list[str] = []
    mode, source, latest = _interpret_mode_state(
        store=active_store, env=active_env, warnings=warnings
    )

    return OperatorStatus(
        execution_mode=mode,
        mode_source=source,
        kill_switch=get_kill_switch_state(path=kill_switch_path, env=active_env),
        latest_mode_authorization=latest,
        warnings=warnings,
    )


def authorize_execution_mode(
    request: ModeAuthorizationRequest,
    *,
    mode_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    allow_live: bool = False,
    now: datetime | None = None,
    store: ModeStateStore | None = None,
) -> ModeAuthorizationResult:
    active_env = env if env is not None else os.environ
    active_store = store or build_mode_state_store(env=active_env, mode_path=mode_path)
    warnings: list[str] = []
    previous_mode, _, _ = _interpret_mode_state(
        store=active_store, env=active_env, warnings=warnings
    )
    timestamp = now or datetime.now(timezone.utc)
    rejection_reasons = _mode_rejection_reasons(request, allow_live=allow_live)
    status = (
        ModeAuthorizationStatus.REJECTED
        if rejection_reasons
        else ModeAuthorizationStatus.ACCEPTED
    )
    active_mode = previous_mode if rejection_reasons else request.requested_mode

    result = ModeAuthorizationResult(
        status=status,
        requested_mode=request.requested_mode,
        previous_mode=previous_mode,
        active_mode=active_mode,
        actor=request.actor,
        reason=request.reason,
        created_at=timestamp,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )

    if status == ModeAuthorizationStatus.ACCEPTED:
        active_store.append_accepted(result)

    return result


def _mode_rejection_reasons(
    request: ModeAuthorizationRequest,
    *,
    allow_live: bool,
) -> list[str]:
    if request.requested_mode != ExecutionMode.LIVE:
        return []

    reasons: list[str] = []
    if not allow_live:
        reasons.append("live_mode_disabled")
    if request.confirmation_text != LIVE_CONFIRMATION_TEXT:
        reasons.append("live_confirmation_missing")
    return reasons


def _interpret_mode_state(
    *,
    store: ModeStateStore,
    env: Mapping[str, str],
    warnings: list[str],
) -> tuple[ExecutionMode, str, ModeAuthorizationResult | None]:
    env_mode = (env.get("PRESCIENT_EXECUTION_MODE") or "").strip()
    if env_mode:
        try:
            mode = ExecutionMode(env_mode)
        except ValueError:
            warnings.append(
                "PRESCIENT_EXECUTION_MODE was invalid; defaulting to propose_only"
            )
            return ExecutionMode.PROPOSE_ONLY, "default", None

        if mode == ExecutionMode.LIVE:
            warnings.append(
                "PRESCIENT_EXECUTION_MODE=live is disabled; defaulting to propose_only"
            )
            return ExecutionMode.PROPOSE_ONLY, "default", None
        return mode, "environment", None

    latest = store.read_latest_accepted(warnings=warnings)
    if latest is None:
        return ExecutionMode.PROPOSE_ONLY, "default", None
    if latest.status != ModeAuthorizationStatus.ACCEPTED:
        return ExecutionMode.PROPOSE_ONLY, "default", latest
    if latest.active_mode == ExecutionMode.LIVE:
        warnings.append("live mode authorization is disabled; defaulting to propose_only")
        return ExecutionMode.PROPOSE_ONLY, "default", latest

    return latest.active_mode, "store", latest
