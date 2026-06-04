from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from prescient.operator.mode_authorization import (
    LIVE_CONFIRMATION_TEXT,
    authorize_execution_mode,
    read_operator_status,
)
from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
)
from prescient.risk.models import ExecutionMode
from prescient.safety import KillSwitchStatus


def test_mode_authorization_request_cleans_actor_and_reason() -> None:
    request = ModeAuthorizationRequest(
        requested_mode=ExecutionMode.PAPER,
        actor=" operator@example.com ",
        reason=" validate broker sandbox ",
    )

    assert request.actor == "operator@example.com"
    assert request.reason == "validate broker sandbox"


def test_mode_authorization_request_rejects_empty_reason() -> None:
    with pytest.raises(ValueError, match="reason is required"):
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.PAPER,
            actor="operator@example.com",
            reason=" ",
        )


def test_mode_authorization_result_serializes_execution_mode_values() -> None:
    result = ModeAuthorizationResult(
        status=ModeAuthorizationStatus.ACCEPTED,
        requested_mode=ExecutionMode.PAPER,
        previous_mode=ExecutionMode.PROPOSE_ONLY,
        active_mode=ExecutionMode.PAPER,
        actor="operator@example.com",
        reason="paper validation",
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )

    dumped = result.model_dump(mode="json")

    assert dumped["requested_mode"] == "paper"
    assert dumped["previous_mode"] == "propose_only"
    assert dumped["active_mode"] == "paper"


def test_operator_status_defaults_to_propose_only_and_inactive_kill_switch(
    tmp_path: Path,
) -> None:
    status = read_operator_status(
        mode_path=tmp_path / "execution-mode.json",
        kill_switch_path=tmp_path / "kill-switch.json",
        env={},
    )

    assert status.execution_mode == ExecutionMode.PROPOSE_ONLY
    assert status.mode_source == "default"
    assert status.kill_switch.status == KillSwitchStatus.INACTIVE


def test_authorizing_paper_writes_mode_state(tmp_path: Path) -> None:
    mode_path = tmp_path / "execution-mode.json"

    result = authorize_execution_mode(
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.PAPER,
            actor="operator@example.com",
            reason="paper validation",
        ),
        mode_path=mode_path,
        env={},
    )

    assert result.status == ModeAuthorizationStatus.ACCEPTED
    assert result.previous_mode == ExecutionMode.PROPOSE_ONLY
    assert result.active_mode == ExecutionMode.PAPER

    status = read_operator_status(mode_path=mode_path, env={})
    assert status.execution_mode == ExecutionMode.PAPER
    assert status.mode_source == "store"


def test_invalid_mode_file_fails_closed_to_propose_only(tmp_path: Path) -> None:
    mode_path = tmp_path / "execution-mode.json"
    mode_path.write_text("{not-json", encoding="utf-8")

    status = read_operator_status(mode_path=mode_path, env={})

    assert status.execution_mode == ExecutionMode.PROPOSE_ONLY
    assert status.mode_source == "default"
    assert any("unreadable" in warning for warning in status.warnings)


def test_live_mode_is_rejected_by_default_even_with_confirmation(
    tmp_path: Path,
) -> None:
    result = authorize_execution_mode(
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.LIVE,
            actor="operator@example.com",
            reason="testing live guard",
            confirmation_text=LIVE_CONFIRMATION_TEXT,
        ),
        mode_path=tmp_path / "execution-mode.json",
        env={},
    )

    assert result.status == ModeAuthorizationStatus.REJECTED
    assert result.active_mode == ExecutionMode.PROPOSE_ONLY
    assert "live_mode_disabled" in result.rejection_reasons
