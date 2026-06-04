from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from prescient.runtime.models import DecisionJournalRecord
from prescient.storage.models import StorageQuery, StorageRecord, StorageWriteResult


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
