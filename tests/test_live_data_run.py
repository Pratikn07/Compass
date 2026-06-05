from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from pytest import MonkeyPatch

from prescient.data import DataProvider, DataProviderError, DataProviderErrorType
from prescient.data.models import (
    EarningsCalendarResult,
    PeerListResult,
    PeerListSnapshot,
)
from prescient.live_data import AssembledLivePipelineInputs, run_live_data_pipeline
from prescient.seed.inputs import build_seed_inputs
from prescient.storage import ProviderSnapshotRecord, StorageWriteResult


class _FakeStorageWriter:
    def __init__(self) -> None:
        self.appended_batches: list[list[Any]] = []
        self.run_status_rows: list[dict[str, Any]] = []
        self.provider_snapshots: list[dict[str, Any]] = []
        self.provider_errors: list[dict[str, Any]] = []
        self.system_health_rows: list[dict[str, Any]] = []
        self.snapshots_by_source: dict[tuple[str, str], ProviderSnapshotRecord] = {}

    def append_decision_journal_records(self, records: Any) -> StorageWriteResult:
        batch = list(records)
        self.appended_batches.append(batch)
        return StorageWriteResult(records_written=len(batch))

    def upsert_run_status(self, record: Any) -> StorageWriteResult:
        self.run_status_rows.append(record.to_row())
        return StorageWriteResult(records_written=1)

    def append_provider_snapshots(self, snapshots: Any) -> StorageWriteResult:
        rows = [_row(snapshot) for snapshot in snapshots]
        self.provider_snapshots.extend(rows)
        return StorageWriteResult(records_written=len(rows))

    def append_provider_errors(self, errors: Any) -> StorageWriteResult:
        rows = [_row(error) for error in errors]
        self.provider_errors.extend(rows)
        return StorageWriteResult(records_written=len(rows))

    def upsert_system_health(self, records: Any) -> StorageWriteResult:
        rows = [_row(record) for record in records]
        self.system_health_rows.extend(rows)
        return StorageWriteResult(records_written=len(rows))

    def read_provider_snapshot(
        self,
        *,
        provider: str,
        source_id: str,
    ) -> ProviderSnapshotRecord | None:
        return self.snapshots_by_source.get((provider, source_id))


class _FailingFinnhub:
    def __init__(self) -> None:
        self.calls = 0

    def get_earnings_calendar(self, *_: Any, **__: Any) -> EarningsCalendarResult:
        self.calls += 1
        return EarningsCalendarResult(
            snapshots=[],
            errors=[
                DataProviderError(
                    provider=DataProvider.FINNHUB,
                    error_type=DataProviderErrorType.RATE_LIMITED,
                    message="Finnhub request was rate limited.",
                    endpoint="earnings_calendar",
                    symbol="NTNX",
                )
            ],
        )


class _ExplodingFinnhub:
    def __init__(self) -> None:
        self.calls = 0

    def get_earnings_calendar(self, *_: Any, **__: Any) -> EarningsCalendarResult:
        self.calls += 1
        raise AssertionError("cache hit should avoid provider call")


class _SuccessfulFmp:
    def get_stock_peers(self, ticker: str, **_: Any) -> PeerListResult:
        return PeerListResult(
            snapshots=[
                PeerListSnapshot(
                    ticker=ticker,
                    peers=["NTAP", "PSTG"],
                    provider=DataProvider.FMP,
                    source_endpoint="peers",
                )
            ],
            errors=[],
        )


def test_live_data_runtime_degrades_provider_health_without_crashing(
    monkeypatch: MonkeyPatch,
) -> None:
    writer = _FakeStorageWriter()
    finnhub = _FailingFinnhub()
    monkeypatch.setattr(
        "prescient.live_data.run._build_provider_adapters",
        lambda config: {
            "finnhub": finnhub,
            "fmp": _SuccessfulFmp(),
            "alphavantage": None,
            "sec_edgar": None,
        },
    )

    summary = run_live_data_pipeline(
        current_date=date(2026, 6, 1),
        storage_writer=writer,
        assembler=_assembler_that_calls_finnhub_and_fmp,
        env={"FINNHUB_API_KEY": "fk", "FMP_API_KEY": "fmpk"},
    )

    assert summary.decision_count == 1
    assert summary.provider_error_count == 1
    assert writer.system_health_rows[0]["component"] == "provider_health"
    assert writer.system_health_rows[0]["status"] == "degraded"
    assert writer.system_health_rows[0]["payload"]["providers"]["finnhub"]["errors"] == 1
    assert writer.system_health_rows[0]["payload"]["providers"]["fmp"]["requests"] == 1
    assert writer.provider_errors[0]["message"] == "Finnhub request was rate limited."
    assert finnhub.calls == 1


def test_live_data_runtime_records_blocked_provider_health_for_all_provider_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    writer = _FakeStorageWriter()
    monkeypatch.setattr(
        "prescient.live_data.run._build_provider_adapters",
        lambda config: {
            "finnhub": _FailingFinnhub(),
            "fmp": None,
            "alphavantage": None,
            "sec_edgar": None,
        },
    )

    summary = run_live_data_pipeline(
        current_date=date(2026, 6, 1),
        storage_writer=writer,
        assembler=_assembler_that_calls_finnhub,
        env={"FINNHUB_API_KEY": "fk", "FMP_API_KEY": "fmpk"},
    )

    assert summary.decision_count == 1
    assert summary.provider_error_count == 1
    assert writer.system_health_rows[0]["status"] == "blocked"
    assert writer.system_health_rows[0]["detail"] == "All provider calls failed or were skipped."


