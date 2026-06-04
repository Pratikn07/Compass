from __future__ import annotations

import ast
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pytest

from prescient.runtime import run_hot_cold_strategy_pipeline
from prescient.runtime.models import DecisionJournalRecord
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    SignalValue,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)
from prescient.storage import (
    StorageError,
    StorageErrorType,
    StorageWritePolicy,
    StorageWriteRequiredError,
    StorageWriteResult,
)


class RecordingStorageWriter:
    def __init__(self, result: StorageWriteResult | None = None) -> None:
        self.result = result or StorageWriteResult(records_written=0)
        self.calls: list[list[DecisionJournalRecord]] = []

    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        batch = list(records)
        self.calls.append(batch)
        if self.result.errors:
            return self.result
        return StorageWriteResult(records_written=len(batch))


def test_runtime_writes_normalized_journal_records_to_optional_storage_writer() -> None:
    writer = RecordingStorageWriter()

    result = _run_pipeline(storage_writer=writer)

    stored_records = [record for batch in writer.calls for record in batch]
    assert result.storage_errors == []
    assert [record.record_type.value for record in stored_records] == [
        "strategy_decision",
        "analyst_review",
    ]
    assert stored_records[0].target == "NTNX"
    assert stored_records[0].theme == "AI_STORAGE"


def test_runtime_collects_optional_storage_errors_without_blocking_pipeline() -> None:
    storage_error = StorageError(
        provider="supabase",
        error_type=StorageErrorType.RATE_LIMITED,
        message="429 Too Many Requests",
    )
    writer = RecordingStorageWriter(StorageWriteResult(errors=[storage_error]))

    result = _run_pipeline(storage_writer=writer)

    assert len(result.strategy_decisions) == 1
    assert result.storage_errors == [storage_error]


def test_runtime_required_storage_policy_fails_closed_on_write_error() -> None:
    storage_error = StorageError(
        provider="supabase",
        error_type=StorageErrorType.UNAVAILABLE,
        message="503 provider unavailable",
    )
    writer = RecordingStorageWriter(StorageWriteResult(errors=[storage_error]))

    with pytest.raises(StorageWriteRequiredError):
        _run_pipeline(
            storage_writer=writer,
            storage_write_policy=StorageWritePolicy.REQUIRED,
        )


def test_deterministic_layers_do_not_import_concrete_storage_adapters() -> None:
    deterministic_roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/runtime"),
        Path("src/prescient/analyst"),
        Path("src/prescient/data"),
    ]
    forbidden_imports = {
        "prescient.storage.sqlite",
        "prescient.storage.supabase",
        "sqlite3",
    }

    for root in deterministic_roots:
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            imports.extend(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )

            assert not any(
                imported == forbidden or imported.startswith(f"{forbidden}.")
                for imported in imports
                for forbidden in forbidden_imports
            ), f"{path} imports a concrete storage adapter: {imports}"


def _run_pipeline(
    *,
    storage_writer: RecordingStorageWriter,
    storage_write_policy: StorageWritePolicy = StorageWritePolicy.OPTIONAL,
):
    return run_hot_cold_strategy_pipeline(
        universe=StrategyUniverse(
            themes=[
                ThemeConfig(
                    name="AI_STORAGE",
                    tickers=["NTNX", "NTAP", "PSTG", "WDC"],
                    drivers=["AI data center demand"],
                )
            ]
        ),
        upcoming_events=[
            EarningsCalendarEvent(
                ticker="NTNX",
                earnings_date=date(2026, 6, 2),
                report_time="AMC",
            )
        ],
        peer_results=[
            _peer_result("NTAP"),
            _peer_result("PSTG"),
            _peer_result("WDC"),
        ],
        target_market_data={
            "NTNX": TargetMarketData(
                ticker="NTNX",
                avg_daily_volume=2_000_000,
                pre_earnings_runup_pct=4.0,
            )
        },
        options_chains={
            "NTNX": [
                OptionContractSnapshot(
                    ticker="NTNX",
                    option_type="CALL",
                    expiration_date=date(2026, 6, 12),
                    bid=4.85,
                    ask=5.15,
                    open_interest=250,
                )
            ]
        },
        current_date=date(2026, 6, 1),
        storage_writer=storage_writer,
        storage_write_policy=storage_write_policy,
    )


def _peer_result(
    ticker: str,
    *,
    guidance_signal: SignalValue = "positive",
    theme_driver_signal: SignalValue = "positive",
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2026, 5, 20),
            report_time="AMC",
            eps_estimate=1.0,
            eps_actual=1.2,
            revenue_estimate=1_000.0,
            revenue_actual=1_100.0,
        ),
        price_reaction_pct=4.0,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )
