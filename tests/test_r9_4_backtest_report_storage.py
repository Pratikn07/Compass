from __future__ import annotations

from datetime import date
from typing import Any

from prescient.backtest import (
    BacktestOutcome,
    BacktestRunRequest,
    BacktestRunResult,
    BacktestSetupResult,
    BacktestSummary,
    BacktestTradeExpression,
    TradePnlOutcome,
)
from prescient.backtest.reports import (
    BACKTEST_LEARNING_REPORT_TYPE,
    backtest_result_to_learning_report_row,
)
from prescient.storage.supabase import SupabaseStorageAdapter


def test_backtest_result_maps_to_learning_report_row() -> None:
    result = _backtest_result()

    row = backtest_result_to_learning_report_row(
        result,
        report_date=date(2026, 6, 4),
        target="ntnx",
        theme="ai_storage",
    )

    assert row["learning_report_id"] == "backtest:r9-4-fixture"
    assert row["run_id"] == "r9-4-fixture"
    assert row["report_date"] == "2026-06-04"
    assert row["target"] == "NTNX"
    assert row["theme"] == "AI_STORAGE"
    assert row["report_type"] == BACKTEST_LEARNING_REPORT_TYPE
    assert row["schema_version"] == 1
    assert row["payload"]["run_id"] == "r9-4-fixture"
    assert row["payload"]["summary"]["win_rate"] == 1.0
    assert row["payload"]["summary"]["beats_buy_and_hold"] is True


def test_supabase_adapter_upserts_learning_report_rows() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")
    row = backtest_result_to_learning_report_row(
        _backtest_result(),
        report_date=date(2026, 6, 4),
    )

    result = adapter.append_learning_reports([row])

    assert result.ok is True
    assert result.records_written == 1
    assert fake_client.schema_name == "prescient_storage"
    assert fake_client.table_name == "learning_reports"
    assert fake_client.on_conflict == "learning_report_id"
    assert fake_client.rows[0]["learning_report_id"] == "backtest:r9-4-fixture"
    assert fake_client.rows[0]["report_type"] == "backtest"


def test_supabase_adapter_skips_empty_learning_report_batch() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    result = adapter.append_learning_reports([])

    assert result.ok is True
    assert result.records_written == 0
    assert fake_client.table_name is None


def _backtest_result() -> BacktestRunResult:
    request = BacktestRunRequest(
        run_id="r9-4-fixture",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        starting_equity=10_000.0,
    )
    setup = BacktestSetupResult(
        setup_id="setup-1",
        ticker="ntnx",
        target="ntnx",
        theme="ai_storage",
        entry_date=date(2026, 2, 1),
        exit_date=date(2026, 2, 2),
        strategy_status="candidate_ready_for_analyst",
        expression=BacktestTradeExpression.CALL_OPTION,
        recommended_expression=BacktestTradeExpression.CALL_OPTION,
        allocated_capital=120.0,
        underlying_entry_price=50.0,
        underlying_exit_price=52.0,
        trade_pnl=TradePnlOutcome(
            ticker="ntnx",
            expression=BacktestTradeExpression.CALL_OPTION,
            quantity=1,
            entry_price=1.2,
            exit_price=1.9,
            gross_pnl=70.0,
            net_pnl=70.0,
            outcome=BacktestOutcome.WIN,
        ),
    )
    return BacktestRunResult(
        run_id="r9-4-fixture",
        request=request,
        setups=[setup],
        summary=BacktestSummary.from_setups([setup], request=request),
    )


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.schema_name: str | None = None
        self.table_name: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.on_conflict: str | None = None

    def schema(self, schema_name: str) -> "FakeSupabaseClient":
        self.schema_name = schema_name
        return self

    def table(self, table_name: str) -> "FakeSupabaseClient":
        self.table_name = table_name
        return self

    def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
        ignore_duplicates: bool = False,
    ) -> "FakeSupabaseClient":
        assert ignore_duplicates is False
        self.rows = rows
        self.on_conflict = on_conflict
        return self

    def execute(self) -> object:
        return type("FakeResponse", (), {"data": self.rows, "error": None})()
