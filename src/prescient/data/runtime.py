from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from prescient.data.models import DataProviderError, DataProviderErrorType
from prescient.storage import (
    ProviderErrorRecord,
    ProviderSnapshotRecord,
    SystemHealthRecord,
    SystemHealthStatus,
)

T = TypeVar("T")

DEFAULT_DAILY_BUDGETS: dict[str, int] = {
    "finnhub": 50,
    "fmp": 50,
    "alpha_vantage": 20,
    "sec_edgar": 100,
    "options": 50,
}
DEFAULT_RUN_BUDGETS: dict[str, int] = {
    "finnhub": 20,
    "fmp": 20,
    "alpha_vantage": 2,
    "sec_edgar": 20,
    "options": 20,
}
DEFAULT_CACHE_TTLS_SECONDS: dict[str, int] = {
    "earnings_calendar": 6 * 60 * 60,
    "company_earnings": 24 * 60 * 60,
    "eps_estimates": 24 * 60 * 60,
    "revenue_estimates": 24 * 60 * 60,
    "peers": 7 * 24 * 60 * 60,
    "news_sentiment": 2 * 60 * 60,
    "sec_facts": 24 * 60 * 60,
    "sec_filings": 24 * 60 * 60,
    "options_chain": 5 * 60,
}
_RETRYABLE_ERROR_TYPES = {
    DataProviderErrorType.TIMEOUT,
    DataProviderErrorType.PROVIDER_UNAVAILABLE,
}
_NEVER_RETRY_ERROR_TYPES = {
    DataProviderErrorType.MISSING_API_KEY,
    DataProviderErrorType.MISSING_USER_AGENT,
    DataProviderErrorType.UNAUTHORIZED,
    DataProviderErrorType.PAYMENT_REQUIRED,
    DataProviderErrorType.UNSUPPORTED_SYMBOL,
    DataProviderErrorType.MALFORMED_RESPONSE,
    DataProviderErrorType.INVALID_SCHEMA_RESPONSE,
    DataProviderErrorType.EMPTY_RESPONSE,
}


class ProviderCachePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ttl_seconds: int
    allow_stale_on_error: bool = True

    def is_fresh(self, retrieved_at: datetime | None, *, now: datetime) -> bool:
        if retrieved_at is None:
            return False
        return retrieved_at + timedelta(seconds=self.ttl_seconds) >= now


class ProviderRuntimeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    daily_budget_limits: dict[str, int] = Field(
        default_factory=lambda: dict(DEFAULT_DAILY_BUDGETS)
    )
    run_budget_limits: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_RUN_BUDGETS))
    cache_policies: dict[str, ProviderCachePolicy] = Field(
        default_factory=lambda: {
            name: ProviderCachePolicy(ttl_seconds=ttl)
            for name, ttl in DEFAULT_CACHE_TTLS_SECONDS.items()
        }
    )
    max_attempts: int = 3
    max_retry_after_seconds: int = 60

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProviderRuntimeSettings":
        active_env = env if env is not None else os.environ
        return cls(
            daily_budget_limits=_merge_int_json(
                DEFAULT_DAILY_BUDGETS,
                active_env.get("PRESCIENT_PROVIDER_DAILY_BUDGETS_JSON"),
            ),
            run_budget_limits=_merge_int_json(
                DEFAULT_RUN_BUDGETS,
                active_env.get("PRESCIENT_PROVIDER_RUN_BUDGETS_JSON"),
            ),
        )


class ProviderBudgetState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_used: dict[str, int] = Field(default_factory=dict)
    run_used: dict[str, int] = Field(default_factory=dict)

    def can_attempt(
        self,
        provider: str,
        *,
        daily_limit: int,
        run_limit: int,
    ) -> bool:
        key = _provider_key(provider)
        return (
            _budget_count(self.daily_used, key) < daily_limit
            and _budget_count(self.run_used, key) < run_limit
        )

    def record_attempt(self, provider: str) -> None:
        key = _provider_key(provider)
        self.daily_used[key] = self.daily_used.get(key, 0) + 1
        self.run_used[key] = self.run_used.get(key, 0) + 1


