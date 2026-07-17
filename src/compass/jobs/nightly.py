from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol


@dataclass(frozen=True)
class StepResult:
    provider: str
    table_name: str
    written_record_count: int
    attempted_record_count: int | None = None
    error_count: int = 0
    payload: dict | None = None


@dataclass(frozen=True)
class NightlyRunResult:
    run_id: str
    status: str
    succeeded_steps: int
    failed_steps: int


class NightlyRepository(Protocol):
    def start_run(self, row: dict) -> dict: ...

    def finish_run(self, run_id: str, *, status: str, payload: dict) -> dict: ...

    def record_provider_error(self, row: dict) -> dict: ...

    def record_storage_audit(self, row: dict) -> dict: ...

    def record_system_health(self, row: dict) -> dict: ...

    def persist_learning_report(self, row: dict) -> dict: ...


NightlyStep = Callable[[str, date], StepResult]
WeeklyBacktest = Callable[[str, date], dict]


def _step_name(step: NightlyStep) -> str:
    return getattr(step, "__name__", step.__class__.__name__)


def _failed_result(run_id: str) -> NightlyRunResult:
    return NightlyRunResult(
        run_id=run_id,
        status="failed",
        succeeded_steps=0,
        failed_steps=1,
    )


def run_nightly(
    *,
    repository: NightlyRepository,
    trading_date: date,
    steps: Sequence[NightlyStep],
    weekly_backtest: WeeklyBacktest | None = None,
    trigger_type: str = "scheduled",
) -> NightlyRunResult:
    run_id = f"nightly:{trading_date.isoformat()}"
    try:
        repository.start_run(
            {
                "run_id": run_id,
                "run_type": "nightly",
                "trigger_type": trigger_type,
                "scheduled_date": trading_date.isoformat(),
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "payload": {},
            }
        )
    except Exception:
        return _failed_result(run_id)

    succeeded = 0
    failed = 0
    for step in steps:
        name = _step_name(step)
        try:
            outcome = step(run_id, trading_date)
            repository.record_storage_audit(
                {
                    "storage_write_audit_id": f"audit:{run_id}:{name}",
                    "provider": outcome.provider,
                    "table_name": outcome.table_name,
                    "run_id": run_id,
                    "attempted_record_count": (
                        outcome.attempted_record_count
                        if outcome.attempted_record_count is not None
                        else outcome.written_record_count
                    ),
                    "written_record_count": outcome.written_record_count,
                    "error_count": outcome.error_count,
                    "payload": outcome.payload or {},
                }
            )
            repository.record_system_health(
                {
                    "system_health_id": f"health:{run_id}:{name}",
                    "component": "provider_health",
                    "status": "degraded" if outcome.error_count else "healthy",
                    "detail": (
                        f"{name} completed with provider errors"
                        if outcome.error_count
                        else f"{name} completed"
                    ),
                    "run_id": run_id,
                    "payload": {"provider": outcome.provider},
                }
            )
            succeeded += 1
            if outcome.error_count:
                repository.record_provider_error(
                    {
                        "provider_error_id": f"error:{run_id}:{name}",
                        "provider": outcome.provider,
                        "error_type": "PartialProviderFailure",
                        "run_id": run_id,
                        "source": "nightly",
                        "message": "Provider returned partial data; inspect Railway logs.",
                        "payload": {"error_count": outcome.error_count},
                    }
                )
                failed += 1
        except Exception as error:
            repository.record_provider_error(
                {
                    "provider_error_id": f"error:{run_id}:{name}",
                    "provider": name,
                    "error_type": error.__class__.__name__,
                    "run_id": run_id,
                    "source": "nightly",
                    "message": "Provider step failed; inspect Railway logs for details.",
                    "payload": {},
                }
            )
            repository.record_system_health(
                {
                    "system_health_id": f"health:{run_id}:{name}",
                    "component": "provider_health",
                    "status": "degraded",
                    "detail": f"{name} failed",
                    "run_id": run_id,
                    "payload": {},
                }
            )
            failed += 1

    if trading_date.weekday() == 4 and weekly_backtest is not None:
        try:
            report_payload = weekly_backtest(run_id, trading_date)
            repository.persist_learning_report(
                {
                    "learning_report_id": f"edge-backtest:{trading_date.isoformat()}",
                    "run_id": run_id,
                    "report_date": trading_date.isoformat(),
                    "report_type": "edge_backtest",
                    "payload": report_payload,
                }
            )
            repository.record_system_health(
                {
                    "system_health_id": f"health:{run_id}:backtest",
                    "component": "backtest_engine",
                    "status": "healthy",
                    "detail": "Weekly edge backtest completed",
                    "run_id": run_id,
                    "payload": {},
                }
            )
            succeeded += 1
        except Exception as error:
            repository.record_provider_error(
                {
                    "provider_error_id": f"error:{run_id}:backtest",
                    "provider": "backtest_engine",
                    "error_type": error.__class__.__name__,
                    "run_id": run_id,
                    "source": "nightly",
                    "message": "Weekly backtest failed; inspect Railway logs for details.",
                    "payload": {},
                }
            )
            failed += 1

    status = "succeeded"
    if failed and succeeded:
        status = "partial"
    elif failed:
        status = "failed"

    payload = {"succeeded_steps": succeeded, "failed_steps": failed}
    try:
        repository.finish_run(run_id, status=status, payload=payload)
    except Exception:
        return NightlyRunResult(
            run_id=run_id,
            status="failed",
            succeeded_steps=succeeded,
            failed_steps=failed + 1,
        )
    return NightlyRunResult(
        run_id=run_id,
        status=status,
        succeeded_steps=succeeded,
        failed_steps=failed,
    )
