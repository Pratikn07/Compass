# Storage / Supabase Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Prescient's Supabase storage adapter with deterministic tests for database-shaped reads, writes, serialization, provider failures, malformed responses, and production-safety guards.

**Architecture:** Extend the existing R6.4 storage tests around `SupabaseStorageAdapter` using fake Supabase clients for normal CI, then add a small `StorageReadError` exception so read failures are surfaced as structured, journal-safe storage errors. Add test-only integration configuration helpers that make any real Supabase round trip opt-in and reject production-looking settings before a network call can happen.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, pytest-cov, supabase-py v2, Supabase Postgres.

---

## Source Requirements

Use these as the requirements source:

- `/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/06-storage-r6-4-supabase-prd.md`
- Conversation PRD section: "Storage/Supabase tests: Test database reads/writes and failure handling with test data only."

Supabase references checked before planning:

- Supabase Python reference documents `select`, filters, modifiers, upsert, delete, and client initialization.
- Supabase RLS docs state RLS must be enabled on tables in exposed schemas and that service/backend access must remain server-side.
- Supabase changelog currently includes database breaking-change entries around API exposure defaults; this plan avoids schema changes and keeps the normal suite fake-client based.

## Current Repo Facts

- Existing focused test file: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`
- Existing adapter: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/supabase.py`
- Existing storage models: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/models.py`
- Existing exports: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/__init__.py`
- Existing migration tests: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_migration.py`
- Existing R6.4 storage test status: `.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py -q` returns `6 passed`.
- The `prescient` directory is not currently a git repository, so task checkpoints use verification commands instead of commits.

## File Structure

Modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`
  - Add fake-client read support, read/query tests, write failure matrix, and read failure tests.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/models.py`
  - Add `StorageReadError`.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/__init__.py`
  - Export `StorageReadError`.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/supabase.py`
  - Wrap read execution, response errors, and malformed rows in `StorageReadError`.

Create:

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/support/__init__.py`
  - Makes test support imports explicit.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/support/supabase_test_env.py`
  - Test-only helper for opt-in real Supabase integration config validation.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_integration_safety.py`
  - Tests that integration config is disabled by default and rejects production settings.

Do not modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk`
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/signal`
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker`
- Supabase migrations, unless a later schema-specific task is approved separately.

## Safety Rules

- Never use production Supabase credentials.
- Normal CI tests must use fake clients and perform no network calls.
- Any real Supabase test must require `PRESCIENT_SUPABASE_INTEGRATION_TESTS=1`.
- A real Supabase test must reject a URL equal to `SUPABASE_URL`.
- A remote real Supabase test must require a schema name containing `test`.
- Do not disable RLS or use broad public access to make tests pass.
- Do not change risk caps, signal scoring, broker execution, or execution mode behavior.

## Tasks

### Task 1: Capture Baseline and Guard Scope

**Files:**
- Read: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/supabase.py`
- Read: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`
- Read: `/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/06-storage-r6-4-supabase-prd.md`

- [ ] **Step 1: Run the existing focused Supabase storage tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py -q
```

Expected: `6 passed` with only the existing websockets deprecation warning.

- [ ] **Step 2: Capture focused coverage for the Supabase adapter**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py --cov=prescient.storage.supabase --cov-report=term-missing -q
```

Expected: tests pass and coverage reports missing read/error lines in `src/prescient/storage/supabase.py`.

- [ ] **Step 3: Confirm no risk or signal files are changed before work starts**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
find src/prescient/risk src/prescient/signal -type f -name "*.py" | sort
```

Expected: command lists files only. No edits are made in this task.

### Task 2: Add Happy-Path Read and Query-Filter Tests

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`

- [ ] **Step 1: Extend imports**

In `tests/test_r6_4_supabase_storage.py`, keep the existing imports and make sure `date` is already imported from `datetime`. No new package import is needed for this task.

- [ ] **Step 2: Add read and filter tests before the fake client class**

Add these tests after `test_supabase_adapter_upserts_normalized_rows_with_injected_client`:

```python
def test_supabase_adapter_reads_rows_as_decision_journal_records() -> None:
    record = _record(
        journal_record_id="jrnl_read_001",
        run_id="scheduled:2026-06-02",
        decision_id="decision_read_001",
        target="pstg",
        theme="ai_storage",
    )
    fake_client = FakeSupabaseClient(
        read_rows=[StorageRecord.from_decision_journal_record(record).to_journal_record_row()]
    )
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    records = adapter.read_decision_journal_records()

    assert records == [record]
    assert fake_client.schema_name == "prescient_storage"
    assert fake_client.table_name == "journal_records"
    assert fake_client.selected_columns == "*"