class ProviderCallTelemetry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    source_endpoint: str
    source_id: str
    status: str
    cache_status: str
    attempts: int = 0
    retry_count: int = 0
    error_count: int = 0
    daily_budget_used: int = 0
    daily_budget_limit: int = 0
    run_budget_used: int = 0
    run_budget_limit: int = 0
    last_success_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class ProviderRuntimeCallResult(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    value: T | dict[str, Any] | None = None
    telemetry: ProviderCallTelemetry
    errors: list[DataProviderError] = Field(default_factory=list)


class ProviderRuntime:
    def __init__(
        self,
        *,
        storage: object | None = None,
        settings: ProviderRuntimeSettings | None = None,
        budget_state: ProviderBudgetState | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._storage = storage
        self._settings = settings or ProviderRuntimeSettings()
        self._budget_state = budget_state or ProviderBudgetState()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def call(
        self,
        *,
        provider: str,
        source_endpoint: str,
        source_id: str,
        fetch: Callable[[], T],
        run_id: str | None = None,
        target: str | None = None,
        theme: str | None = None,
        daily_budget_limit: int | None = None,
        run_budget_limit: int | None = None,
        cache_decoder: Callable[[dict[str, Any]], T] | None = None,
        snapshot_payload: Callable[[T], dict[str, Any]] | None = None,
    ) -> ProviderRuntimeCallResult[T]:
        provider_key = _provider_key(provider)
        now = self._now()
        daily_limit = daily_budget_limit or self._settings.daily_budget_limits.get(
            provider_key, 0
        )
        run_limit = run_budget_limit or self._settings.run_budget_limits.get(provider_key, 0)
        policy = self._settings.cache_policies.get(source_endpoint)
        cached = self._read_cached_snapshot(
            provider=provider_key,
            source_id=source_id,
            policy=policy,
            now=now,
        )
        if cached is not None:
            value = cache_decoder(cached.payload) if cache_decoder else cached.payload
            return ProviderRuntimeCallResult(
                value=value,
                telemetry=self._telemetry(
                    provider=provider_key,
                    source_endpoint=source_endpoint,
                    source_id=source_id,
                    status="success",
                    cache_status="hit",
                    daily_limit=daily_limit,
                    run_limit=run_limit,
                    last_success_at=cached.retrieved_at,
                ),
            )

        if not self._budget_state.can_attempt(
            provider_key,
            daily_limit=daily_limit,
            run_limit=run_limit,
        ):
            error = DataProviderError(
                provider=provider_key,
                error_type=DataProviderErrorType.RATE_LIMITED,
                message="Provider budget exhausted.",
                retry_after_seconds=None,
            )
            self._write_provider_errors(
                [error],
                provider=provider_key,
                run_id=run_id,
                target=target,
                source=source_endpoint,
            )
            return ProviderRuntimeCallResult(
                value=None,
                errors=[error],
                telemetry=self._telemetry(
                    provider=provider_key,
                    source_endpoint=source_endpoint,
                    source_id=source_id,
                    status="skipped_budget_exhausted",
                    cache_status="miss",
                    daily_limit=daily_limit,
                    run_limit=run_limit,
                    error_count=1,
                    warnings=["Provider budget exhausted."],
                ),
            )

        attempts = 0
        retry_count = 0
        errors: list[DataProviderError] = []
        value: T | None = None
        for attempt in range(1, self._settings.max_attempts + 1):
            attempts = attempt
            self._budget_state.record_attempt(provider_key)
            try:
                value = fetch()
            except Exception as exc:
                errors = [_error_from_exception(provider_key, exc)]
            else:
                errors = _errors_from_result(value)
                if not errors:
                    payload = snapshot_payload(value) if snapshot_payload else _payload_from_value(value)
                    self._write_provider_snapshot(
                        ProviderSnapshotRecord(
                            provider=provider_key,
                            target=target,
                            theme=theme,
                            source_endpoint=source_endpoint,
                            source_id=source_id,
                            retrieved_at=now,
                            payload=payload,
                        )
                    )
                    return ProviderRuntimeCallResult(
                        value=value,
                        telemetry=self._telemetry(
                            provider=provider_key,
                            source_endpoint=source_endpoint,
                            source_id=source_id,
                            status="success",
                            cache_status="miss",
                            attempts=attempts,
                            retry_count=retry_count,
                            daily_limit=daily_limit,
                            run_limit=run_limit,
                            last_success_at=now,
                        ),
                    )

            if not _should_retry(
                errors,
                max_retry_after_seconds=self._settings.max_retry_after_seconds,
            ):
                break
            if attempt >= self._settings.max_attempts:
                break
            retry_count += 1

        self._write_provider_errors(
            errors,
            provider=provider_key,
            run_id=run_id,
            target=target,
            source=source_endpoint,
        )
        return ProviderRuntimeCallResult(
            value=None,
            errors=errors,
            telemetry=self._telemetry(
                provider=provider_key,
                source_endpoint=source_endpoint,
                source_id=source_id,
                status="failed",
                cache_status="miss",
                attempts=attempts,
                retry_count=retry_count,
                error_count=len(errors),
                daily_limit=daily_limit,
                run_limit=run_limit,
            ),
        )

    def _read_cached_snapshot(
        self,
        *,
        provider: str,
        source_id: str,
        policy: ProviderCachePolicy | None,
        now: datetime,
    ) -> ProviderSnapshotRecord | None:
        if policy is None or self._storage is None:
            return None
        reader = getattr(self._storage, "read_provider_snapshot", None)
        if not callable(reader):
            return None
        snapshot = reader(provider=provider, source_id=source_id)
        if not isinstance(snapshot, ProviderSnapshotRecord):
            return None
        if policy.is_fresh(snapshot.retrieved_at, now=now):
            return snapshot
        return None

    def _write_provider_snapshot(self, snapshot: ProviderSnapshotRecord) -> None:
        if self._storage is None:
            return
        writer = getattr(self._storage, "append_provider_snapshots", None)
        if callable(writer):
            writer([snapshot])

    def _write_provider_errors(
        self,
        errors: list[DataProviderError],
        *,
        provider: str,
        run_id: str | None,
        target: str | None,
        source: str,
    ) -> None:
        if self._storage is None or not errors:
            return
        writer = getattr(self._storage, "append_provider_errors", None)
        if not callable(writer):
            return
        writer(
            [
                ProviderErrorRecord(
                    provider=provider,
                    error_type=error.error_type.value,
                    run_id=run_id,
                    target=target or error.symbol,
                    source=source,
                    message=error.message,
                    payload={
                        "endpoint": error.endpoint,
                        "status_code": error.status_code,
                        "retry_after_seconds": error.retry_after_seconds,
                    },
                )
                for error in errors
            ]
        )

    def _telemetry(
        self,
        *,
        provider: str,
        source_endpoint: str,
        source_id: str,
        status: str,
        cache_status: str,
        daily_limit: int,
        run_limit: int,
        attempts: int = 0,
        retry_count: int = 0,
        error_count: int = 0,
        last_success_at: datetime | None = None,
        warnings: list[str] | None = None,
    ) -> ProviderCallTelemetry:
        return ProviderCallTelemetry(
            provider=provider,
            source_endpoint=source_endpoint,
            source_id=source_id,
            status=status,
            cache_status=cache_status,
            attempts=attempts,
            retry_count=retry_count,
            error_count=error_count,
            daily_budget_used=_budget_count(self._budget_state.daily_used, provider),
            daily_budget_limit=daily_limit,
            run_budget_used=_budget_count(self._budget_state.run_used, provider),
            run_budget_limit=run_limit,
            last_success_at=last_success_at,
            warnings=warnings or [],
        )


def _provider_key(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"alphavantage", "alpha-vantage"}:
        return "alpha_vantage"
    return normalized


def _budget_count(values: dict[str, int], provider: str) -> int:
    key = _provider_key(provider)
    aliases = {key}
    if key == "alpha_vantage":
        aliases.add("alphavantage")
    return sum(values.get(alias, 0) for alias in aliases)


def _merge_int_json(defaults: dict[str, int], raw: str | None) -> dict[str, int]:
    values = dict(defaults)
    if not raw:
        return values
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return values
    for key, value in parsed.items():
        if isinstance(value, int) and value >= 0:
            values[_provider_key(str(key))] = value
    return values


def _errors_from_result(value: object) -> list[DataProviderError]:
    errors = getattr(value, "errors", [])
    if not isinstance(errors, list):
        return []
    return [error for error in errors if isinstance(error, DataProviderError)]


def _payload_from_value(value: object) -> dict[str, Any]:
    snapshots = getattr(value, "snapshots", None)
    if isinstance(snapshots, list) and snapshots:
        return _dump_payload(snapshots[0])
    return _dump_payload(value)


def _dump_payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    return {"value": repr(value)}


def _error_from_exception(provider: str, exc: Exception) -> DataProviderError:
    error_type = (
        DataProviderErrorType.TIMEOUT
        if isinstance(exc, TimeoutError)
        else DataProviderErrorType.PROVIDER_UNAVAILABLE
    )
    return DataProviderError(
        provider=provider,
        error_type=error_type,
        message=str(exc) or type(exc).__name__,
    )


def _should_retry(
    errors: list[DataProviderError],
    *,
    max_retry_after_seconds: int,
) -> bool:
    if not errors:
        return False
    for error in errors:
        if error.error_type in _NEVER_RETRY_ERROR_TYPES:
            return False
        if error.error_type == DataProviderErrorType.RATE_LIMITED:
            retry_after = error.retry_after_seconds
            if retry_after is None or retry_after > max_retry_after_seconds:
                return False
            continue
        if error.error_type not in _RETRYABLE_ERROR_TYPES:
            return False
    return True


def build_provider_health_record(
    *,
    run_id: str,
    telemetry: list[ProviderCallTelemetry],
    created_at: datetime | None = None,
) -> SystemHealthRecord:
    now = created_at or datetime.now(timezone.utc)
    issue_count = sum(
        1 for item in telemetry if item.error_count > 0 or item.status != "success"
    )
    if not telemetry:
        status = SystemHealthStatus.UNKNOWN
        detail = "No provider telemetry recorded."
    elif issue_count == 0:
        status = SystemHealthStatus.HEALTHY
        detail = "Provider reads completed."
    elif issue_count == len(telemetry):
        status = SystemHealthStatus.BLOCKED
        detail = "All provider calls failed or were skipped."
    else:
        status = SystemHealthStatus.DEGRADED
        detail = f"{issue_count} provider issue{'s' if issue_count != 1 else ''} recorded."

    return SystemHealthRecord(
        component="provider_health",
        status=status,
        detail=detail,
        latency_seconds=None,
        run_id=run_id,
        payload={"providers": _provider_health_payload(telemetry)},
        created_at=now,
    )


def _provider_health_payload(
    telemetry: list[ProviderCallTelemetry],
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for item in telemetry:
        row = payload.setdefault(
            item.provider,
            {
                "requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "retries": 0,
                "errors": 0,
                "budget_used": 0,
                "budget_limit": item.daily_budget_limit,
                "last_success_at": None,
                "warnings": [],
            },
        )
        row["requests"] += item.attempts
        if item.cache_status == "hit":
            row["cache_hits"] += 1
        elif item.cache_status == "miss":
            row["cache_misses"] += 1
        row["retries"] += item.retry_count
        row["errors"] += item.error_count
        row["budget_used"] = max(int(row["budget_used"]), item.daily_budget_used)
        row["budget_limit"] = max(int(row["budget_limit"]), item.daily_budget_limit)
        if item.last_success_at is not None:
            row["last_success_at"] = item.last_success_at.isoformat().replace(
                "+00:00", "Z"
            )
        warnings = row["warnings"]
        if isinstance(warnings, list):
            for warning in item.warnings:
                if warning not in warnings:
                    warnings.append(warning)
    return payload
