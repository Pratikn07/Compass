from __future__ import annotations

import ast
import sqlite3
from datetime import date
from pathlib import Path

from prescient.main import main
from prescient.scheduler import (
    CronRunRequest,
    CronRunStatus,
    run_cron_guarded_job,
)


def _request(
    database_path: Path,
    *,
    job_name: str = "scheduled-strategy",
    run_key: str = "2026-06-01",
) -> CronRunRequest:
    return CronRunRequest(
        job_name=job_name,
        run_key=run_key,
        scheduled_for=date(2026, 6, 1),
        database_path=database_path,
    )


def test_cron_guard_executes_first_run_and_marks_completed(tmp_path: Path) -> None:
    calls: list[str] = []

    result = run_cron_guarded_job(
        _request(tmp_path / "prescient.sqlite"),
        lambda: calls.append("called") or 0,
    )

    assert result.status == CronRunStatus.COMPLETED
    assert result.exit_code == 0
    assert calls == ["called"]


def test_cron_guard_skips_already_completed_run(tmp_path: Path) -> None:
    database_path = tmp_path / "prescient.sqlite"
    run_cron_guarded_job(_request(database_path), lambda: 0)
    calls: list[str] = []

    result = run_cron_guarded_job(
        _request(database_path),
        lambda: calls.append("called") or 0,
    )

    assert result.status == CronRunStatus.ALREADY_COMPLETED
    assert result.exit_code == 0
    assert calls == []


def test_cron_guard_skips_existing_started_run(tmp_path: Path) -> None:
    database_path = tmp_path / "prescient.sqlite"
    request = _request(database_path)
    run_cron_guarded_job(request, lambda: 0)
    _mark_started_for_test(database_path, request.job_name, request.run_key)
    calls: list[str] = []

    result = run_cron_guarded_job(
        request,
        lambda: calls.append("called") or 0,
    )

    assert result.status == CronRunStatus.ALREADY_RUNNING
    assert result.exit_code == 0
    assert calls == []


def test_cron_guard_marks_non_zero_return_failed(tmp_path: Path) -> None:
    result = run_cron_guarded_job(_request(tmp_path / "prescient.sqlite"), lambda: 7)

    assert result.status == CronRunStatus.FAILED
    assert result.exit_code == 7
    assert "non-zero" in result.message


def test_cron_guard_marks_exception_failed_with_secret_safe_message(tmp_path: Path) -> None:
    def failing_job() -> int:
        raise RuntimeError("Authorization bearer secret raw_payload leaked")

    result = run_cron_guarded_job(_request(tmp_path / "prescient.sqlite"), failing_job)

    assert result.status == CronRunStatus.FAILED
    assert result.exit_code == 1
    serialized = result.model_dump_json().lower()
    assert "authorization" not in serialized
    assert "bearer" not in serialized
    assert "secret" not in serialized
    assert "raw_payload" not in serialized


def test_scheduler_cron_source_is_bounded_and_has_no_live_dependencies() -> None:
    path = Path("src/prescient/scheduler/cron.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
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

    assert "while True" not in source
    assert "time.sleep" not in source
    assert "asyncio.sleep" not in source
    forbidden = {
        "prescient.broker",
        "prescient.data",
        "prescient.runtime.pipeline",
    }
    assert not any(
        imported == root or imported.startswith(f"{root}.")
        for imported in imports
        for root in forbidden
    )


def test_cli_scheduler_cron_guard_records_bounded_run(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "prescient.sqlite"

    exit_code = main(
        [
            "scheduler",
            "cron-guard",
            "--job-name",
            "scheduled-strategy",
            "--run-key",
            "2026-06-01",
            "--scheduled-for",
            "2026-06-01",
            "--database-path",
            str(database_path),
            "--command-label",
            "propose-only-scheduled-strategy",
        ]
    )

    assert exit_code == 0
    assert "completed" in capsys.readouterr().out.lower()
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT status, execution_mode FROM scheduler_runs WHERE job_name = ? AND run_key = ?",
            ("scheduled-strategy", "2026-06-01"),
        ).fetchone()
    assert row == ("completed", "propose_only")


def test_cli_live_data_run_uses_current_date_and_universe_path(monkeypatch, capsys) -> None:
    from prescient import live_data

    calls: list[dict[str, object]] = []

    def fake_run_live_data_pipeline(**kwargs: object) -> object:
        calls.append(kwargs)

        class _Summary:
            run_id = "scheduled:2026-06-01"
            decision_count = 1
            provider_error_count = 0
            skipped_target_count = 0
            wrote_storage = True

        return _Summary()

    monkeypatch.setattr(live_data, "run_live_data_pipeline", fake_run_live_data_pipeline)

    exit_code = main(
        [
            "live-data-run",
            "--current-date",
            "2026-06-01",
            "--universe-path",
            "config/themes.yaml",
            "--storage-write-policy",
            "required",
        ]
    )

    assert exit_code == 0
    assert calls == [
        {
            "current_date": date(2026, 6, 1),
            "universe_path": "config/themes.yaml",
            "storage_write_policy": "required",
        }
    ]
    output = capsys.readouterr().out
    assert "live-data-run: scheduled:2026-06-01" in output
    assert "decisions: 1" in output


def test_cli_live_data_run_returns_nonzero_for_secret_safe_config_error(
    monkeypatch,
    capsys,
) -> None:
    from prescient import live_data

    def fake_run_live_data_pipeline(**kwargs: object) -> object:
        raise live_data.LiveDataConfigurationError(
            "Missing mandatory live-data provider configuration: fmp"
        )

    monkeypatch.setattr(live_data, "run_live_data_pipeline", fake_run_live_data_pipeline)

    exit_code = main(["live-data-run", "--current-date", "2026-06-01"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Missing mandatory live-data provider configuration: fmp" in output
    assert "secret" not in output.lower()


def test_cli_live_data_run_returns_nonzero_for_secret_safe_storage_error(
    monkeypatch,
    capsys,
) -> None:
    from prescient import live_data
    from prescient.storage import (
        StorageConfigurationError,
        StorageError,
        StorageErrorType,
    )

    def fake_run_live_data_pipeline(**kwargs: object) -> object:
        raise StorageConfigurationError(
            StorageError(
                provider="supabase",
                error_type=StorageErrorType.MISSING_CREDENTIALS,
                message="Missing Supabase storage configuration.",
            )
        )

    monkeypatch.setattr(live_data, "run_live_data_pipeline", fake_run_live_data_pipeline)

    exit_code = main(["live-data-run", "--current-date", "2026-06-01"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Missing Supabase storage configuration." in output
    assert "service_role" not in output.lower()


def _mark_started_for_test(database_path: Path, job_name: str, run_key: str) -> int:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE scheduler_runs
            SET status = 'started', completed_at = NULL, failed_at = NULL
            WHERE job_name = ? AND run_key = ?
            """,
            (job_name, run_key),
        )
    return 0