def test_supabase_adapter_applies_storage_query_filters_at_provider_boundary() -> None:
    fake_client = FakeSupabaseClient(read_rows=[])
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    records = adapter.read_decision_journal_records(
        StorageQuery(
            run_id="scheduled:2026-06-01",
            decision_id="decision_001",
            target="ntnx",
            theme="ai_storage",
            record_type="strategy_decision",
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 2),
            limit=25,
        )
    )

    assert records == []
    assert fake_client.filters == [
        ("eq", "run_id", "scheduled:2026-06-01"),
        ("eq", "decision_id", "decision_001"),
        ("eq", "target", "NTNX"),
        ("eq", "theme", "AI_STORAGE"),
        ("eq", "record_type", "strategy_decision"),
        ("gte", "trading_date", "2026-06-01"),
        ("lte", "trading_date", "2026-06-02"),
        ("limit", "limit", 25),
    ]
```

- [ ] **Step 3: Replace the fake Supabase client with read-chain support**

Replace the existing `FakeSupabaseClient` class in `tests/test_r6_4_supabase_storage.py` with:

```python
class FakeSupabaseClient:
    def __init__(
        self,
        *,
        read_rows: list[dict[str, Any]] | None = None,
        execute_error: Exception | None = None,
        response_error: object | None = None,
    ) -> None:
        self.read_rows = read_rows or []
        self.execute_error = execute_error
        self.response_error = response_error
        self.schema_name: str | None = None
        self.table_name: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.on_conflict: str | None = None
        self.selected_columns: str | None = None
        self.filters: list[tuple[str, str, object]] = []
        self.operation: str | None = None

    def schema(self, schema_name: str) -> "FakeSupabaseClient":
        self.schema_name = schema_name
        return self

    def table(self, table_name: str) -> "FakeSupabaseClient":
        self.table_name = table_name
        return self

    def select(self, columns: str) -> "FakeSupabaseClient":
        self.operation = "select"
        self.selected_columns = columns
        return self

    def eq(self, column: str, value: object) -> "FakeSupabaseClient":
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column: str, value: object) -> "FakeSupabaseClient":
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value: object) -> "FakeSupabaseClient":
        self.filters.append(("lte", column, value))
        return self

    def limit(self, value: int) -> "FakeSupabaseClient":
        self.filters.append(("limit", "limit", value))
        return self

    def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
        ignore_duplicates: bool = False,
    ) -> "FakeSupabaseClient":
        self.operation = "upsert"
        self.rows = rows
        self.on_conflict = on_conflict
        assert ignore_duplicates is False
        return self

    def execute(self) -> object:
        if self.execute_error is not None:
            raise self.execute_error
        data = self.read_rows if self.operation == "select" else self.rows
        return type("FakeResponse", (), {"data": data, "error": self.response_error})()
```

- [ ] **Step 4: Run the new tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_reads_rows_as_decision_journal_records \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_applies_storage_query_filters_at_provider_boundary \
  -q
```

Expected: both tests pass after the fake client is extended. If either test fails, fix only the test fake or the query assertion unless the adapter is demonstrably violating the PRD.

- [ ] **Step 5: Run the full focused file**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py -q
```

Expected: all tests in the file pass.

### Task 3: Add Structured Read Error Handling

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/models.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/__init__.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/supabase.py`

- [ ] **Step 1: Add the failing read exception test**

In `tests/test_r6_4_supabase_storage.py`, add `StorageReadError` to the `from prescient.storage import (...)` import list.

Add this test after `test_supabase_adapter_returns_secret_safe_structured_errors`:

```python
def test_supabase_adapter_wraps_read_execute_exceptions_as_storage_read_error() -> None:
    fake_client = FakeSupabaseClient(
        execute_error=TimeoutError("request timed out bearer secret should not leak")
    )
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    with pytest.raises(StorageReadError) as exc_info:
        adapter.read_decision_journal_records(StorageQuery(run_id="scheduled:2026-06-01"))

    assert exc_info.value.error.provider == "supabase"
    assert exc_info.value.error.error_type == StorageErrorType.TIMEOUT
    serialized = exc_info.value.error.model_dump_json().lower()
    assert "bearer" not in serialized
    assert "secret" not in serialized
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py::test_supabase_adapter_wraps_read_execute_exceptions_as_storage_read_error -q
```

