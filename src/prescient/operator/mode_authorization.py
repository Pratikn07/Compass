from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
    OperatorStatus,
)
from prescient.risk.models import ExecutionMode
from prescient.safety import get_kill_switch_state


DEFAULT_MODE_AUTHORIZATION_PATH = Path(".prescient/execution-mode.json")
LIVE_CONFIRMATION_TEXT = "AUTHORIZE LIVE TRADING"


def read_operator_status(
    *,
    mode_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> OperatorStatus:
    active_env = env if env is not None else os.environ
    warnings: list[str] = []
    mode, source, latest = _read_mode_state(
        path=Path(mode_path) if mode_path is not None else DEFAULT_MODE_AUTHORIZATION_PATH,
        env=active_env,
        warnings=warnings,
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
) -> ModeAuthorizationResult:
    active_env = env if env is not None else os.environ
    path = Path(mode_path) if mode_path is not None else DEFAULT_MODE_AUTHORIZATION_PATH
    warnings: list[str] = []
    previous_mode, _, _ = _read_mode_state(path=path, env=active_env, warnings=warnings)
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
        _write_mode_state(path, result)

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


def _read_mode_state(
    *,
    path: Path,
    env: Mapping[str, str],
    warnings: list[str],
) -> tuple[ExecutionMode, str, ModeAuthorizationResult | None]:
    env_mode = (env.get("PRESCIENT_EXECUTION_MODE") or "").strip()
    if env_mode:
        try:
            mode = ExecutionMode(env_mode)
        except ValueError:
            warnings.append("PRESCIENT_EXECUTION_MODE was invalid; defaulting to propose_only")
            return ExecutionMode.PROPOSE_ONLY, "default", None

        if mode == ExecutionMode.LIVE:
            warnings.append("PRESCIENT_EXECUTION_MODE=live is disabled; defaulting to propose_only")
            return ExecutionMode.PROPOSE_ONLY, "default", None
        return mode, "environment", None

    if not path.exists():
        return ExecutionMode.PROPOSE_ONLY, "default", None

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        latest = ModeAuthorizationResult.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError):
        warnings.append(f"mode authorization state unreadable at {path}")
        return ExecutionMode.PROPOSE_ONLY, "default", None

    if latest.status != ModeAuthorizationStatus.ACCEPTED:
        return ExecutionMode.PROPOSE_ONLY, "default", latest
    if latest.active_mode == ExecutionMode.LIVE:
        warnings.append("live mode authorization is disabled; defaulting to propose_only")
        return ExecutionMode.PROPOSE_ONLY, "default", latest

    return latest.active_mode, "file", latest


def _write_mode_state(path: Path, result: ModeAuthorizationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(result.model_dump_json(), encoding="utf-8")
    os.replace(tmp_path, path)
