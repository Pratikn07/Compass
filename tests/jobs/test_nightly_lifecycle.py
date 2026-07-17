from __future__ import annotations

from datetime import date

from compass.jobs.nightly import StepResult, run_nightly


class JobRepository:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.runs: dict[str, dict] = {}
        self.errors: dict[str, dict] = {}
        self.audits: dict[str, dict] = {}
        self.health: dict[str, dict] = {}
        self.reports: dict[str, dict] = {}

    def start_run(self, row: dict) -> dict:
        if self.fail_start:
            raise RuntimeError("database unavailable")
        self.runs[row["run_id"]] = dict(row)
        return self.runs[row["run_id"]]

    def finish_run(self, run_id: str, *, status: str, payload: dict) -> dict:
        self.runs[run_id].update(status=status, payload=payload)
        return self.runs[run_id]

    def record_provider_error(self, row: dict) -> dict:
        self.errors[row["provider_error_id"]] = dict(row)
        return row

    def record_storage_audit(self, row: dict) -> dict:
        self.audits[row["storage_write_audit_id"]] = dict(row)
        return row

    def record_system_health(self, row: dict) -> dict:
        self.health[row["system_health_id"]] = dict(row)
        return row

    def persist_learning_report(self, row: dict) -> dict:
        self.reports[row["learning_report_id"]] = dict(row)
        return row


def successful_step(_run_id: str, _trading_date: date) -> StepResult:
    return StepResult(provider="yahoo", table_name="price_bars", written_record_count=12)


def failing_step(_run_id: str, _trading_date: date) -> StepResult:
    raise RuntimeError("provider secret must stay hidden")


def test_duplicate_nightly_runs_are_idempotent() -> None:
    repository = JobRepository()

    first = run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 16),
        steps=[successful_step],
    )
    second = run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 16),
        steps=[successful_step],
    )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert len(repository.runs) == 1
    assert len(repository.audits) == 1
    assert len(repository.health) == 1


def test_one_provider_failure_yields_partial_and_sanitized_error() -> None:
    repository = JobRepository()

    result = run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 16),
        steps=[successful_step, failing_step],
    )

    assert result.status == "partial"
    assert len(repository.errors) == 1
    error = next(iter(repository.errors.values()))
    assert error["provider"] == "failing_step"
    assert "secret" not in error["message"]


def test_database_start_failure_returns_failed_without_running_steps() -> None:
    repository = JobRepository(fail_start=True)
    called = False

    def should_not_run(_run_id: str, _trading_date: date) -> StepResult:
        nonlocal called
        called = True
        return successful_step(_run_id, _trading_date)

    result = run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 16),
        steps=[should_not_run],
    )

    assert result.status == "failed"
    assert called is False


def test_friday_run_persists_one_learning_report() -> None:
    repository = JobRepository()

    def backtest(_run_id: str, _trading_date: date) -> dict:
        return {"scorecards": {"reaction_aware_peer": {"survived": False}}}

    run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 17),
        steps=[successful_step],
        weekly_backtest=backtest,
    )
    run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 17),
        steps=[successful_step],
        weekly_backtest=backtest,
    )

    assert len(repository.reports) == 1
    report = next(iter(repository.reports.values()))
    assert report["report_type"] == "edge_backtest"
    assert report["report_date"] == "2026-07-17"


def test_non_friday_run_does_not_generate_weekly_report() -> None:
    repository = JobRepository()
    called = False

    def backtest(_run_id: str, _trading_date: date) -> dict:
        nonlocal called
        called = True
        return {}

    run_nightly(
        repository=repository,
        trading_date=date(2026, 7, 16),
        steps=[successful_step],
        weekly_backtest=backtest,
    )

    assert called is False
    assert repository.reports == {}