Expected: fail with an import error for `StorageReadError` or with the raw `TimeoutError`.

- [ ] **Step 3: Add `StorageReadError` to storage models**

In `src/prescient/storage/models.py`, add this class after `StorageConfigurationError`:

```python
class StorageReadError(RuntimeError):
    def __init__(self, error: StorageError) -> None:
        self.error = error
        super().__init__(error.message)
```

- [ ] **Step 4: Export `StorageReadError`**

In `src/prescient/storage/__init__.py`, add `StorageReadError` to the import from `prescient.storage.models`:

```python
    StorageReadError,
```

Also add it to `__all__`:

```python
    "StorageReadError",
```

- [ ] **Step 5: Wrap Supabase read execution errors**

In `src/prescient/storage/supabase.py`, update the storage model imports to include `StorageReadError`:

```python
    StorageReadError,
```

Then replace `read_decision_journal_records` with:

```python
    def read_decision_journal_records(
        self,
        query: StorageQuery | None = None,
    ) -> list[DecisionJournalRecord]:
        # Read support is intentionally narrow for R6.4. Query shaping lives at this
        # storage boundary so runtime and learning code never see raw provider rows.
        active_query = query or StorageQuery()
        try:
            request = self._client.schema(self._schema).table("journal_records").select("*")
            request = _apply_query_filters(request, active_query)
            response = request.execute()
        except Exception as exc:
            raise StorageReadError(_error_from_exception(exc)) from exc

        response_error = getattr(response, "error", None)
        if response_error is not None:
            raise StorageReadError(_error_from_exception(response_error))

        rows = getattr(response, "data", None) or []
        try:
            return [_decision_record_from_row(row) for row in rows]
        except Exception as exc:
            raise StorageReadError(
                StorageError(
                    provider="supabase",
                    error_type=StorageErrorType.MALFORMED_RESPONSE,
                    message="Malformed Supabase journal_records response.",
                    source="supabase",
                )
            ) from exc
```

- [ ] **Step 6: Run the read exception test and verify GREEN**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py::test_supabase_adapter_wraps_read_execute_exceptions_as_storage_read_error -q
```

Expected: pass.

### Task 4: Cover Read Response Errors, Malformed Rows, Empty Reads, and Write Errors

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_storage.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/storage/supabase.py` only if a new test exposes a real PRD violation.

- [ ] **Step 1: Add read response error and malformed row tests**

Add these tests after `test_supabase_adapter_wraps_read_execute_exceptions_as_storage_read_error`:

```python
def test_supabase_adapter_wraps_read_response_errors_as_storage_read_error() -> None:
    fake_client = FakeSupabaseClient(response_error=RuntimeError("403 forbidden by RLS policy"))
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    with pytest.raises(StorageReadError) as exc_info:
        adapter.read_decision_journal_records()

    assert exc_info.value.error.provider == "supabase"
    assert exc_info.value.error.error_type == StorageErrorType.FORBIDDEN


def test_supabase_adapter_reports_malformed_rows_as_storage_read_error() -> None:
    fake_client = FakeSupabaseClient(read_rows=[{"journal_record_id": "jrnl_malformed"}])
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    with pytest.raises(StorageReadError) as exc_info:
        adapter.read_decision_journal_records()

    assert exc_info.value.error.provider == "supabase"
    assert exc_info.value.error.error_type == StorageErrorType.MALFORMED_RESPONSE
    assert exc_info.value.error.message == "Malformed Supabase journal_records response."


def test_supabase_adapter_returns_empty_list_for_empty_read_response() -> None:
    fake_client = FakeSupabaseClient(read_rows=[])
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    records = adapter.read_decision_journal_records(StorageQuery(run_id="missing-run"))

    assert records == []
```

- [ ] **Step 2: Add empty write and write response classification tests**

Add these tests after `test_supabase_adapter_returns_secret_safe_structured_errors`:

