"""Bounded provider-data scheduled runs.

This module wires provider configuration, the strategy universe, the Phase B/C
assembler contract, the existing scheduler pipeline, and storage audit writes.
Provider calls are routed through ProviderRuntime so adapters stay unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from prescient.data import DataProviderError
from prescient.data.config import ProviderConfig
from prescient.data.models import (
    CompanyEarningsResult,
    CompanyFactsResult,
    EarningsCalendarResult,
    EarningsEstimateResult,
    FilingHistoryResult,
    HistoricalPriceResult,
    NewsSentimentResult,
    PeerListResult,
    RevenueEstimateResult,
)
from prescient.data.providers import (
    build_alpaca_market_data_adapter,
    build_alpha_vantage_adapter,
    build_finnhub_adapter,
    build_fmp_adapter,
    build_fmp_market_data_adapter,
    build_sec_edgar_adapter,
)
from prescient.data.runtime import (
    ProviderCallTelemetry,
    ProviderRuntime,
    ProviderRuntimeSettings,
    build_provider_health_record,
)
from prescient.scheduler import (
    ScheduleTriggerType,
    ScheduledRunRequest,
    run_scheduled_strategy_pipeline,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategySettings,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.universe import load_strategy_universe
from prescient.storage import RunStatusRecord

_DEFAULT_UNIVERSE_PATH = Path("config/themes.yaml")
_DEFAULT_SETTINGS = StrategySettings(earnings_window_days=14)
_REQUIRED_PROVIDER_NAMES = ("finnhub", "fmp")


class LiveDataConfigurationError(RuntimeError):
    """Secret-safe configuration error for scheduled provider-data runs."""


@dataclass(frozen=True)
class AssembledLivePipelineInputs:
    """Phase B/C assembly output consumed by live-data orchestration."""

    universe: StrategyUniverse
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: Mapping[str, TargetMarketData] | None
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None = None
    provider_snapshots: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[DataProviderError] = field(default_factory=list)
    skipped_targets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LiveDataRunSummary:
    run_id: str
    decision_count: int
    provider_error_count: int
    skipped_target_count: int
    wrote_storage: bool


Assembler = Callable[..., AssembledLivePipelineInputs]


def run_live_data_pipeline(
    *,
    current_date: date,
    universe_path: str | Path = _DEFAULT_UNIVERSE_PATH,
    storage_writer: object | None = None,
    storage_write_policy: object = "required",
    env: Mapping[str, str] | None = None,
    assembler: Assembler | None = None,
    settings: StrategySettings = _DEFAULT_SETTINGS,
    runtime_settings: ProviderRuntimeSettings | None = None,
) -> LiveDataRunSummary:
    active_env = env if env is not None else os.environ
    config = ProviderConfig.from_env(active_env)
    _require_provider_config(config, _REQUIRED_PROVIDER_NAMES)

    writer = storage_writer if storage_writer is not None else _supabase_writer(active_env)
    run_id = f"{ScheduleTriggerType.SCHEDULED.value}:{current_date.isoformat()}"
    window_end = current_date + timedelta(days=settings.earnings_window_days)
    universe = load_strategy_universe(universe_path)
    telemetry: list[ProviderCallTelemetry] = []
    runtime = ProviderRuntime(
        storage=writer,
        settings=runtime_settings or ProviderRuntimeSettings.from_env(active_env),
        now=lambda: datetime.now(timezone.utc),
    )
    provider_adapters = _wrap_provider_adapters(
        _build_provider_adapters(config),
        runtime=runtime,
        telemetry=telemetry,
        run_id=run_id,
    )
    assemble = assembler if assembler is not None else _missing_assembler

    assembled = assemble(
        run_id=run_id,
        universe=universe,
        current_date=current_date,
        provider_config=config,
        provider_adapters=provider_adapters,
        provider_runtime=runtime,
    )

    provider_error_rows = _provider_error_rows(
        run_id=run_id,
        errors=assembled.provider_errors,
    )
    _write_storage_result(
        writer=writer,
        method_name="append_provider_snapshots",
        values=assembled.provider_snapshots,
        storage_write_policy=storage_write_policy,
    )
    _write_storage_result(
        writer=writer,
        method_name="append_provider_errors",
        values=provider_error_rows,
        storage_write_policy=storage_write_policy,
    )
    _write_provider_health(
        writer=writer,
        run_id=run_id,
        telemetry=telemetry,
        storage_write_policy=storage_write_policy,
    )

    request = ScheduledRunRequest(
        run_id=run_id,
        trigger_type=ScheduleTriggerType.SCHEDULED,
        scheduled_date=current_date,
        current_date=current_date,
        window_start=current_date,
        window_end=window_end,
        relevant_tickers=_relevant_tickers(assembled),
    )
    result = run_scheduled_strategy_pipeline(
        request=request,
        universe=assembled.universe,
        upcoming_events=assembled.upcoming_events,
        peer_results=assembled.peer_results,
        target_market_data=assembled.target_market_data,
        options_chains=assembled.options_chains,
        indicator_snapshots=assembled.indicator_snapshots,
        settings=settings,
        enable_claude_analysis=False,
        storage_writer=writer,
        storage_write_policy=storage_write_policy,
    )

    decision_count = result.summary.total_decision_count
    if decision_count == 0:
        _append_empty_decision_batch(writer)
        _write_no_candidate_run_status(
            writer=writer,
            run_id=run_id,
            current_date=current_date,
            window_end=window_end,
            provider_error_count=_provider_error_count(provider_error_rows, telemetry),
            skipped_target_count=len(assembled.skipped_targets),
            storage_write_policy=storage_write_policy,
        )

    return LiveDataRunSummary(
        run_id=run_id,
        decision_count=decision_count,
        provider_error_count=_provider_error_count(provider_error_rows, telemetry),
        skipped_target_count=len(assembled.skipped_targets),
        wrote_storage=writer is not None,
    )


def _require_provider_config(
    config: ProviderConfig,
    provider_names: Sequence[str],
) -> None:
    missing = config.missing_for(list(provider_names))
    if missing:
        raise LiveDataConfigurationError(
            "Missing mandatory live-data provider configuration: "
            + ", ".join(sorted(missing))
        )


def _build_provider_adapters(config: ProviderConfig) -> dict[str, object | None]:
    return {
        "finnhub": build_finnhub_adapter(config),
        "fmp": build_fmp_adapter(config),
        "fmp_market_data": build_fmp_market_data_adapter(config),
        "alphavantage": build_alpha_vantage_adapter(config),
        "sec_edgar": build_sec_edgar_adapter(config),
        "alpaca": _build_alpaca_adapter(config),
    }


def _build_alpaca_adapter(config: ProviderConfig) -> object | None:
    """Build the Alpaca adapter with live SDK readers when creds are present.

    SDK readers are constructed here (orchestration layer), not in the data
    package, to keep prescient.data free of the Alpaca SDK import.
    """
    if not config.has("alpaca"):
        return None
    from prescient.live_data.alpaca_readers import build_alpaca_sdk_readers

    option_chain_reader, daily_bars_reader = build_alpaca_sdk_readers(
        api_key_id=config.alpaca_api_key_id or "",
        api_secret_key=config.alpaca_api_secret_key or "",
    )
    return build_alpaca_market_data_adapter(
        config,
        option_chain_reader=option_chain_reader,
        daily_bars_reader=daily_bars_reader,
    )


def _wrap_provider_adapters(
    adapters: Mapping[str, object | None],
    *,
    runtime: ProviderRuntime,
    telemetry: list[ProviderCallTelemetry],
    run_id: str,
) -> dict[str, object | None]:
    wrapped: dict[str, object | None] = {}
    for provider, adapter in adapters.items():
        wrapped[provider] = (
            None
            if adapter is None
            else _RuntimeProviderAdapter(
                provider=provider,
                inner=adapter,
                runtime=runtime,
                telemetry=telemetry,
                run_id=run_id,
            )
        )
    return wrapped


def _missing_assembler(**_: Any) -> AssembledLivePipelineInputs:
    raise LiveDataConfigurationError(
        "Phase B/C assemble_pipeline_inputs contract is not configured."
    )


def _provider_error_rows(
    *,
    run_id: str,
    errors: Sequence[DataProviderError],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, error in enumerate(errors):
        provider = error.provider.value
        source = error.endpoint or "provider"
        target = error.symbol
        target_part = target or "global"
        rows.append(
            {
                "provider_error_id": f"{run_id}:{provider}:{source}:{target_part}:{index}",
                "provider": provider,
                "error_type": error.error_type.value,
                "run_id": run_id,
                "target": target,
                "source": source,
                "message": error.message,
                "payload": {
                    "retry_after_seconds": error.retry_after_seconds,
                    "status_code": error.status_code,
                },
                "schema_version": 1,
            }
        )
    return rows


def _write_storage_result(
    *,
    writer: object | None,
    method_name: str,
    values: Sequence[dict[str, Any]],
    storage_write_policy: object,
) -> None:
    if writer is None or not values:
        return
    method = getattr(writer, method_name, None)
    if not callable(method):
        raise TypeError(f"storage_writer must implement {method_name}().")
    result = method(values)
    _raise_for_required_storage_errors(result, storage_write_policy)


def _write_provider_health(
    *,
    writer: object | None,
    run_id: str,
    telemetry: list[ProviderCallTelemetry],
    storage_write_policy: object,
) -> None:
    if writer is None or not telemetry:
        return
    upsert = getattr(writer, "upsert_system_health", None)
    if not callable(upsert):
        return
    result = upsert([build_provider_health_record(run_id=run_id, telemetry=telemetry)])
    _raise_for_required_storage_errors(result, storage_write_policy)


def _write_no_candidate_run_status(
    *,
    writer: object | None,
    run_id: str,
    current_date: date,
    window_end: date,
    provider_error_count: int,
    skipped_target_count: int,
    storage_write_policy: object,
) -> None:
    if writer is None:
        return
    upsert = getattr(writer, "upsert_run_status", None)
    if not callable(upsert):
        raise TypeError("storage_writer must implement upsert_run_status().")
    result = upsert(
        RunStatusRecord(
            run_id=run_id,
            trigger_type=ScheduleTriggerType.SCHEDULED.value,
            scheduled_date=current_date,
            current_date=current_date,
            window_start=current_date,
            window_end=window_end,
            status="no_candidates",
            payload={
                "source": "live_data_run",
                "execution_mode": "propose_only",
                "decision_count": 0,
                "provider_error_count": provider_error_count,
                "skipped_target_count": skipped_target_count,
            },
            created_at=datetime.combine(current_date, time.min, tzinfo=timezone.utc),
        )
    )
    _raise_for_required_storage_errors(result, storage_write_policy)


def _append_empty_decision_batch(writer: object | None) -> None:
    if writer is None:
        return
    append = getattr(writer, "append_decision_journal_records", None)
    if callable(append):
        append([])


def _relevant_tickers(assembled: AssembledLivePipelineInputs) -> list[str]:
    values = {event.ticker for event in assembled.upcoming_events}
    values.update(peer.ticker for peer in assembled.peer_results)
    values.update(assembled.skipped_targets)
    return sorted(values)


def _provider_error_count(
    provider_error_rows: Sequence[dict[str, Any]],
    telemetry: Sequence[ProviderCallTelemetry],
) -> int:
    return len(provider_error_rows) + sum(item.error_count for item in telemetry)


def _raise_for_required_storage_errors(result: object, storage_write_policy: object) -> None:
    errors = list(getattr(result, "errors", []))
    if errors and _storage_policy_required(storage_write_policy):
        raise_if_required = getattr(result, "raise_if_required", None)
        if callable(raise_if_required):
            raise_if_required()
        raise RuntimeError("Required storage writes failed.")


def _storage_policy_required(storage_write_policy: object) -> bool:
    value = getattr(storage_write_policy, "value", storage_write_policy)
    return str(value).lower() == "required"


def _supabase_writer(env: Mapping[str, str]) -> object:
    from prescient.storage.supabase import SupabaseStorageAdapter

    return SupabaseStorageAdapter.from_env(environ=env)


_METHOD_ENDPOINTS = {
    "get_earnings_calendar": "earnings_calendar",
    "get_company_earnings": "company_earnings",
    "get_eps_estimates": "eps_estimates",
    "get_revenue_estimates": "revenue_estimates",
    "get_stock_peers": "peers",
    "get_bulk_stock_peers": "peers",
    "get_historical_prices": "historical_prices",
    "get_news_sentiment": "news_sentiment",
    "get_company_facts": "sec_facts",
    "get_company_concept": "sec_facts",
    "get_filing_history": "sec_filings",
    "get_options_chain": "options_chain",
}

_METHOD_RESULT_MODELS: dict[str, type[BaseModel]] = {
    "get_earnings_calendar": EarningsCalendarResult,
    "get_company_earnings": CompanyEarningsResult,
    "get_eps_estimates": EarningsEstimateResult,
    "get_revenue_estimates": RevenueEstimateResult,
    "get_stock_peers": PeerListResult,
    "get_bulk_stock_peers": PeerListResult,
    "get_historical_prices": HistoricalPriceResult,
    "get_news_sentiment": NewsSentimentResult,
    "get_company_facts": CompanyFactsResult,
    "get_company_concept": CompanyFactsResult,
    "get_filing_history": FilingHistoryResult,
}


class _RuntimeProviderAdapter:
    def __init__(
        self,
        *,
        provider: str,
        inner: object,
        runtime: ProviderRuntime,
        telemetry: list[ProviderCallTelemetry],
        run_id: str,
    ) -> None:
        self._provider = provider
        self._inner = inner
        self._runtime = runtime
        self._telemetry = telemetry
        self._run_id = run_id

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr) or name not in _METHOD_ENDPOINTS:
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            endpoint = _METHOD_ENDPOINTS[name]
            model = _METHOD_RESULT_MODELS.get(name)
            result = self._runtime.call(
                provider=self._provider,
                source_endpoint=endpoint,
                source_id=_source_id(endpoint, args, kwargs),
                fetch=lambda: attr(*args, **kwargs),
                run_id=self._run_id,
                target=_target_for_call(args, kwargs),
                cache_decoder=(
                    (lambda payload: model.model_validate(payload))
                    if model is not None
                    else None
                ),
                snapshot_payload=_snapshot_payload,
            )
            self._telemetry.append(result.telemetry)
            if result.value is not None:
                return result.value
            if model is not None:
                return model.model_validate({"errors": result.errors})
            return {"errors": result.errors}

        return call


def _source_id(
    endpoint: str,
    args: Sequence[Any],
    kwargs: Mapping[str, Any],
) -> str:
    parts = [_source_part(value) for value in args]
    parts.extend(
        f"{key}={_source_part(value)}"
        for key, value in sorted(kwargs.items())
        if key != "fetched_at"
    )
    return f"{endpoint}:{'|'.join(part for part in parts if part) or 'global'}"


def _source_part(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip().upper()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return ",".join(_source_part(item) for item in value)
    if isinstance(value, Mapping):
        return ",".join(
            f"{key}={_source_part(item)}" for key, item in sorted(value.items())
        )
    if value is None:
        return ""
    return str(value)


def _target_for_call(
    args: Sequence[Any],
    kwargs: Mapping[str, Any],
) -> str | None:
    for key in ("ticker", "symbol"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    if args and isinstance(args[0], str) and args[0].strip():
        return args[0].strip().upper()
    tickers = kwargs.get("tickers")
    if isinstance(tickers, Sequence) and not isinstance(tickers, (bytes, bytearray, str)):
        normalized = [item.strip().upper() for item in tickers if isinstance(item, str)]
        if len(normalized) == 1:
            return normalized[0]
    return None


def _snapshot_payload(value: object) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": repr(value)}
