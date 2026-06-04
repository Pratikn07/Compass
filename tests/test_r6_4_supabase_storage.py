from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from prescient.runtime.models import DecisionJournalRecord, DecisionJournalRecordType
from prescient.storage import (
    JsonlStorageAdapter,
    StorageConfigurationError,
    StorageError,
    StorageErrorType,
    StorageQuery,
    StorageRecord,
    StorageReadError,
    StorageWriteRequiredError,
    StorageWriteResult,
    SupabaseStorageAdapter,
)


def _record(
    *,
    journal_record_id: str = "jrnl_001",
    run_id: str = "scheduled:2026-06-01",
    decision_id: str = "decision_001",
    target: str = "ntnx",
    theme: str = "ai_storage",
) -> DecisionJournalRecord:
    return DecisionJournalRecord(
        journal_record_id=journal_record_id,
        record_type=DecisionJournalRecordType.STRATEGY_DECISION,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=0,
        trading_date=date(2026, 6, 1),
        created_at=datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
        target=target,
        theme=theme,
        strategy_type="bullish_earnings_readthrough",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="propose_only",
        source="runtime.strategy",
        payload={"thesis": "Bullish AI_STORAGE read-through for NTNX."},
    )


def test_storage_record_normalizes_decision_journal_metadata() -> None:
    record = _record()

    storage_record = StorageRecord.from_decision_journal_record(record)
    row = storage_record.to_journal_record_row()

    assert storage_record.schema_version == 1
    assert storage_record.storage_record_id == "jrnl_001"
    assert storage_record.record_type == "strategy_decision"
    assert storage_record.target == "NTNX"
    assert storage_record.theme == "AI_STORAGE"
    assert row["journal_record_id"] == "jrnl_001"
    assert row["trading_date"] == "2026-06-01"
    assert row["created_at"] == "2026-06-01T14:30:00Z"
    assert row["payload"] == {"thesis": "Bullish AI_STORAGE read-through for NTNX."}


def test_storage_record_projects_run_row_from_journal_record() -> None:
    row = StorageRecord.from_decision_journal_record(_record()).to_run_row()

    assert row == {
        "run_id": "scheduled:2026-06-01",
        "trigger_type": "scheduled",
        "scheduled_date": "2026-06-01",
        "current_date": "2026-06-01",
        "window_start": "2026-06-01",
        "window_end": "2026-06-01",
        "status": "recorded",
        "payload": {
            "source": "storage_projection",
            "execution_mode": "propose_only",
            "record_count": 1,
        },
        "schema_version": 1,
        "created_at": "2026-06-01T14:30:00Z",
    }