```python
def test_supabase_adapter_skips_empty_write_batch_without_provider_call() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    result = adapter.append_decision_journal_records([])

    assert result.ok is True
    assert result.records_written == 0
    assert fake_client.schema_name is None
    assert fake_client.table_name is None


@pytest.mark.parametrize(
    ("message", "expected_type"),
    [
        ("403 forbidden by RLS policy", StorageErrorType.FORBIDDEN),
        ("402 payment required", StorageErrorType.PAYMENT_REQUIRED),
        ("429 too many requests", StorageErrorType.RATE_LIMITED),
        ("database schema mismatch", StorageErrorType.SCHEMA_MISMATCH),
        ("duplicate key conflict", StorageErrorType.CONFLICT),
        ("503 database unavailable", StorageErrorType.UNAVAILABLE),
        ("malformed json response", StorageErrorType.MALFORMED_RESPONSE),
        ("empty response from provider", StorageErrorType.EMPTY_RESPONSE),
    ],
)
def test_supabase_adapter_classifies_write_response_errors(
    message: str,
    expected_type: StorageErrorType,
) -> None:
    fake_client = FakeSupabaseClient(response_error=RuntimeError(message))
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    result = adapter.append_decision_journal_records([_record()])

    assert result.ok is False
    assert result.errors[0].provider == "supabase"
    assert result.errors[0].error_type == expected_type
```

- [ ] **Step 3: Run these tests and fix only exposed storage-boundary issues**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_wraps_read_response_errors_as_storage_read_error \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_reports_malformed_rows_as_storage_read_error \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_returns_empty_list_for_empty_read_response \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_skips_empty_write_batch_without_provider_call \
  tests/test_r6_4_supabase_storage.py::test_supabase_adapter_classifies_write_response_errors \
  -q
```

Expected: all pass after Task 3 implementation. If a classification fails, update only `_error_from_exception` in `src/prescient/storage/supabase.py` with the missing exact phrase branch.

- [ ] **Step 4: Run the focused storage file**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py -q
```

Expected: all R6.4 Supabase storage tests pass.

### Task 5: Add Test-Only Supabase Integration Safety Harness

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/support/__init__.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/support/supabase_test_env.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_integration_safety.py`

- [ ] **Step 1: Create explicit test support package**

Create `tests/support/__init__.py` with:

```python
"""Test-only support helpers."""
```

- [ ] **Step 2: Add Supabase test environment validation helper**

Create `tests/support/supabase_test_env.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse


ENABLE_ENV = "PRESCIENT_SUPABASE_INTEGRATION_TESTS"
TEST_URL_ENV = "PRESCIENT_TEST_SUPABASE_URL"
TEST_SERVICE_ROLE_KEY_ENV = "PRESCIENT_TEST_SUPABASE_SERVICE_ROLE_KEY"
TEST_SCHEMA_ENV = "PRESCIENT_TEST_SUPABASE_SCHEMA"
PRODUCTION_URL_ENV = "SUPABASE_URL"
DEFAULT_TEST_SCHEMA = "prescient_storage_test"


class SupabaseIntegrationTestNotEnabled(RuntimeError):
    pass


class SupabaseTestConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseIntegrationTestConfig:
    url: str
    service_role_key: str
    schema: str


def load_supabase_integration_test_config(
    environ: Mapping[str, str],
) -> SupabaseIntegrationTestConfig:
    if environ.get(ENABLE_ENV) != "1":
        raise SupabaseIntegrationTestNotEnabled(
            f"Set {ENABLE_ENV}=1 to run Supabase integration tests."
        )

    url = environ.get(TEST_URL_ENV, "").strip()
    service_role_key = environ.get(TEST_SERVICE_ROLE_KEY_ENV, "").strip()
    schema = environ.get(TEST_SCHEMA_ENV, DEFAULT_TEST_SCHEMA).strip()

    if not url or not service_role_key:
        raise SupabaseTestConfigurationError(
            f"Missing {TEST_URL_ENV} or {TEST_SERVICE_ROLE_KEY_ENV}."
        )
    if not schema:
        raise SupabaseTestConfigurationError(f"Missing {TEST_SCHEMA_ENV}.")

    production_url = environ.get(PRODUCTION_URL_ENV, "").strip()
    if production_url and url.rstrip("/") == production_url.rstrip("/"):
        raise SupabaseTestConfigurationError("Test Supabase URL must not equal SUPABASE_URL.")

    if not _is_local_url(url) and "test" not in schema.lower():
        raise SupabaseTestConfigurationError(
            "Remote Supabase integration tests must use a schema containing 'test'."
        )

    return SupabaseIntegrationTestConfig(
        url=url,
        service_role_key=service_role_key,
        schema=schema,
    )


def _is_local_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}
```

- [ ] **Step 3: Add safety tests**

Create `tests/test_r6_4_supabase_integration_safety.py` with:

```python
from __future__ import annotations

