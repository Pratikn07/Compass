from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol, cast

from prescient.runtime.models import DecisionJournalRecord
from prescient.storage.models import (
    DecisionAttentionStatus,
    ProviderErrorRecord,
    ProviderSnapshotRecord,
    RunStatusRecord,
    SystemHealthRecord,
    SystemHealthStatus,
    StorageConfigurationError,
    StorageError,
    StorageErrorType,
    StorageQuery,
    StorageReadError,
    StorageRecord,
    StorageWriteResult,
)


class _SupabaseExecutable(Protocol):
    def execute(self) -> object:
        ...


class _SupabaseTable(Protocol):
    def select(self, columns: str) -> Any:
        ...

    def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
        ignore_duplicates: bool = False,
    ) -> _SupabaseExecutable:
        ...


class _SupabaseSchemaClient(Protocol):
    def table(self, table_name: str) -> _SupabaseTable:
        ...


class _SupabaseClient(Protocol):
    def schema(self, schema_name: str) -> _SupabaseSchemaClient:
        ...


class SupabaseStorageAdapter:
    def __init__(
        self,
        *,
        client: _SupabaseClient,
        schema: str = "prescient_storage",
    ) -> None:
        self._client = client
        self._schema = schema

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        create_client_factory: Callable[[str, str], _SupabaseClient] | None = None,
    ) -> "SupabaseStorageAdapter":
        env = environ if environ is not None else os.environ
        url = env.get("SUPABASE_URL", "").strip()
        service_role_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        schema = env.get("PRESCIENT_STORAGE_SCHEMA", "prescient_storage").strip()

        if not url or not service_role_key:
            raise StorageConfigurationError(
                StorageError(
                    provider="supabase",
                    error_type=StorageErrorType.MISSING_CREDENTIALS,
                    message="Missing Supabase storage configuration.",
                    source="env",
                )
            )

        factory = create_client_factory
        if factory is None:
            from supabase import create_client

            factory = cast(Callable[[str, str], _SupabaseClient], create_client)

        return cls(client=factory(url, service_role_key), schema=schema)

    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        storage_records = [
            StorageRecord.from_decision_journal_record(record) for record in records
        ]
        journal_rows = [record.to_journal_record_row() for record in storage_records]
        if not journal_rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="journal_records",
                rows=journal_rows,
                on_conflict="journal_record_id",
            )
            run_rows = _project_run_rows(storage_records)
            if run_rows:
                self._upsert_rows(
                    table_name="runs",
                    rows=run_rows,
                    on_conflict="run_id",
                )
            decision_rows = _project_decision_rows(storage_records)
            if decision_rows:
                self._upsert_rows(
                    table_name="decision_records",
                    rows=decision_rows,
                    on_conflict="decision_record_id",
                )
            system_health_rows = [
                record.to_row() for record in _project_system_health_records(storage_records)
            ]
            if system_health_rows:
                self._upsert_rows(
                    table_name="system_health",
                    rows=system_health_rows,
                    on_conflict="system_health_id",
                )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(journal_rows))

    def upsert_system_health(
        self,
        records: Iterable[SystemHealthRecord],
    ) -> StorageWriteResult:
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="system_health",
                rows=rows,
                on_conflict="system_health_id",
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(rows))

    def upsert_run_status(
        self,
        record: RunStatusRecord,
    ) -> StorageWriteResult:
        try:
            self._upsert_rows(
                table_name="runs",
                rows=[record.to_row()],
                on_conflict="run_id",
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=1)

    def append_provider_snapshots(
        self,
        snapshots: Iterable[ProviderSnapshotRecord | dict[str, object]],
    ) -> StorageWriteResult:
        records = [_provider_snapshot_record(snapshot) for snapshot in snapshots]
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="provider_snapshots",
                rows=rows,
                on_conflict="provider_snapshot_id",
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(rows))

    def append_provider_errors(
        self,
        errors: Iterable[ProviderErrorRecord | dict[str, object]],
    ) -> StorageWriteResult:
        records = [_provider_error_record(error) for error in errors]
        rows = [record.to_row() for record in records]
        if not rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="provider_errors",
                rows=rows,
                on_conflict="provider_error_id",
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(rows))

    def upsert_watchlist_seed_rows(
        self,
        *,
        watchlists: Iterable[dict[str, Any]],
        items: Iterable[dict[str, Any]],
    ) -> StorageWriteResult:
        watchlist_rows = [dict(row) for row in watchlists]
        item_rows = [dict(row) for row in items]
        if not watchlist_rows and not item_rows:
            return StorageWriteResult(records_written=0)

        try:
            if watchlist_rows:
                self._upsert_rows(
                    table_name="watchlists",
                    rows=watchlist_rows,
                    on_conflict="watchlist_id",
                )
            if item_rows:
                self._upsert_rows(
                    table_name="watchlist_items",
                    rows=item_rows,
                    on_conflict="watchlist_item_id",
                )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(watchlist_rows) + len(item_rows))

    def append_learning_reports(
        self,
        reports: Iterable[dict[str, object]],
    ) -> StorageWriteResult:
        report_rows = [dict(report) for report in reports]
        if not report_rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="learning_reports",
                rows=report_rows,
                on_conflict="learning_report_id",
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(report_rows))

    def read_provider_snapshot(
        self,
        *,
        provider: str,
        source_id: str,
    ) -> ProviderSnapshotRecord | None:
        try:
            request = (
                self._client.schema(self._schema)
                .table("provider_snapshots")
                .select("*")
                .eq("provider", provider.strip().lower())
                .eq("source_id", source_id)
            )
            order = getattr(request, "order", None)
            if callable(order):
                request = order("retrieved_at", desc=True)
            response = request.limit(1).execute()
        except Exception as exc:
            raise StorageReadError(_error_from_exception(exc)) from exc

        response_error = getattr(response, "error", None)
        if response_error is not None:
            raise StorageReadError(_error_from_exception(response_error))

        rows = getattr(response, "data", None) or []
        if not rows:
            return None
        try:
            return _provider_snapshot_record(rows[0])
        except Exception as exc:
            raise StorageReadError(
                StorageError(
                    provider="supabase",
                    error_type=StorageErrorType.MALFORMED_RESPONSE,
                    message="Malformed Supabase provider_snapshots response.",
                    source="supabase",
                )
            ) from exc

    def _upsert_rows(
        self,
        *,
        table_name: str,
        rows: list[dict[str, Any]],
        on_conflict: str,
    ) -> None:
        response = (
            self._client.schema(self._schema)
            .table(table_name)
            .upsert(rows, on_conflict=on_conflict, ignore_duplicates=False)
            .execute()
        )
        response_error = getattr(response, "error", None)
        if response_error is not None:
            raise RuntimeError(str(response_error))

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


