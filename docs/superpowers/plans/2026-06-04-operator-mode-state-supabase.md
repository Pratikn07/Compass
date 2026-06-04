# Operator Mode State → Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the FastAPI operator service's execution-mode state from a local JSON file into Supabase (append-only `operator_mode_authorizations` table) behind a `ModeStateStore` protocol, so the service survives restarts while preserving every safety rail.

**Architecture:** Introduce a `ModeStateStore` protocol with two implementations — `FileModeStateStore` (current behavior; tests + local dev) and `SupabaseModeStateStore` (prod). `mode_authorization.py`'s logic is unchanged; only persistence is abstracted. A factory selects the store from env (Supabase creds present → Supabase, else File). "Current mode = newest accepted row," interpreted by the existing fail-safe logic (→ `propose_only` on any doubt, refuse `live`).

**Tech Stack:** Python ≥3.11, pydantic, Supabase (PostgREST via `supabase` client, `service_role`), `uv` for running tests (`uv run pytest -q`). Supabase CLI for the migration.

**Reference spec:** `docs/superpowers/specs/2026-06-04-operator-mode-state-supabase-design.md`

---

## File Structure

```
src/prescient/operator/
  mode_state_store.py        # NEW: ModeStateStore Protocol + FileModeStateStore + SupabaseModeStateStore + factory
  mode_authorization.py      # MODIFY: delegate persistence to a ModeStateStore; keep all logic/rails
  api.py                     # MODIFY (small): pass env through so store factory can select backend

supabase/migrations/
  <ts>_operator_mode_authorizations.sql   # NEW: append-only table + service_role-only RLS

tests/
  test_operator_mode_state_store.py        # NEW: contract tests (both impls) + Supabase fake-client tests
  test_operator_mode_authorization.py      # MODIFY: keep passing; add store-injection coverage
```

**Key existing facts (verified):**
- `ModeAuthorizationResult` (in `operator/models.py`) fields: `status` (`ModeAuthorizationStatus` enum: `accepted`/`rejected`), `requested_mode`, `previous_mode`, `active_mode` (all `ExecutionMode`), `actor`, `reason`, `created_at` (datetime), `rejection_reasons: list[str]`, `warnings: list[str]`. `extra="forbid"`, frozen.
- `mode_authorization.py` currently isolates persistence to `_read_mode_state` (returns `(mode, source, latest)`) and `_write_mode_state(path, result)`.
- Supabase access uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, schema `prescient_storage`, via a client with `.schema(name).table(name)...` chaining (see `storage/supabase.py`).
- `ExecutionMode` enum lives in `prescient.risk.models` with values incl. `PROPOSE_ONLY = "propose_only"`, `LIVE = "live"`.

---

## Task 1: Create the Supabase migration for the append-only table

**Files:**
- Create: `supabase/migrations/<timestamp>_operator_mode_authorizations.sql`

- [ ] **Step 1: Generate the migration file**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase migration new operator_mode_authorizations
```

- [ ] **Step 2: Write the table + RLS into the generated file**

Exact content:

```sql
-- Append-only operator execution-mode authorization history (spec §2).
-- Current mode = newest accepted row. Reachable ONLY via the guarded FastAPI
-- routes (service_role); never browser->Supabase directly.

create table if not exists prescient_storage.operator_mode_authorizations (
    id                bigint generated always as identity primary key,
    status            text not null,
    requested_mode    text not null,
    previous_mode     text not null,
    active_mode       text not null,
    actor             text not null,
    reason            text not null,
    rejection_reasons jsonb not null default '[]'::jsonb,
    warnings          jsonb not null default '[]'::jsonb,
    created_at        timestamptz not null default now(),
    schema_version    integer not null default 1
);

create index if not exists operator_mode_authorizations_created_at_idx
    on prescient_storage.operator_mode_authorizations (created_at desc);

alter table prescient_storage.operator_mode_authorizations enable row level security;

grant all on prescient_storage.operator_mode_authorizations to service_role;
-- Intentionally NO policy for anon/authenticated: operator mode state is only
-- reachable through the guarded FastAPI routes.
```

- [ ] **Step 3: Apply locally and verify the table exists**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase start
supabase migration up
psql "$(supabase status -o env | grep DB_URL | cut -d= -f2- | tr -d '"')" \
  -c "\d prescient_storage.operator_mode_authorizations"
```

Expected: table description prints with the 11 columns above.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/
git commit -m "feat(storage): operator_mode_authorizations append-only table + service_role RLS"
```

---

## Task 2: Define the ModeStateStore protocol + FileModeStateStore (TDD)

This moves the existing file behavior behind the new interface, with NO behavior change.

**Files:**
- Create: `src/prescient/operator/mode_state_store.py`
- Test: `tests/test_operator_mode_state_store.py`

- [ ] **Step 1: Write the failing contract test for the file store**

Create `tests/test_operator_mode_state_store.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_operator_mode_state_store.py -v`
Expected: FAIL — `ModuleNotFoundError: prescient.operator.mode_state_store`.

- [ ] **Step 3: Implement the protocol + FileModeStateStore**

Create `src/prescient/operator/mode_state_store.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from prescient.operator.models import ModeAuthorizationResult


@runtime_checkable
class ModeStateStore(Protocol):
    """Persistence boundary for operator execution-mode authorizations.

    Implementations must fail safe: read_latest_accepted returns None on any
    unreadable state (callers default to propose_only). append_accepted must
    raise on persistence failure (never silently succeed).
    """

    def read_latest_accepted(self) -> ModeAuthorizationResult | None: ...

    def append_accepted(self, result: ModeAuthorizationResult) -> None: ...


