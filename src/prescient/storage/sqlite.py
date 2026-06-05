from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from prescient.runtime.models import DecisionJournalRecord
from prescient.storage.models import (
    ProviderErrorRecord,
    ProviderSnapshotRecord,
    RunStatusRecord,
    SystemHealthRecord,
    StorageQuery,
    StorageRecord,
    StorageWriteResult,
)


class SQLiteStorageAdapter:
    def __init__(self, path: str | Path, *, initialize: bool = True) -> None:
        self.path = Path(path)
        if initialize:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_records (
                    journal_record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    decision_id TEXT,
                    decision_index INTEGER,
                    trading_date TEXT,
                    created_at TEXT NOT NULL,
                    target TEXT,
                    theme TEXT,
                    strategy_type TEXT,
                    strategy_status TEXT,
                    execution_mode TEXT,
                    source TEXT,
                    provider TEXT,
                    order_id TEXT,
                    parent_record_id TEXT,
                    duplicate_of_record_id TEXT,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            for column in [
                "run_id",
                "decision_id",
                "target",
                "theme",
                "record_type",
                "trading_date",
            ]:
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_journal_records_{column}
                    ON journal_records ({column})
                    """
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    trigger_type TEXT,
                    scheduled_date TEXT,
                    current_date TEXT,
                    window_start TEXT,
                    window_end TEXT,
                    status TEXT,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_snapshots (
                    provider_snapshot_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    target TEXT,
                    theme TEXT,
                    source_endpoint TEXT,
                    source_url TEXT,
                    source_id TEXT,
                    as_of TEXT,
                    retrieved_at TEXT,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_snapshots_provider_source_id
                ON provider_snapshots (provider, source_id, retrieved_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_errors (
                    provider_error_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    run_id TEXT,
                    target TEXT,
                    source TEXT,
                    message TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS system_health (
                    system_health_id TEXT PRIMARY KEY,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT,
                    latency_seconds REAL,
                    run_id TEXT,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        batch = list(records)
        if not batch:
            return StorageWriteResult(records_written=0)

        self.initialize_schema()
        rows = [
            StorageRecord.from_decision_journal_record(record).to_journal_record_row()
            for record in batch
        ]
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO journal_records (
                    journal_record_id,
                    record_type,
                    run_id,
                    decision_id,
                    decision_index,
                    trading_date,
                    created_at,
                    target,
                    theme,
                    strategy_type,
                    strategy_status,
                    execution_mode,
                    source,
                    provider,
                    order_id,
                    parent_record_id,
                    duplicate_of_record_id,
                    payload,
                    schema_version
                ) VALUES (
                    :journal_record_id,
                    :record_type,
                    :run_id,
                    :decision_id,
                    :decision_index,
                    :trading_date,
                    :created_at,
                    :target,
                    :theme,
                    :strategy_type,
                    :strategy_status,
                    :execution_mode,
                    :source,
                    :provider,
                    :order_id,
                    :parent_record_id,
                    :duplicate_of_record_id,
                    :payload_json,
                    :schema_version
                )
                ON CONFLICT(journal_record_id) DO UPDATE SET
                    record_type = excluded.record_type,
                    run_id = excluded.run_id,
                    decision_id = excluded.decision_id,
                    decision_index = excluded.decision_index,
                    trading_date = excluded.trading_date,
                    created_at = excluded.created_at,
                    target = excluded.target,
                    theme = excluded.theme,
                    strategy_type = excluded.strategy_type,
                    strategy_status = excluded.strategy_status,
                    execution_mode = excluded.execution_mode,
                    source = excluded.source,
                    provider = excluded.provider,
                    order_id = excluded.order_id,
                    parent_record_id = excluded.parent_record_id,
                    duplicate_of_record_id = excluded.duplicate_of_record_id,
                    payload = excluded.payload,
                    schema_version = excluded.schema_version
                """,
                [_sqlite_row(row) for row in rows],
            )
        return StorageWriteResult(records_written=len(rows))

    def upsert_run_status(self, record: RunStatusRecord) -> StorageWriteResult:
        self.initialize_schema()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    trigger_type,
                    scheduled_date,
                    current_date,
                    window_start,
                    window_end,
                    status,
                    payload,
                    schema_version,
                    created_at
                ) VALUES (
                    :run_id,
                    :trigger_type,
                    :scheduled_date,
                    :current_date,
                    :window_start,
                    :window_end,
                    :status,
                    :payload_json,
                    :schema_version,
                    :created_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    trigger_type = excluded.trigger_type,
                    scheduled_date = excluded.scheduled_date,
                    current_date = excluded.current_date,
                    window_start = excluded.window_start,
                    window_end = excluded.window_end,
                    status = excluded.status,
                    payload = excluded.payload,
                    schema_version = excluded.schema_version,
                    created_at = excluded.created_at
                """,
                _sqlite_row(record.to_row()),
            )
        return StorageWriteResult(records_written=1)

    def append_provider_snapshots(
        self,
        snapshots: Iterable[ProviderSnapshotRecord | dict[str, object]],
    ) -> StorageWriteResult:
        records = [_provider_snapshot_record(snapshot) for snapshot in snapshots]
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        self.initialize_schema()
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO provider_snapshots (
                    provider_snapshot_id,
                    provider,
                    target,
                    theme,
                    source_endpoint,
                    source_url,
                    source_id,
                    as_of,
                    retrieved_at,
                    payload,
                    schema_version,
                    created_at
                ) VALUES (
                    :provider_snapshot_id,
                    :provider,
                    :target,
                    :theme,
                    :source_endpoint,
                    :source_url,
                    :source_id,
                    :as_of,
                    :retrieved_at,
                    :payload_json,
                    :schema_version,
                    :created_at
                )
                ON CONFLICT(provider_snapshot_id) DO UPDATE SET
                    provider = excluded.provider,
                    target = excluded.target,
                    theme = excluded.theme,
                    source_endpoint = excluded.source_endpoint,
                    source_url = excluded.source_url,
                    source_id = excluded.source_id,
                    as_of = excluded.as_of,
                    retrieved_at = excluded.retrieved_at,
                    payload = excluded.payload,
                    schema_version = excluded.schema_version,
                    created_at = excluded.created_at
                """,
                [_sqlite_row(row) for row in rows],
            )
        return StorageWriteResult(records_written=len(rows))

    def append_provider_errors(
        self,
        errors: Iterable[ProviderErrorRecord | dict[str, object]],
    ) -> StorageWriteResult:
        records = [_provider_error_record(error) for error in errors]
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        self.initialize_schema()
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO provider_errors (
                    provider_error_id,
                    provider,
                    error_type,
                    run_id,
                    target,
                    source,
                    message,
                    payload,
                    schema_version,
                    created_at
                ) VALUES (
                    :provider_error_id,
                    :provider,
                    :error_type,
                    :run_id,
                    :target,
                    :source,
                    :message,
                    :payload_json,
                    :schema_version,
                    :created_at
                )
                ON CONFLICT(provider_error_id) DO UPDATE SET
                    provider = excluded.provider,
                    error_type = excluded.error_type,
                    run_id = excluded.run_id,
                    target = excluded.target,
                    source = excluded.source,
                    message = excluded.message,
                    payload = excluded.payload,
                    schema_version = excluded.schema_version,
                    created_at = excluded.created_at
                """,
                [_sqlite_row(row) for row in rows],
            )
        return StorageWriteResult(records_written=len(rows))

    def upsert_system_health(
        self,
        records: Iterable[SystemHealthRecord],
    ) -> StorageWriteResult:
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        self.initialize_schema()
        with sqlite3.connect(self.path) as connection:
            connection.executemany(
                """
                INSERT INTO system_health (
                    system_health_id,
                    component,
                    status,
                    detail,
                    latency_seconds,
                    run_id,
                    payload,
                    schema_version,
                    created_at
                ) VALUES (
                    :system_health_id,
                    :component,
                    :status,
                    :detail,
                    :latency_seconds,
                    :run_id,
                    :payload_json,
                    :schema_version,
                    :created_at
                )
                ON CONFLICT(system_health_id) DO UPDATE SET
                    component = excluded.component,
                    status = excluded.status,
                    detail = excluded.detail,
                    latency_seconds = excluded.latency_seconds,
                    run_id = excluded.run_id,
                    payload = excluded.payload,
                    schema_version = excluded.schema_version,
                    created_at = excluded.created_at
                """,
                [_sqlite_row(row) for row in rows],
            )
        return StorageWriteResult(records_written=len(rows))

    def read_decision_journal_records(
        self,
        query: StorageQuery | None = None,
    ) -> Sequence[DecisionJournalRecord]:
        active_query = query or StorageQuery()
        self.initialize_schema()
        sql = "SELECT * FROM journal_records"
        clauses: list[str] = []
        params: dict[str, Any] = {}

        _add_filter(clauses, params, "run_id", active_query.run_id)
        _add_filter(clauses, params, "decision_id", active_query.decision_id)
        _add_filter(clauses, params, "target", active_query.target)
        _add_filter(clauses, params, "theme", active_query.theme)
        _add_filter(clauses, params, "record_type", active_query.record_type)
        if active_query.from_date is not None:
            clauses.append("trading_date >= :from_date")
            params["from_date"] = active_query.from_date.isoformat()
        if active_query.to_date is not None:
            clauses.append("trading_date <= :to_date")
            params["to_date"] = active_query.to_date.isoformat()

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY trading_date, created_at, journal_record_id"
        if active_query.limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = active_query.limit

        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()

        return [_record_from_row(row) for row in rows]

    def read_provider_snapshot(
        self,
        *,
        provider: str,
        source_id: str,
    ) -> ProviderSnapshotRecord | None:
        self.initialize_schema()
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT * FROM provider_snapshots
                WHERE provider = ? AND source_id = ?
                ORDER BY retrieved_at DESC, created_at DESC
                LIMIT 1
                """,
                (provider.strip().lower(), source_id),
            ).fetchone()

        return _provider_snapshot_from_row(row) if row is not None else None