def _apply_query_filters(request: Any, query: StorageQuery) -> Any:
    if query.run_id is not None:
        request = request.eq("run_id", query.run_id)
    if query.decision_id is not None:
        request = request.eq("decision_id", query.decision_id)
    if query.target is not None:
        request = request.eq("target", query.target)
    if query.theme is not None:
        request = request.eq("theme", query.theme)
    if query.record_type is not None:
        request = request.eq("record_type", query.record_type)
    if query.from_date is not None:
        request = request.gte("trading_date", query.from_date.isoformat())
    if query.to_date is not None:
        request = request.lte("trading_date", query.to_date.isoformat())
    if query.limit is not None:
        request = request.limit(query.limit)
    return request


def _project_run_rows(storage_records: list[StorageRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StorageRecord]] = {}
    for record in storage_records:
        grouped.setdefault(record.run_id, []).append(record)

    rows: list[dict[str, Any]] = []
    for records in grouped.values():
        first = min(records, key=lambda record: record.created_at)
        rows.append(first.to_run_row(record_count=len(records)))
    return rows


def _project_decision_rows(storage_records: list[StorageRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StorageRecord]] = {}
    for record in storage_records:
        if record.decision_id is not None:
            grouped.setdefault(record.decision_id, []).append(record)

    rows: list[dict[str, Any]] = []
    for records in grouped.values():
        strategy_record = next(
            (record for record in records if record.record_type == "strategy_decision"),
            None,
        )
        if strategy_record is None:
            continue
        attention_status, attention_reasons = _attention_for_records(records)
        row = strategy_record.to_decision_record_row(
            attention_status=attention_status,
            attention_reasons=attention_reasons,
        )
        if row is not None:
            rows.append(row)
    return rows


def _attention_for_records(
    records: list[StorageRecord],
) -> tuple[DecisionAttentionStatus, list[str]]:
    reasons: list[str] = []
    for record in records:
        payload = record.payload
        if record.record_type == "strategy_decision":
            for value in _string_list(payload.get("missing_data")):
                _append_unique(reasons, f"missing_data: {value}")
            for value in _string_list(payload.get("warnings")):
                _append_unique(reasons, f"warning: {value}")
        elif record.record_type == "analyst_review":
            analysis = _mapping(payload.get("analysis"))
            for value in _string_list(analysis.get("missing_context")):
                _append_unique(reasons, f"analyst_missing_context: {value}")
            if payload.get("status") == "failed" and isinstance(
                payload.get("error_message"), str
            ):
                _append_unique(reasons, f"analyst_error: {payload['error_message']}")
        elif record.record_type == "risk_decision":
            for value in _string_list(payload.get("rejection_reasons")):
                _append_unique(reasons, f"risk_rejection: {value}")
        elif record.record_type == "position_sizing":
            for value in _string_list(payload.get("rejection_reasons")):
                _append_unique(reasons, f"sizing_rejection: {value}")

    status = (
        DecisionAttentionStatus.NEEDS_ATTENTION
        if reasons
        else DecisionAttentionStatus.NORMAL
    )
    return status, reasons