class FileModeStateStore:
    """Stores the latest accepted authorization in a single JSON file.

    Matches the historical .prescient/execution-mode.json behavior: the file
    holds the most recent accepted authorization (append overwrites).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read_latest_accepted(self) -> ModeAuthorizationResult | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return ModeAuthorizationResult.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

    def append_accepted(self, result: ModeAuthorizationResult) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_name(f".{self._path.name}.tmp")
        tmp_path.write_text(result.model_dump_json(), encoding="utf-8")
        os.replace(tmp_path, self._path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_operator_mode_state_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/mode_state_store.py tests/test_operator_mode_state_store.py
git commit -m "feat(operator): ModeStateStore protocol + FileModeStateStore"
```

---

## Task 3: Add SupabaseModeStateStore (TDD with fake client)

**Files:**
- Modify: `src/prescient/operator/mode_state_store.py`
- Modify: `tests/test_operator_mode_state_store.py`

- [ ] **Step 1: Write failing tests for the Supabase store using a fake client**

Append to `tests/test_operator_mode_state_store.py`:

```python
from typing import Any

from prescient.operator.mode_state_store import SupabaseModeStateStore


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


class _FakeTable(_FakeQuery):
    pass


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_operator_mode_state_store.py -k supabase -v`
Expected: FAIL — `ImportError: cannot import name 'SupabaseModeStateStore'`.

- [ ] **Step 3: Implement SupabaseModeStateStore**

Append to `src/prescient/operator/mode_state_store.py`:

```python
from collections.abc import Mapping
from typing import Any


class SupabaseModeStateStore:
    """Append-only Supabase-backed store. Current = newest accepted row.

    Fails safe: read_latest_accepted returns None on any read/parse error so
    callers default to propose_only. append_accepted lets write errors raise.
    """

    _TABLE = "operator_mode_authorizations"

    def __init__(self, *, client: Any, schema: str = "prescient_storage") -> None:
        self._client = client
        self._schema = schema

    def read_latest_accepted(self) -> ModeAuthorizationResult | None:
        try:
            response = (
                self._client.schema(self._schema)
                .table(self._TABLE)
                .select("*")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            return None

        rows = getattr(response, "data", None) or []
        if not rows:
            return None
        try:
            return ModeAuthorizationResult.model_validate(_row_to_result(rows[0]))
        except Exception:
            return None

    def append_accepted(self, result: ModeAuthorizationResult) -> None:
        row = _result_to_row(result)
        self._client.schema(self._schema).table(self._TABLE).insert(row).execute()

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str],
        create_client_factory: Any = None,
    ) -> "SupabaseModeStateStore":
        url = env.get("SUPABASE_URL", "").strip()
        key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        schema = env.get("PRESCIENT_STORAGE_SCHEMA", "prescient_storage").strip()
        factory = create_client_factory
        if factory is None:
            from supabase import create_client

            factory = create_client
        return cls(client=factory(url, key), schema=schema)


def _result_to_row(result: ModeAuthorizationResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "requested_mode": result.requested_mode.value,
        "previous_mode": result.previous_mode.value,
        "active_mode": result.active_mode.value,
        "actor": result.actor,
        "reason": result.reason,
        "rejection_reasons": list(result.rejection_reasons),
        "warnings": list(result.warnings),
        "created_at": result.created_at.isoformat(),
    }


def _row_to_result(row: dict[str, Any]) -> dict[str, Any]:
    # Map a stored row back to ModeAuthorizationResult fields. Extra DB-only
    # columns (id, schema_version) are dropped because the model forbids extras.
    return {
        "status": row["status"],
        "requested_mode": row["requested_mode"],
        "previous_mode": row["previous_mode"],
        "active_mode": row["active_mode"],
        "actor": row["actor"],
        "reason": row["reason"],
        "rejection_reasons": row.get("rejection_reasons") or [],
        "warnings": row.get("warnings") or [],
        "created_at": row["created_at"],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_operator_mode_state_store.py -v`
Expected: PASS (all file + supabase tests).

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/mode_state_store.py tests/test_operator_mode_state_store.py
git commit -m "feat(operator): SupabaseModeStateStore (append-only, fail-safe reads)"
```

---

## Task 4: Add the env-selected store factory (TDD)

**Files:**
- Modify: `src/prescient/operator/mode_state_store.py`
- Modify: `tests/test_operator_mode_state_store.py`

- [ ] **Step 1: Write failing tests for the factory**

Append to `tests/test_operator_mode_state_store.py`:

```python
from prescient.operator.mode_state_store import (
    FileModeStateStore,
    SupabaseModeStateStore,
    build_mode_state_store,
)


def test_factory_returns_file_store_without_supabase_env(tmp_path: Path) -> None:
    store = build_mode_state_store(env={}, mode_path=tmp_path / "m.json")
    assert isinstance(store, FileModeStateStore)


def test_factory_returns_supabase_store_when_env_present() -> None:
    captured = {}

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


def test_factory_explicit_mode_path_forces_file_store_even_with_env(tmp_path: Path) -> None:
    store = build_mode_state_store(
        env={
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        },
        mode_path=tmp_path / "m.json",
    )
    assert isinstance(store, FileModeStateStore)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_operator_mode_state_store.py -k factory -v`
Expected: FAIL — `ImportError: cannot import name 'build_mode_state_store'`.

- [ ] **Step 3: Implement the factory**

Append to `src/prescient/operator/mode_state_store.py`:

```python
from pathlib import Path as _Path

DEFAULT_MODE_AUTHORIZATION_PATH = _Path(".prescient/execution-mode.json")


def build_mode_state_store(
    *,
    env: Mapping[str, str],
    mode_path: str | _Path | None = None,
    create_client_factory: Any = None,
) -> ModeStateStore:
    """Select the store. Explicit mode_path forces the file store (test/local
    seam). Otherwise, Supabase creds present -> Supabase; else file at the
    default path.
    """
    if mode_path is not None:
        return FileModeStateStore(_Path(mode_path))

    has_supabase = bool(
        env.get("SUPABASE_URL", "").strip()
        and env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if has_supabase:
        return SupabaseModeStateStore.from_env(
            env=env, create_client_factory=create_client_factory
        )
    return FileModeStateStore(DEFAULT_MODE_AUTHORIZATION_PATH)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_operator_mode_state_store.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/mode_state_store.py tests/test_operator_mode_state_store.py
git commit -m "feat(operator): env-selected mode state store factory"
```

---

## Task 5: Rewire mode_authorization.py to use the store (preserve all rails)

**Files:**
- Modify: `src/prescient/operator/mode_authorization.py`
- Test: `tests/test_operator_mode_authorization.py` (existing — must keep passing)

- [ ] **Step 1: Run the existing tests first to capture the green baseline**

Run: `uv run pytest tests/test_operator_mode_authorization.py -v`
Expected: PASS (record the count; this must not regress).

- [ ] **Step 2: Replace persistence internals with the store, keeping logic identical**

In `src/prescient/operator/mode_authorization.py`, replace the body so that
`read_operator_status` and `authorize_execution_mode` accept an optional
`store: ModeStateStore | None` and delegate persistence to it. Keep `_read_mode_state`'s
interpretation (env precedence, propose_only default, live refusal) but source the
"latest" from the store instead of reading the file directly.

Full new content for the two public functions and the interpretation helper:

```python
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

    latest = store.read_latest_accepted()
    if latest is None:
        return ExecutionMode.PROPOSE_ONLY, "default", None
    if latest.status != ModeAuthorizationStatus.ACCEPTED:
        return ExecutionMode.PROPOSE_ONLY, "default", latest
    if latest.active_mode == ExecutionMode.LIVE:
        warnings.append("live mode authorization is disabled; defaulting to propose_only")
        return ExecutionMode.PROPOSE_ONLY, "default", latest
    return latest.active_mode, "store", latest
```

> NOTE: the `mode_source` value for a stored authorization changes from `"file"`
> to `"store"`. If `tests/test_operator_mode_authorization.py` asserts `"file"`,
> update those assertions to `"store"` in Step 3 (this is the only intended
> behavior-visible change). Keep `DEFAULT_MODE_AUTHORIZATION_PATH` import for
> backward references.

- [ ] **Step 3: Update any existing assertions that referenced `"file"` source**

Run: `uv run pytest tests/test_operator_mode_authorization.py -v`
If failures are only `mode_source == "file"` assertions, change them to `"store"`.
If any other assertion fails, STOP — the refactor changed behavior it should not have;
re-read the diff against the original logic.

- [ ] **Step 4: Run the full operator test set to confirm green**

Run: `uv run pytest tests/test_operator_mode_authorization.py tests/test_operator_api.py tests/test_operator_mode_state_store.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/mode_authorization.py tests/test_operator_mode_authorization.py
git commit -m "refactor(operator): persist mode state via ModeStateStore (rails preserved)"
```

---

## Task 6: Pass env through in api.py so prod selects Supabase automatically

**Files:**
- Modify: `src/prescient/operator/api.py`

- [ ] **Step 1: Confirm current wiring**

Read `src/prescient/operator/api.py`. It builds `active_env` and passes
`mode_path=active_mode_path` to `read_operator_status` / `authorize_execution_mode`.
The default `active_mode_path` resolves to `DEFAULT_MODE_AUTHORIZATION_PATH`, which
would force the file store. We must let prod use Supabase when no explicit path is set.

- [ ] **Step 2: Make mode_path opt-in so env selection works**

In `create_app`, change the mode-path resolution so that an explicit
`PRESCIENT_MODE_AUTHORIZATION_PATH` (or `mode_path` arg) forces the file store, but
when neither is set, `mode_path` stays `None` (letting the factory pick Supabase if
creds exist). Replace the `active_mode_path` block with:

```python
    explicit_mode_path = (
        mode_path
        if mode_path is not None
        else active_env.get("PRESCIENT_MODE_AUTHORIZATION_PATH") or None
    )
    active_mode_path = Path(explicit_mode_path) if explicit_mode_path else None
```

Then in the two route handlers, pass `mode_path=active_mode_path` and
`env=active_env` exactly as before (now `None` when unset). The store factory will
select Supabase when `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are present.

- [ ] **Step 3: Run the operator API tests**

Run: `uv run pytest tests/test_operator_api.py -v`
Expected: PASS. (These tests don't set Supabase env, so they use the file store via
a tmp path or the default — confirm they pass; if a test relied on the default file
path existing, it still works because the factory returns a FileModeStateStore at
the default path when no Supabase env and no explicit path.)

- [ ] **Step 4: Commit**

```bash
git add src/prescient/operator/api.py
git commit -m "feat(operator): api selects Supabase mode store via env when no path set"
```

---

## Task 7: Full-suite regression + apply migration to hosted Supabase

**Files:** none (verification + deploy-side migration)

- [ ] **Step 1: Run the entire backend suite**

Run: `uv run pytest -q`
Expected: all pass (previous green count + the new store tests). No regressions.

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: clean.

- [ ] **Step 3: Apply the migration to the hosted project**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase link --project-ref cnlszlquqnczowrxbvxx   # if not already linked
supabase db push
```

Expected: `operator_mode_authorizations` created on the hosted project.

- [ ] **Step 4: Live smoke test against hosted Supabase (service role)**

```bash
# With SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY exported for the hosted project:
SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... PRESCIENT_OPERATOR_API_TOKEN=dev-operator-token \
  .venv/bin/uvicorn prescient.operator.api:app --port 8009 &
sleep 4
# request paper mode (actor required)
curl -s -X POST -H "Authorization: Bearer dev-operator-token" -H "Content-Type: application/json" \
  -d '{"requested_mode":"paper","reason":"hosted smoke","actor":"smoke@test"}' \
  http://127.0.0.1:8009/mode-authorization | python3 -c "import sys,json;d=json.load(sys.stdin);print('status:',d['status'],'active:',d['active_mode'])"
# read status back — should reflect paper from Supabase, source 'store'
curl -s -H "Authorization: Bearer dev-operator-token" http://127.0.0.1:8009/status \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('mode:',d['execution_mode'],'source:',d['mode_source'])"
# reset to propose_only (hygiene)
curl -s -X POST -H "Authorization: Bearer dev-operator-token" -H "Content-Type: application/json" \
  -d '{"requested_mode":"propose_only","reason":"reset","actor":"smoke@test"}' \
  http://127.0.0.1:8009/mode-authorization >/dev/null
pkill -f "uvicorn prescient.operator.api"
```

Expected: paper request `status: accepted active: paper`; status read `mode: paper source: store`; then reset. Confirms state persisted in Supabase (not a file) and survives a fresh process.

- [ ] **Step 5: Restart-persistence check**

Stop and restart the uvicorn process WITHOUT touching any file; call `/status` again
before the reset — it must still report the last accepted mode from Supabase. This is
the core "survives restart" proof. (Do this between Step 4's read and reset, or repeat.)

- [ ] **Step 6: Commit any final doc/notes (no code expected here)**

```bash
git add -A && git commit -m "test(operator): verify Supabase mode state persists across restart" || echo "nothing to commit"
```

---

## Definition of Done

- `operator_mode_authorizations` table exists locally and on the hosted project (Task 1, 7).
- `ModeStateStore` protocol + `FileModeStateStore` + `SupabaseModeStateStore` + factory exist and are tested (Tasks 2–4).
- `mode_authorization.py` persists via the store; env precedence, propose_only default, and live refusal all preserved (Task 5). Only visible change: `mode_source` `"file"` → `"store"`.
- `api.py` auto-selects Supabase in prod via env (Task 6).
- Full backend suite + ruff pass; no regressions (Task 7).
- Live: a paper-mode request persists in Supabase and survives a process restart (Task 7 Steps 4–5).