import pytest

from tests.support.supabase_test_env import (
    ENABLE_ENV,
    TEST_SCHEMA_ENV,
    TEST_SERVICE_ROLE_KEY_ENV,
    TEST_URL_ENV,
    SupabaseIntegrationTestNotEnabled,
    SupabaseTestConfigurationError,
    load_supabase_integration_test_config,
)


def test_supabase_integration_tests_are_disabled_by_default() -> None:
    with pytest.raises(SupabaseIntegrationTestNotEnabled):
        load_supabase_integration_test_config({})


def test_supabase_integration_config_requires_test_credentials_when_enabled() -> None:
    with pytest.raises(SupabaseTestConfigurationError):
        load_supabase_integration_test_config({ENABLE_ENV: "1"})


def test_supabase_integration_config_rejects_production_url_match() -> None:
    with pytest.raises(SupabaseTestConfigurationError, match="must not equal SUPABASE_URL"):
        load_supabase_integration_test_config(
            {
                ENABLE_ENV: "1",
                TEST_URL_ENV: "https://prod-ref.supabase.co",
                TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
                TEST_SCHEMA_ENV: "prescient_storage_test",
                "SUPABASE_URL": "https://prod-ref.supabase.co",
            }
        )


def test_supabase_integration_config_requires_test_schema_for_remote_url() -> None:
    with pytest.raises(SupabaseTestConfigurationError, match="schema containing 'test'"):
        load_supabase_integration_test_config(
            {
                ENABLE_ENV: "1",
                TEST_URL_ENV: "https://remote-ref.supabase.co",
                TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
                TEST_SCHEMA_ENV: "prescient_storage",
            }
        )


def test_supabase_integration_config_accepts_local_project() -> None:
    config = load_supabase_integration_test_config(
        {
            ENABLE_ENV: "1",
            TEST_URL_ENV: "http://127.0.0.1:54321",
            TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
            TEST_SCHEMA_ENV: "prescient_storage",
        }
    )

    assert config.url == "http://127.0.0.1:54321"
    assert config.service_role_key == "test-service-role-key"
    assert config.schema == "prescient_storage"


def test_supabase_integration_config_accepts_remote_test_schema() -> None:
    config = load_supabase_integration_test_config(
        {
            ENABLE_ENV: "1",
            TEST_URL_ENV: "https://remote-ref.supabase.co",
            TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
            TEST_SCHEMA_ENV: "prescient_storage_test",
        }
    )

    assert config.url == "https://remote-ref.supabase.co"
    assert config.service_role_key == "test-service-role-key"
    assert config.schema == "prescient_storage_test"
```

- [ ] **Step 4: Run safety tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_integration_safety.py -q
```

Expected: all safety tests pass and no network call occurs.

### Task 6: Add Opt-In Real Supabase Round-Trip Test

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r6_4_supabase_integration_roundtrip.py`

- [ ] **Step 1: Add opt-in round-trip test**

Create `tests/test_r6_4_supabase_integration_roundtrip.py` with:

```python
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from prescient.runtime.models import DecisionJournalRecord, DecisionJournalRecordType
from prescient.storage import StorageQuery, SupabaseStorageAdapter
from tests.support.supabase_test_env import (
    SupabaseIntegrationTestNotEnabled,
    load_supabase_integration_test_config,
)


def test_supabase_adapter_round_trips_against_configured_test_project() -> None:
    try:
        config = load_supabase_integration_test_config(os.environ)
    except SupabaseIntegrationTestNotEnabled as exc:
        pytest.skip(str(exc))

    from supabase import create_client

    client = create_client(config.url, config.service_role_key)
    adapter = SupabaseStorageAdapter(client=client, schema=config.schema)
    record_id = f"test_jrnl_{uuid4().hex}"
    run_id = f"test_run_{uuid4().hex}"
    record = DecisionJournalRecord(
        journal_record_id=record_id,
        record_type=DecisionJournalRecordType.STRATEGY_DECISION,
        run_id=run_id,
        decision_id=f"test_decision_{uuid4().hex}",
        decision_index=0,
        trading_date=date(2026, 6, 4),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        target="NTNX",
        theme="AI_STORAGE",
        strategy_type="bullish_earnings_readthrough",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="propose_only",
        source="tests.supabase.integration",
        payload={"test": True},
    )

    try:
        write_result = adapter.append_decision_journal_records([record])
        assert write_result.ok is True
        assert write_result.records_written == 1

        records = adapter.read_decision_journal_records(StorageQuery(run_id=run_id, limit=5))

        assert [stored.journal_record_id for stored in records] == [record_id]
        assert records[0].payload == {"test": True}
    finally:
        client.schema(config.schema).table("journal_records").delete().eq(
            "journal_record_id",
            record_id,
        ).execute()
