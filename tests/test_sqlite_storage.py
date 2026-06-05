from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from prescient.runtime.models import DecisionJournalRecord, DecisionJournalRecordType
from prescient.storage import (
    ProviderErrorRecord,
    ProviderSnapshotRecord,
    SQLiteStorageAdapter,
    SystemHealthRecord,
    SystemHealthStatus,
    StorageQuery,
)


def _record(
    *,
    journal_record_id: str = "jrnl_001",
    run_id: str = "scheduled:2026-06-01",
    decision_id: str = "decision_001",
    trading_date: date = date(2026, 6, 1),
    target: str = "ntnx",
    theme: str = "ai_storage",
    record_type: DecisionJournalRecordType = DecisionJournalRecordType.STRATEGY_DECISION,
    payload: dict[str, object] | None = None,
) -> DecisionJournalRecord:
    return DecisionJournalRecord(
        journal_record_id=journal_record_id,
        record_type=record_type,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=0,
        trading_date=trading_date,
        created_at=datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
        target=target,
        theme=theme,
        strategy_type="bullish_earnings_readthrough",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="propose_only",
        source="runtime.strategy",
        payload=payload or {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
    )


def test_sqlite_storage_initializes_schema_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "storage" / "prescient.sqlite"
    adapter = SQLiteStorageAdapter(database_path)

    adapter.initialize_schema()
    adapter.initialize_schema()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert "journal_records" in tables
    assert "idx_journal_records_run_id" in indexes
    assert "idx_journal_records_decision_id" in indexes
    assert "idx_journal_records_target" in indexes
    assert "idx_journal_records_theme" in indexes
    assert "idx_journal_records_record_type" in indexes
    assert "idx_journal_records_trading_date" in indexes


def test_sqlite_storage_writes_normalized_journal_record_and_reads_by_run_id(
    tmp_path: Path,
) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    record = _record(target="ntnx", theme="ai_storage")

    result = adapter.append_decision_journal_records([record])
    read_back = adapter.read_decision_journal_records(StorageQuery(run_id=record.run_id))

    assert result.ok is True
    assert result.records_written == 1
    assert read_back == [record]

    with sqlite3.connect(tmp_path / "prescient.sqlite") as connection:
        row = connection.execute(
            "SELECT target, theme, payload FROM journal_records WHERE journal_record_id = ?",
            (record.journal_record_id,),
        ).fetchone()

    assert row[0] == "NTNX"
    assert row[1] == "AI_STORAGE"
    assert "Bullish AI_STORAGE read-through" in row[2]


def test_sqlite_storage_query_filters_are_applied(tmp_path: Path) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    matching = _record(
        journal_record_id="jrnl_001",
        run_id="run-a",
        decision_id="decision-a",
        trading_date=date(2026, 6, 2),
        target="ntnx",
        theme="ai_storage",
    )
    wrong_target = _record(
        journal_record_id="jrnl_002",
        run_id="run-a",
        decision_id="decision-b",
        trading_date=date(2026, 6, 2),
        target="crm",
        theme="saas",
    )
    wrong_date = _record(
        journal_record_id="jrnl_003",
        run_id="run-a",
        decision_id="decision-c",
        trading_date=date(2026, 7, 1),
        target="ntnx",
        theme="ai_storage",
    )
    adapter.append_decision_journal_records([matching, wrong_target, wrong_date])

    records = adapter.read_decision_journal_records(
        StorageQuery(
            run_id="run-a",
            target="NTNX",
            theme="AI_STORAGE",
            record_type="strategy_decision",
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
    )

    assert records == [matching]


def test_sqlite_storage_upserts_duplicate_journal_ids(tmp_path: Path) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    first = _record(payload={"version": 1})
    second = _record(payload={"version": 2})

    first_result = adapter.append_decision_journal_records([first])
    second_result = adapter.append_decision_journal_records([second])
    records = adapter.read_decision_journal_records(StorageQuery(run_id=first.run_id))

    assert first_result.records_written == 1
    assert second_result.records_written == 1
    assert len(records) == 1
    assert records[0].payload == {"version": 2}


def test_sqlite_storage_writes_and_reads_provider_snapshots_by_source_id(
    tmp_path: Path,
) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    older = ProviderSnapshotRecord(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        retrieved_at=datetime(2026, 6, 1, 13, tzinfo=timezone.utc),
        payload={"ticker": "OLD"},
    )
    newer = ProviderSnapshotRecord(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        retrieved_at=datetime(2026, 6, 1, 14, tzinfo=timezone.utc),
        payload={"ticker": "NTNX"},
    )

    result = adapter.append_provider_snapshots([older, newer])
    snapshot = adapter.read_provider_snapshot(
        provider="finnhub",
        source_id="earnings_calendar:NTNX",
    )

    assert result.ok is True
    assert result.records_written == 2
    assert snapshot is not None
    assert snapshot.payload == {"ticker": "NTNX"}


def test_sqlite_storage_writes_provider_errors_and_health_payload(
    tmp_path: Path,
) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    error_result = adapter.append_provider_errors(
        [
            ProviderErrorRecord(
                provider="finnhub",
                error_type="rate_limited",
                run_id="scheduled:2026-06-01",
                source="earnings_calendar",
                message="rate limited",
                payload={"retry_after_seconds": 30},
                created_at=datetime(2026, 6, 1, 13, tzinfo=timezone.utc),
            )
        ]
    )
    health_result = adapter.upsert_system_health(
        [
            SystemHealthRecord(
                component="provider_health",
                status=SystemHealthStatus.DEGRADED,
                detail="Provider warnings recorded.",
                run_id="scheduled:2026-06-01",
                payload={"providers": {"finnhub": {"errors": 1}}},
                created_at=datetime(2026, 6, 1, 13, tzinfo=timezone.utc),
            )
        ]
    )

    assert error_result.ok is True
    assert health_result.ok is True
    with sqlite3.connect(tmp_path / "prescient.sqlite") as connection:
        provider_error = connection.execute(
            "SELECT provider, error_type, payload FROM provider_errors"
        ).fetchone()
        health = connection.execute(
            "SELECT component, status, payload FROM system_health"
        ).fetchone()

    assert provider_error[0] == "finnhub"
    assert provider_error[1] == "rate_limited"
    assert '"retry_after_seconds":30' in provider_error[2]
    assert health[0] == "provider_health"
    assert health[1] == "degraded"
    assert '"errors":1' in health[2]


def test_sqlite_storage_serialized_rows_do_not_leak_sensitive_terms(
    tmp_path: Path,
) -> None:
    adapter = SQLiteStorageAdapter(tmp_path / "prescient.sqlite")
    safe_record = _record(payload={"note": "safe fixture payload"})

    adapter.append_decision_journal_records([safe_record])

    with sqlite3.connect(tmp_path / "prescient.sqlite") as connection:
        rows = connection.execute("SELECT * FROM journal_records").fetchall()

    serialized = repr(rows).lower()
    for forbidden in [
        "authorization",
        "bearer",
        "secret",
        "raw_payload",
        "service_role",
    ]:
        assert forbidden not in serialized
