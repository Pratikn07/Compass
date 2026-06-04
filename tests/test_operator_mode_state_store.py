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


# --- SupabaseModeStateStore (fake client) ---------------------------------

from typing import Any  # noqa: E402

from prescient.operator.mode_state_store import SupabaseModeStateStore  # noqa: E402


class _FakeQuery:
    def __init__(self, client: "_FakeSupabaseClient") -> None:
        self._client = client

    def insert(self, row: dict[str, Any]) -> "_FakeQuery":
        if self._client.write_error:
            raise self._client.write_error
        self._client.inserted.append(row)
        return self

    def select(self, columns: str) -> "_FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeQuery":
        return self

    def limit(self, n: int) -> "_FakeQuery":
        return self

    def execute(self) -> Any:
        if self._client.read_error:
            raise self._client.read_error
        return type("Resp", (), {"data": self._client.rows})()


class _FakeSchema:
    def __init__(self, client: "_FakeSupabaseClient") -> None:
        self._client = client

    def table(self, name: str) -> _FakeQuery:
        self._client.table_name = name
        return _FakeQuery(self._client)


class _FakeSupabaseClient:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.read_error = read_error
        self.write_error = write_error
        self.inserted: list[dict[str, Any]] = []
        self.table_name: str | None = None

    def schema(self, name: str) -> _FakeSchema:
        return _FakeSchema(self)


def _row(active: str = "paper") -> dict[str, Any]:
    return {
        "status": "accepted",
        "requested_mode": active,
        "previous_mode": "propose_only",
        "active_mode": active,
        "actor": "operator@example.com",
        "reason": "paper validation",
        "rejection_reasons": [],
        "warnings": [],
        "created_at": "2026-06-04T12:00:00+00:00",
    }


def test_supabase_store_reads_latest_row() -> None:
    client = _FakeSupabaseClient(rows=[_row("paper")])
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    loaded = store.read_latest_accepted()
    assert loaded is not None
    assert loaded.active_mode == ExecutionMode.PAPER
    assert client.table_name == "operator_mode_authorizations"


def test_supabase_store_empty_returns_none() -> None:
    client = _FakeSupabaseClient(rows=[])
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    assert store.read_latest_accepted() is None


def test_supabase_store_read_failure_returns_none() -> None:
    client = _FakeSupabaseClient(read_error=TimeoutError("db unreachable"))
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    assert store.read_latest_accepted() is None


def test_supabase_store_malformed_row_returns_none() -> None:
    client = _FakeSupabaseClient(rows=[{"status": "accepted"}])  # missing fields
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    assert store.read_latest_accepted() is None


def test_supabase_store_append_inserts_row() -> None:
    client = _FakeSupabaseClient()
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    store.append_accepted(_accepted(ExecutionMode.PAPER))
    assert len(client.inserted) == 1
    assert client.inserted[0]["active_mode"] == "paper"
    assert client.inserted[0]["status"] == "accepted"


def test_supabase_store_write_failure_raises() -> None:
    client = _FakeSupabaseClient(write_error=RuntimeError("insert denied"))
    store = SupabaseModeStateStore(client=client, schema="prescient_storage")
    with pytest.raises(RuntimeError):
        store.append_accepted(_accepted(ExecutionMode.PAPER))


# --- build_mode_state_store factory ---------------------------------------

from prescient.operator.mode_state_store import build_mode_state_store  # noqa: E402


def test_factory_returns_file_store_without_supabase_env(tmp_path: Path) -> None:
    store = build_mode_state_store(env={}, mode_path=tmp_path / "m.json")
    assert isinstance(store, FileModeStateStore)


def test_factory_returns_supabase_store_when_env_present() -> None:
    captured: dict[str, str] = {}

    def fake_factory(url: str, key: str) -> object:
        captured["url"] = url
        return object()

    store = build_mode_state_store(
        env={
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        },
        mode_path=None,
        create_client_factory=fake_factory,
    )
    assert isinstance(store, SupabaseModeStateStore)
    assert captured["url"] == "https://x.supabase.co"


def test_factory_explicit_mode_path_forces_file_store_even_with_env(
    tmp_path: Path,
) -> None:
    store = build_mode_state_store(
        env={
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        },
        mode_path=tmp_path / "m.json",
    )
    assert isinstance(store, FileModeStateStore)