def test_live_data_runtime_cache_hit_keeps_provider_call_bounded(
    monkeypatch: MonkeyPatch,
) -> None:
    writer = _FakeStorageWriter()
    cached = EarningsCalendarResult(snapshots=[], errors=[])
    source_id = "earnings_calendar:2026-06-01|2026-06-15|tickers=NTNX"
    writer.snapshots_by_source[("finnhub", source_id)] = ProviderSnapshotRecord(
        provider="finnhub",
        source_endpoint="earnings_calendar",
        source_id=source_id,
        retrieved_at=datetime.now(timezone.utc),
        payload=cached.model_dump(mode="json"),
    )
    finnhub = _ExplodingFinnhub()
    monkeypatch.setattr(
        "prescient.live_data.run._build_provider_adapters",
        lambda config: {
            "finnhub": finnhub,
            "fmp": None,
            "alphavantage": None,
            "sec_edgar": None,
        },
    )

    summary = run_live_data_pipeline(
        current_date=date(2026, 6, 1),
        storage_writer=writer,
        assembler=_assembler_that_calls_finnhub,
        env={"FINNHUB_API_KEY": "fk", "FMP_API_KEY": "fmpk"},
    )

    assert summary.provider_error_count == 0
    assert finnhub.calls == 0
    assert writer.provider_snapshots == []
    assert writer.system_health_rows[0]["status"] == "healthy"
    assert writer.system_health_rows[0]["payload"]["providers"]["finnhub"]["cache_hits"] == 1


def _assembler_that_calls_finnhub(**kwargs: Any) -> AssembledLivePipelineInputs:
    kwargs["provider_adapters"]["finnhub"].get_earnings_calendar(
        date(2026, 6, 1),
        date(2026, 6, 15),
        tickers=["NTNX"],
    )
    return _assembled_inputs(current_date=kwargs["current_date"])


def _assembler_that_calls_finnhub_and_fmp(**kwargs: Any) -> AssembledLivePipelineInputs:
    kwargs["provider_adapters"]["finnhub"].get_earnings_calendar(
        date(2026, 6, 1),
        date(2026, 6, 15),
        tickers=["NTNX"],
    )
    kwargs["provider_adapters"]["fmp"].get_stock_peers("NTNX")
    return _assembled_inputs(current_date=kwargs["current_date"])


def _assembled_inputs(*, current_date: date) -> AssembledLivePipelineInputs:
    seed = build_seed_inputs(current_date=current_date)
    return AssembledLivePipelineInputs(
        universe=seed.universe,
        upcoming_events=seed.upcoming_events,
        peer_results=seed.peer_results,
        target_market_data=seed.target_market_data,
        options_chains=seed.options_chains,
        indicator_snapshots=None,
        provider_snapshots=[],
        provider_errors=[],
        skipped_targets=[],
    )


def _row(value: Any) -> dict[str, Any]:
    to_row = getattr(value, "to_row", None)
    if callable(to_row):
        return to_row()
    return dict(value)


def test_default_live_assembler_bridges_adapters_to_live_inputs() -> None:
    from datetime import date

    from prescient.live_data.run import default_live_assembler
    from prescient.signal.models import (
        OptionContractSnapshot,
        StrategySettings,
        StrategyUniverse,
        ThemeConfig,
    )
    from prescient.data.config import ProviderConfig

    # Minimal fake adapters matching Phase B provider protocols.
    class FakeEarnings:
        def get_earnings_calendar(self, date_from, date_to, tickers=None, fetched_at=None):
            from prescient.data.models import (
                EarningsCalendarResult,
                EarningsCalendarSnapshot,
            )
            return EarningsCalendarResult(
                snapshots=[
                    EarningsCalendarSnapshot(
                        ticker="NVDA",
                        earnings_date=date(2026, 6, 12),
                        report_time="AMC",
                        provider="finnhub",
                        source_endpoint="earnings_calendar",
                    )
                ],
                errors=[],
            )

    class FakeMarket:
        def get_historical_prices(self, ticker, date_from, date_to, fetched_at=None):
            from prescient.data.models import HistoricalPriceResult
            return HistoricalPriceResult(candles=[], errors=[])

    class FakeOptions:
        def get_option_chain_snapshots(self, *, underlying_symbol, earnings_date,
                                       max_expiration_date, feed="indicative", fetched_at=None):
            return [
                OptionContractSnapshot(
                    ticker=underlying_symbol, option_type="CALL",
                    expiration_date=date(2026, 6, 12), bid=5.0, ask=5.2,
                    open_interest=100,
                )
            ]

    universe = StrategyUniverse(
        themes=[ThemeConfig(name="AI", tickers=["NVDA", "AMD"], drivers=["AI demand"])]
    )
    out = default_live_assembler(
        run_id="scheduled:2026-06-01",
        universe=universe,
        current_date=date(2026, 6, 1),
        provider_config=ProviderConfig(),
        provider_adapters={
            "finnhub": FakeEarnings(),
            "fmp_market_data": FakeMarket(),
            "fmp": None,
            "alphavantage": None,
            "alpaca": FakeOptions(),
        },
        settings=StrategySettings(earnings_window_days=14, peer_result_window_days=21),
    )

    assert [e.ticker for e in out.upcoming_events] == ["NVDA"]
    assert out.options_chains["NVDA"][0].bid == 5.0
