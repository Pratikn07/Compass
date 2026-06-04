from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


_UNSAFE_MESSAGE_PATTERN = re.compile(
    r"(authorization|bearer\b|service[_-]?role|secret|api[_-]?key|raw[_-]?payload|-----begin)",
    re.IGNORECASE,
)


class CronRunStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    ALREADY_RUNNING = "already_running"
    ALREADY_COMPLETED = "already_completed"


class CronRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_name: str
    run_key: str
    scheduled_for: date
    database_path: str | Path
    execution_mode: str = "propose_only"

    @field_validator("job_name", "run_key", "execution_mode")
    @classmethod
    def require_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Cron run text fields must not be empty.")
        return cleaned


class CronRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_name: str
    run_key: str
    status: CronRunStatus
    exit_code: int
    message: str

    @field_validator("message")
    @classmethod
    def redact_message(cls, value: str) -> str:
        if _UNSAFE_MESSAGE_PATTERN.search(value):
            return "Cron job failed; sensitive details were redacted."
        return value


def run_cron_guarded_job(
    request: CronRunRequest,
    job: Callable[[], int],
) -> CronRunResult:
    database_path = Path(request.database_path)
    _initialize_schema(database_path)

    existing_status = _existing_status(database_path, request)
    if existing_status == CronRunStatus.COMPLETED:
        return CronRunResult(
            job_name=request.job_name,
            run_key=request.run_key,
            status=CronRunStatus.ALREADY_COMPLETED,
            exit_code=0,
            message="Cron run already completed.",
        )
    if existing_status == CronRunStatus.STARTED:
        return CronRunResult(
            job_name=request.job_name,
            run_key=request.run_key,
            status=CronRunStatus.ALREADY_RUNNING,
            exit_code=0,
            message="Cron run already started.",
        )

    _mark_started(database_path, request)
    try:
        exit_code = int(job())
    except Exception as exc:
        _mark_finished(database_path, request, CronRunStatus.FAILED, 1, str(exc))
        return CronRunResult(
            job_name=request.job_name,
            run_key=request.run_key,
            status=CronRunStatus.FAILED,
            exit_code=1,
            message=str(exc),
        )

    if exit_code == 0:
        _mark_finished(
            database_path,
            request,
            CronRunStatus.COMPLETED,
            0,
            "Cron run completed.",
        )
        return CronRunResult(
            job_name=request.job_name,
            run_key=request.run_key,
            status=CronRunStatus.COMPLETED,
            exit_code=0,
            message="Cron run completed.",
        )

    message = f"Cron job returned non-zero exit code {exit_code}."
    _mark_finished(database_path, request, CronRunStatus.FAILED, exit_code, message)
    return CronRunResult(
        job_name=request.job_name,
        run_key=request.run_key,
        status=CronRunStatus.FAILED,
        exit_code=exit_code,
        message=message,
    )


def _initialize_schema(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_runs (
                job_name TEXT NOT NULL,
                run_key TEXT NOT NULL,
                scheduled_for TEXT NOT NULL,
                execution_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                failed_at TEXT,
                exit_code INTEGER,
                message TEXT NOT NULL,
                PRIMARY KEY (job_name, run_key)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status
            ON scheduler_runs (status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scheduler_runs_scheduled_for
            ON scheduler_runs (scheduled_for)
            """
        )


def _existing_status(
    database_path: Path,
    request: CronRunRequest,
) -> CronRunStatus | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT status FROM scheduler_runs
            WHERE job_name = ? AND run_key = ?
            """,
            (request.job_name, request.run_key),
        ).fetchone()
    if row is None:
        return None
    return CronRunStatus(row[0])


def _mark_started(database_path: Path, request: CronRunRequest) -> None:
    now = _utc_now()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO scheduler_runs (
                job_name,
                run_key,
                scheduled_for,
                execution_mode,
                status,
                started_at,
                completed_at,
                failed_at,
                exit_code,
                message
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
            ON CONFLICT(job_name, run_key) DO UPDATE SET
                scheduled_for = excluded.scheduled_for,
                execution_mode = excluded.execution_mode,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = NULL,
                failed_at = NULL,
                exit_code = NULL,
                message = excluded.message
            """,
            (
                request.job_name,
                request.run_key,
                request.scheduled_for.isoformat(),
                request.execution_mode,
                CronRunStatus.STARTED.value,
                now,
                "Cron run started.",
            ),
        )


def _mark_finished(
    database_path: Path,
    request: CronRunRequest,
    status: CronRunStatus,
    exit_code: int,
    message: str,
) -> None:
    now = _utc_now()
    completed_at = now if status == CronRunStatus.COMPLETED else None
    failed_at = now if status == CronRunStatus.FAILED else None
    safe_message = CronRunResult(
        job_name=request.job_name,
        run_key=request.run_key,
        status=status,
        exit_code=exit_code,
        message=message,
    ).message
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE scheduler_runs
            SET status = ?,
                completed_at = ?,
                failed_at = ?,
                exit_code = ?,
                message = ?
            WHERE job_name = ? AND run_key = ?
            """,
            (
                status.value,
                completed_at,
                failed_at,
                exit_code,
                safe_message,
                request.job_name,
                request.run_key,
            ),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
