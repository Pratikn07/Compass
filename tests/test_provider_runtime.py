from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prescient.data.models import DataProviderError, DataProviderErrorType
from prescient.data.runtime import (
    ProviderBudgetState,
    ProviderCachePolicy,
    ProviderCallTelemetry,
    ProviderRuntime,
    ProviderRuntimeSettings,
    build_provider_health_record,
)
from prescient.storage import SystemHealthStatus
from prescient.storage import ProviderErrorRecord, ProviderSnapshotRecord


class _Result:
    def __init__(
        self,
        *,
        snapshots: list[dict[str, object]] | None = None,
        errors: list[DataProviderError] | None = None,
    ) -> None:
        self.snapshots = snapshots or []
        self.errors = errors or []


class _MemoryProviderStore:
    def __init__(
        self,
        snapshot: ProviderSnapshotRecord | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.snapshots_written: list[ProviderSnapshotRecord] = []
        self.errors_written: list[ProviderErrorRecord] = []

    def read_provider_snapshot(
        self,
        *,
        provider: str,
        source_id: str,
    ) -> ProviderSnapshotRecord | None:
        if self.snapshot is None:
            return None
        if self.snapshot.provider == provider and self.snapshot.source_id == source_id:
            return self.snapshot
        return None

    def append_provider_snapshots(
        self,
        snapshots: list[ProviderSnapshotRecord],
    ) -> object:
        self.snapshots_written.extend(snapshots)
        return type("WriteResult", (), {"ok": True, "errors": []})()

    def append_provider_errors(self, errors: list[ProviderErrorRecord]) -> object:
        self.errors_written.extend(errors)
        return type("WriteResult", (), {"ok": True, "errors": []})()


def test_provider_runtime_cache_hit_avoids_provider_call() -> None:
    now = datetime(2026, 6, 1, 14, tzinfo=timezone.utc)
    store = _MemoryProviderStore(
        ProviderSnapshotRecord(
            provider="finnhub",
            source_endpoint="earnings_calendar",
            source_id="earnings_calendar:NTNX",
            retrieved_at=now - timedelta(minutes=5),
            payload={"ticker": "NTNX"},
        )
    )
    runtime = ProviderRuntime(
        storage=store,
        settings=ProviderRuntimeSettings(
            cache_policies={
                "earnings_calendar": ProviderCachePolicy(ttl_seconds=3600)
            }
        ),
        now=lambda: now,
    )
    calls = 0

    def fetch() -> _Result:
        nonlocal calls
        calls += 1
        return _Result(snapshots=[{"ticker": "LIVE"}])

    result = runtime.call(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        fetch=fetch,
    )

    assert calls == 0
    assert result.value == {"ticker": "NTNX"}
    assert result.telemetry.cache_status == "hit"
    assert result.telemetry.attempts == 0


def test_provider_runtime_cache_miss_writes_snapshot_and_tracks_budget() -> None:
    now = datetime(2026, 6, 1, 14, tzinfo=timezone.utc)
    store = _MemoryProviderStore()
    budget = ProviderBudgetState(daily_used={"finnhub": 4}, run_used={})
    runtime = ProviderRuntime(storage=store, budget_state=budget, now=lambda: now)

    result = runtime.call(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        fetch=lambda: _Result(snapshots=[{"ticker": "NTNX"}]),
        daily_budget_limit=50,
        run_budget_limit=20,
    )

    assert result.value.snapshots == [{"ticker": "NTNX"}]
    assert result.telemetry.cache_status == "miss"
    assert result.telemetry.attempts == 1
    assert result.telemetry.daily_budget_used == 5
    assert result.telemetry.run_budget_used == 1
    assert store.snapshots_written[0].payload == {"ticker": "NTNX"}


def test_provider_runtime_budget_exhaustion_skips_fetch_and_records_error() -> None:
    store = _MemoryProviderStore()
    runtime = ProviderRuntime(
        storage=store,
        budget_state=ProviderBudgetState(daily_used={"alphavantage": 20}),
    )
    calls = 0

    def fetch() -> _Result:
        nonlocal calls
        calls += 1
        return _Result()

    result = runtime.call(
        provider="alphavantage",
        source_endpoint="news_sentiment",
        source_id="news:AAPL",
        fetch=fetch,
        run_id="scheduled:2026-06-01",
        daily_budget_limit=20,
    )

    assert calls == 0
    assert result.value is None
    assert result.telemetry.status == "skipped_budget_exhausted"
    assert result.errors[0].error_type == DataProviderErrorType.RATE_LIMITED
    assert store.errors_written[0].error_type == "rate_limited"


def test_provider_runtime_retries_retryable_errors_then_succeeds() -> None:
    store = _MemoryProviderStore()
    runtime = ProviderRuntime(storage=store)
    attempts = 0

    def fetch() -> _Result:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return _Result(
                errors=[
                    DataProviderError(
                        provider="finnhub",
                        error_type=DataProviderErrorType.TIMEOUT,
                        message="request timed out",
                    )
                ]
            )
        return _Result(snapshots=[{"ticker": "NTNX"}])

    result = runtime.call(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        fetch=fetch,
    )

    assert attempts == 3
    assert result.value.snapshots == [{"ticker": "NTNX"}]
    assert result.telemetry.retry_count == 2
    assert result.telemetry.status == "success"


def test_provider_runtime_does_not_retry_non_retryable_errors() -> None:
    store = _MemoryProviderStore()
    runtime = ProviderRuntime(storage=store)
    attempts = 0

    def fetch() -> _Result:
        nonlocal attempts
        attempts += 1
        return _Result(
            errors=[
                DataProviderError(
                    provider="finnhub",
                    error_type=DataProviderErrorType.UNAUTHORIZED,
                    message="bad api key",
                )
            ]
        )

    result = runtime.call(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        fetch=fetch,
        run_id="scheduled:2026-06-01",
    )

    assert attempts == 1
    assert result.value is None
    assert result.telemetry.status == "failed"
    assert store.errors_written[0].message == "bad api key"


def test_provider_runtime_redacts_secret_like_storage_error_text() -> None:
    store = _MemoryProviderStore()
    runtime = ProviderRuntime(storage=store)

    result = runtime.call(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id="earnings_calendar:NTNX",
        fetch=lambda: _Result(
            errors=[
                DataProviderError(
                    provider="finnhub",
                    error_type=DataProviderErrorType.PROVIDER_UNAVAILABLE,
                    message="bearer secret FINNHUB_API_KEY=abc123 raw_payload={...}",
                )
            ]
        ),
        run_id="scheduled:2026-06-01",
    )

    serialized = store.errors_written[0].model_dump_json().lower()
    assert result.telemetry.error_count == 1
    assert "abc123" not in serialized
    assert "bearer" not in serialized
    assert "raw_payload" not in serialized


def test_build_provider_health_record_summarizes_degraded_provider_state() -> None:
    created_at = datetime(2026, 6, 1, 14, tzinfo=timezone.utc)
    record = build_provider_health_record(
        run_id="scheduled:2026-06-01",
        telemetry=[
            ProviderCallTelemetry(
                provider="finnhub",
                source_endpoint="earnings_calendar",
                source_id="earnings_calendar:NTNX",
                status="success",
                cache_status="miss",
                attempts=1,
                daily_budget_used=1,
                daily_budget_limit=50,
                run_budget_used=1,
                run_budget_limit=20,
                last_success_at=created_at,
            ),
            ProviderCallTelemetry(
                provider="alpha_vantage",
                source_endpoint="news_sentiment",
                source_id="news:AAPL",
                status="skipped_budget_exhausted",
                cache_status="miss",
                attempts=0,
                error_count=1,
                daily_budget_used=20,
                daily_budget_limit=20,
                run_budget_used=0,
                run_budget_limit=2,
                warnings=["Provider budget exhausted."],
            ),
        ],
        created_at=created_at,
    )

    assert record.component == "provider_health"
    assert record.status == SystemHealthStatus.DEGRADED
    assert record.detail == "1 provider issue recorded."
    assert record.payload["providers"]["finnhub"]["requests"] == 1
    assert record.payload["providers"]["alpha_vantage"]["errors"] == 1
    assert record.payload["providers"]["alpha_vantage"]["budget_used"] == 20


def test_build_provider_health_record_blocks_when_all_provider_calls_fail() -> None:
    created_at = datetime(2026, 6, 1, 14, tzinfo=timezone.utc)
    record = build_provider_health_record(
        run_id="scheduled:2026-06-01",
        telemetry=[
            ProviderCallTelemetry(
                provider="finnhub",
                source_endpoint="earnings_calendar",
                source_id="earnings_calendar:NTNX",
                status="failed",
                cache_status="miss",
                attempts=3,
                retry_count=2,
                error_count=1,
                daily_budget_used=3,
                daily_budget_limit=50,
                run_budget_used=3,
                run_budget_limit=20,
            )
        ],
        created_at=created_at,
    )

    assert record.status == SystemHealthStatus.BLOCKED
    assert record.detail == "All provider calls failed or were skipped."