def test_storage_record_projects_decision_row_only_for_strategy_decision() -> None:
    strategy_row = StorageRecord.from_decision_journal_record(
        _record()
    ).to_decision_record_row()

    assert strategy_row == {
        "decision_record_id": "decision_001",
        "run_id": "scheduled:2026-06-01",
        "decision_id": "decision_001",
        "decision_index": 0,
        "trading_date": "2026-06-01",
        "target": "NTNX",
        "theme": "AI_STORAGE",
        "strategy_type": "bullish_earnings_readthrough",
        "strategy_status": "candidate_ready_for_analyst",
        "execution_mode": "propose_only",
        "payload": {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
        "schema_version": 1,
        "created_at": "2026-06-01T14:30:00Z",
    }

    analyst = _record(journal_record_id="jrnl_analyst")
    analyst = analyst.model_copy(
        update={"record_type": DecisionJournalRecordType.ANALYST_REVIEW}
    )
    assert (
        StorageRecord.from_decision_journal_record(analyst).to_decision_record_row()
        is None
    )


def test_jsonl_storage_adapter_preserves_existing_record_shape(tmp_path: Path) -> None:
    journal_path = tmp_path / "runtime" / "journal.jsonl"
    adapter = JsonlStorageAdapter(journal_path)
    record = _record()

    result = adapter.append_decision_journal_records([record])
    read_back = adapter.read_decision_journal_records(StorageQuery(run_id=record.run_id))

    assert result.ok is True
    assert result.records_written == 1
    assert result.errors == []
    assert json.loads(journal_path.read_text().splitlines()[0])["journal_record_id"] == (
        record.journal_record_id
    )
    assert read_back == [record]


def test_supabase_adapter_upserts_normalized_rows_with_injected_client() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")
    record = _record(target="ntnx", theme="ai_storage")

    result = adapter.append_decision_journal_records([record])

    assert result.ok is True
    assert result.records_written == 1
    assert fake_client.schema_name == "prescient_storage"
    assert fake_client.upserts_by_table["journal_records"][0]["journal_record_id"] == (
        record.journal_record_id
    )
    assert fake_client.conflicts_by_table["journal_records"] == "journal_record_id"
    assert fake_client.upserts_by_table["journal_records"][0]["target"] == "NTNX"
    assert fake_client.upserts_by_table["journal_records"][0]["theme"] == "AI_STORAGE"
    assert fake_client.upserts_by_table["journal_records"][0]["provider"] is None


def test_supabase_adapter_upserts_run_and_decision_projections() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")
    strategy = _record()
    analyst = strategy.model_copy(
        update={
            "journal_record_id": "jrnl_analyst",
            "record_type": DecisionJournalRecordType.ANALYST_REVIEW,
        }
    )

    result = adapter.append_decision_journal_records([strategy, analyst])

    assert result.ok is True
    assert result.records_written == 2
    assert fake_client.upserts_by_table["journal_records"][0]["journal_record_id"] == (
        "jrnl_001"
    )
    assert fake_client.upserts_by_table["journal_records"][1]["journal_record_id"] == (
        "jrnl_analyst"
    )
    assert fake_client.upserts_by_table["runs"] == [
        {
            "run_id": "scheduled:2026-06-01",
            "trigger_type": "scheduled",
            "scheduled_date": "2026-06-01",
            "current_date": "2026-06-01",
            "window_start": "2026-06-01",
            "window_end": "2026-06-01",
            "status": "recorded",
            "payload": {
                "source": "storage_projection",
                "execution_mode": "propose_only",
                "record_count": 2,
            },
            "schema_version": 1,
            "created_at": "2026-06-01T14:30:00Z",
        }
    ]
    assert fake_client.upserts_by_table["decision_records"] == [
        {
            "decision_record_id": "decision_001",
            "run_id": "scheduled:2026-06-01",
            "decision_id": "decision_001",
            "decision_index": 0,
            "trading_date": "2026-06-01",
            "target": "NTNX",
            "theme": "AI_STORAGE",
            "strategy_type": "bullish_earnings_readthrough",
            "strategy_status": "candidate_ready_for_analyst",
            "execution_mode": "propose_only",
            "payload": {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
            "schema_version": 1,
            "created_at": "2026-06-01T14:30:00Z",
        }
    ]
    assert fake_client.conflicts_by_table == {
        "journal_records": "journal_record_id",
        "runs": "run_id",
        "decision_records": "decision_record_id",
    }


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


def test_supabase_adapter_returns_secret_safe_structured_errors() -> None:
    fake_client = FakeSupabaseClient(
        execute_error=RuntimeError(
            "401 Authorization bearer secret SUPABASE_SERVICE_ROLE_KEY=abcdef raw_payload={...}"
        )
    )
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    result = adapter.append_decision_journal_records([_record()])

    assert result.ok is False
    assert result.errors[0].provider == "supabase"
    assert result.errors[0].error_type == StorageErrorType.UNAUTHORIZED
    serialized = result.errors[0].model_dump_json().lower()
    assert "abcdef" not in serialized
    assert "authorization" not in serialized
    assert "raw_payload" not in serialized
    assert "service_role" not in serialized


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


def test_supabase_from_env_requires_url_and_service_role_key() -> None:
    with pytest.raises(StorageConfigurationError) as exc_info:
        SupabaseStorageAdapter.from_env(environ={})

    assert exc_info.value.error.error_type == StorageErrorType.MISSING_CREDENTIALS
    assert "SUPABASE_SERVICE_ROLE_KEY" not in exc_info.value.error.model_dump_json()


def test_required_storage_write_policy_raises_secret_safe_error() -> None:
    error = StorageError(
        provider="supabase",
        error_type=StorageErrorType.RATE_LIMITED,
        message="429 bearer token should not leak",
    )
    result = StorageWriteResult(errors=[error])

    with pytest.raises(StorageWriteRequiredError) as exc_info:
        result.raise_if_required()

    assert "bearer" not in str(exc_info.value).lower()
    assert exc_info.value.errors == [error]


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
        self.upserts_by_table: dict[str, list[dict[str, Any]]] = {}
        self.conflicts_by_table: dict[str, str] = {}
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
        if self.table_name is not None:
            self.upserts_by_table[self.table_name] = rows
            self.conflicts_by_table[self.table_name] = on_conflict
        assert ignore_duplicates is False
        return self

    def execute(self) -> object:
        if self.execute_error is not None:
            raise self.execute_error
        data = self.read_rows if self.operation == "select" else self.rows
        return type("FakeResponse", (), {"data": data, "error": self.response_error})()