def _sqlite_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "payload_json": json.dumps(row["payload"], sort_keys=True, separators=(",", ":")),
    }


def _add_filter(
    clauses: list[str],
    params: dict[str, Any],
    column: str,
    value: str | None,
) -> None:
    if value is None:
        return
    clauses.append(f"{column} = :{column}")
    params[column] = value


def _record_from_row(row: sqlite3.Row) -> DecisionJournalRecord:
    return DecisionJournalRecord.model_validate(
        {
            "journal_record_id": row["journal_record_id"],
            "record_type": row["record_type"],
            "run_id": row["run_id"],
            "decision_id": row["decision_id"],
            "decision_index": row["decision_index"],
            "trading_date": row["trading_date"],
            "created_at": row["created_at"],
            "target": row["target"],
            "theme": row["theme"],
            "strategy_type": row["strategy_type"],
            "strategy_status": row["strategy_status"],
            "execution_mode": row["execution_mode"],
            "source": row["source"],
            "order_id": row["order_id"],
            "parent_record_id": row["parent_record_id"],
            "duplicate_of_record_id": row["duplicate_of_record_id"],
            "payload": json.loads(row["payload"]),
        }
    )


def _provider_snapshot_record(
    value: ProviderSnapshotRecord | dict[str, object],
) -> ProviderSnapshotRecord:
    if isinstance(value, ProviderSnapshotRecord):
        return value
    data = dict(value)
    data.pop("provider_snapshot_id", None)
    return ProviderSnapshotRecord.model_validate(data)


def _provider_error_record(
    value: ProviderErrorRecord | dict[str, object],
) -> ProviderErrorRecord:
    if isinstance(value, ProviderErrorRecord):
        return value
    data = dict(value)
    data.pop("provider_error_id", None)
    return ProviderErrorRecord.model_validate(data)


def _provider_snapshot_from_row(row: sqlite3.Row) -> ProviderSnapshotRecord:
    return ProviderSnapshotRecord.model_validate(
        {
            "provider": row["provider"],
            "target": row["target"],
            "theme": row["theme"],
            "source_endpoint": row["source_endpoint"],
            "source_url": row["source_url"],
            "source_id": row["source_id"],
            "as_of": row["as_of"],
            "retrieved_at": row["retrieved_at"],
            "payload": json.loads(row["payload"]),
            "schema_version": row["schema_version"],
            "created_at": row["created_at"],
        }
    )