```

- [ ] **Step 2: Run the round-trip test without integration env**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_integration_roundtrip.py -q
```

Expected: `1 skipped`. There must be no network call.

- [ ] **Step 3: Document the command for an intentionally configured local/test Supabase run**

Use this command only with a local Supabase project or a dedicated remote test project:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
PRESCIENT_SUPABASE_INTEGRATION_TESTS=1 \
PRESCIENT_TEST_SUPABASE_URL=http://127.0.0.1:54321 \
PRESCIENT_TEST_SUPABASE_SERVICE_ROLE_KEY="$PRESCIENT_TEST_SUPABASE_SERVICE_ROLE_KEY" \
PRESCIENT_TEST_SUPABASE_SCHEMA=prescient_storage \
.venv/bin/python -m pytest tests/test_r6_4_supabase_integration_roundtrip.py -q
```

Expected against a correctly migrated local Supabase database: `1 passed`. If the schema is missing, the test must fail with a storage error or provider error; do not create schema changes inside this test task.

### Task 7: Verification, Coverage, and Final Report

**Files:**
- Read all changed files.
- Modify only if verification exposes syntax, import, or PRD-alignment issues in the changed files.

- [ ] **Step 1: Run focused R6.4 tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_supabase_integration_safety.py \
  tests/test_r6_4_supabase_integration_roundtrip.py \
  tests/test_r6_4_supabase_migration.py \
  tests/test_r6_4_storage_runtime.py \
  -q
```

Expected: all non-integration tests pass and the round-trip test is skipped unless explicitly enabled.

- [ ] **Step 2: Run focused coverage for Supabase storage**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_supabase_integration_safety.py \
  tests/test_r6_4_supabase_integration_roundtrip.py \
  --cov=prescient.storage.supabase \
  --cov-report=term-missing \
  -q
```

Expected:

- Tests pass.
- Round-trip test is skipped unless integration env is enabled.
- `src/prescient/storage/supabase.py` coverage is materially higher than the prior focused baseline and should be near or above 80%.

- [ ] **Step 3: Run lint on touched Python files**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m ruff check \
  src/prescient/storage/models.py \
  src/prescient/storage/__init__.py \
  src/prescient/storage/supabase.py \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_supabase_integration_safety.py \
  tests/test_r6_4_supabase_integration_roundtrip.py \
  tests/support
```

Expected: no lint errors.

- [ ] **Step 4: Run full suite**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest -q
```

Expected: all tests pass, with the existing websockets deprecation warning allowed.

- [ ] **Step 5: Produce final implementation report**

Write a short final response that includes the measured command output summaries from this task:

```text
Storage/Supabase test hardening complete.

Changed:
- Added read-path fake Supabase coverage.
- Added StorageReadError for structured read failures.
- Added write/read provider error tests.
- Added production-safety checks for opt-in Supabase integration tests.
- Added optional local/test Supabase round-trip test.

Verification:
- Focused R6.4 tests: include the exact pytest summary from Step 1.
- Supabase storage coverage: include the baseline percentage from Task 1 and the final percentage from Step 2.
- Full pytest suite: include the exact pytest summary from Step 4.
- Integration round-trip: state whether it was skipped by default or explicitly run against local/test Supabase.

Notes:
- No risk/signal/broker files changed.
- No production Supabase credentials used.
```

## Self-Review Checklist

- Spec coverage: PRD requirements for reads, writes, failure handling, production safety, fake-client default tests, and optional real test database path are each mapped to a task.
- Scope: This plan stays inside storage tests, storage error models, Supabase adapter read handling, and test-only integration helpers.
- Type consistency: `StorageReadError` carries one `StorageError`, matching `StorageConfigurationError`; write behavior keeps `StorageWriteResult`.
- Safety: Normal test runs perform no network calls and cannot use production Supabase accidentally.
- Remaining intentional gap: this plan does not add schema migrations or RLS policy changes because the PRD asks for storage testing, and the current migration tests already enforce private schema, RLS, revokes, and no privileged public functions.
