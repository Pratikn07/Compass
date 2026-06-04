from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from prescient.operator.mode_state_store import FileModeStateStore
from prescient.operator.models import (
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
)
from prescient.risk.models import ExecutionMode


def _accepted(active: ExecutionMode = ExecutionMode.PAPER) -> ModeAuthorizationResult:
    return ModeAuthorizationResult(
        status=ModeAuthorizationStatus.ACCEPTED,
        requested_mode=active,
        previous_mode=ExecutionMode.PROPOSE_ONLY,
        active_mode=active,
        actor="operator@example.com",
        reason="paper validation",
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )


def test_file_store_empty_returns_none(tmp_path: Path) -> None:
    store = FileModeStateStore(tmp_path / "execution-mode.json")
    assert store.read_latest_accepted() is None


def test_file_store_append_then_read_roundtrips(tmp_path: Path) -> None:
    store = FileModeStateStore(tmp_path / "execution-mode.json")
    result = _accepted()
    store.append_accepted(result)
    loaded = store.read_latest_accepted()
    assert loaded is not None
    assert loaded.active_mode == ExecutionMode.PAPER
    assert loaded.actor == "operator@example.com"


def test_file_store_newest_write_wins(tmp_path: Path) -> None:
    store = FileModeStateStore(tmp_path / "execution-mode.json")
    store.append_accepted(_accepted(ExecutionMode.PAPER))
    store.append_accepted(_accepted(ExecutionMode.PROPOSE_ONLY))
    loaded = store.read_latest_accepted()
    assert loaded is not None
    assert loaded.active_mode == ExecutionMode.PROPOSE_ONLY


def test_file_store_unreadable_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "execution-mode.json"
    path.write_text("{not json", encoding="utf-8")
    store = FileModeStateStore(path)
    assert store.read_latest_accepted() is None