def _project_system_health_records(
    storage_records: list[StorageRecord],
) -> list[SystemHealthRecord]:
    grouped: dict[str, list[StorageRecord]] = {}
    for record in storage_records:
        grouped.setdefault(record.run_id, []).append(record)

    health: list[SystemHealthRecord] = []
    for run_id, records in grouped.items():
        created_at = max(record.created_at for record in records)
        strategy_records = [
            record for record in records if record.record_type == "strategy_decision"
        ]
        risk_records = [
            record
            for record in records
            if record.record_type in {"risk_decision", "position_sizing"}
        ]

        market_missing = [
            value
            for record in strategy_records
            for value in _string_list(record.payload.get("missing_data"))
            if value != "options_chain"
        ]
        option_counts = [
            _number_or_none(
                _mapping(record.payload.get("data_snapshot")).get(
                    "option_contract_count"
                )
            )
            for record in strategy_records
        ]
        option_missing = any(count == 0 for count in option_counts if count is not None)
        risk_rejections = [
            value
            for record in risk_records
            for value in _string_list(record.payload.get("rejection_reasons"))
        ]

        health.append(
            SystemHealthRecord(
                component="market_data",
                status=SystemHealthStatus.DEGRADED
                if market_missing
                else SystemHealthStatus.HEALTHY,
                detail="Missing data: " + ", ".join(sorted(set(market_missing)))
                if market_missing
                else "Provider reads completed.",
                latency_seconds=None,
                run_id=run_id,
                created_at=created_at,
            )
        )
        health.append(
            SystemHealthRecord(
                component="pricing_engine",
                status=SystemHealthStatus.DEGRADED
                if option_missing
                else SystemHealthStatus.HEALTHY,
                detail="Option chain incomplete."
                if option_missing
                else "Pricing inputs available.",
                latency_seconds=None,
                run_id=run_id,
                created_at=created_at,
            )
        )
        health.append(
            SystemHealthRecord(
                component="risk_engine",
                status=SystemHealthStatus.BLOCKED
                if risk_rejections
                else (
                    SystemHealthStatus.HEALTHY
                    if risk_records
                    else SystemHealthStatus.UNKNOWN
                ),
                detail="Risk rejection: " + ", ".join(sorted(set(risk_rejections)))
                if risk_rejections
                else (
                    "Risk checks completed."
                    if risk_records
                    else "No risk records for this run."
                ),
                latency_seconds=None,
                run_id=run_id,
                created_at=created_at,
            )
        )
    return health


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _number_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


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


def _decision_record_from_row(row: Mapping[str, Any]) -> DecisionJournalRecord:
    return DecisionJournalRecord.model_validate(
        {
            "journal_record_id": row["journal_record_id"],
            "record_type": row["record_type"],
            "run_id": row["run_id"],
            "decision_id": row["decision_id"],
            "decision_index": row.get("decision_index"),
            "trading_date": row["trading_date"],
            "created_at": row["created_at"],
            "target": row.get("target"),
            "theme": row.get("theme"),
            "strategy_type": row.get("strategy_type"),
            "strategy_status": row.get("strategy_status"),
            "execution_mode": row.get("execution_mode"),
            "source": row["source"],
            "order_id": row.get("order_id"),
            "parent_record_id": row.get("parent_record_id"),
            "duplicate_of_record_id": row.get("duplicate_of_record_id"),
            "payload": row.get("payload") or {},
        }
    )


def _error_from_exception(exc: object) -> StorageError:
    message = str(exc)
    lowered = message.lower()
    error_type = StorageErrorType.UNKNOWN

    if "401" in lowered or "unauthorized" in lowered:
        error_type = StorageErrorType.UNAUTHORIZED
    elif "403" in lowered or "forbidden" in lowered:
        error_type = StorageErrorType.FORBIDDEN
    elif "402" in lowered or "payment" in lowered:
        error_type = StorageErrorType.PAYMENT_REQUIRED
    elif "429" in lowered or "rate limit" in lowered or "too many" in lowered:
        error_type = StorageErrorType.RATE_LIMITED
    elif "timeout" in lowered or "timed out" in lowered:
        error_type = StorageErrorType.TIMEOUT
    elif "malformed" in lowered or "json" in lowered:
        error_type = StorageErrorType.MALFORMED_RESPONSE
    elif "empty" in lowered:
        error_type = StorageErrorType.EMPTY_RESPONSE
    elif "unsupported" in lowered:
        error_type = StorageErrorType.UNSUPPORTED_SYMBOL
    elif "503" in lowered or "unavailable" in lowered:
        error_type = StorageErrorType.UNAVAILABLE
    elif "schema" in lowered:
        error_type = StorageErrorType.SCHEMA_MISMATCH
    elif "conflict" in lowered or "duplicate" in lowered:
        error_type = StorageErrorType.CONFLICT

    return StorageError(
        provider="supabase",
        error_type=error_type,
        message=message,
        source="supabase",
    )
