from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from prescient.learning.analyzer import analyze_learning_records
from prescient.learning.journal_reader import LocalJsonlLearningJournalReader
from prescient.learning.models import (
    DEFAULT_LEARNABLE_PARAMETERS,
    LearnableParameterPolicy,
    LearningJournalReader,
    LearningJournalRecord,
    LearningMode,
    LearningRecordType,
    LearningRunReport,
    LearningRunRequest,
)
from prescient.learning.overlay import write_learning_overlay
from prescient.learning.tuner import generate_parameter_proposals


def run_morning_learning_loop(
    request: LearningRunRequest,
    *,
    reader: LearningJournalReader | None = None,
    settings_snapshot: Mapping[str, Any] | None = None,
    policies: Sequence[LearnableParameterPolicy] = DEFAULT_LEARNABLE_PARAMETERS,
    created_at: datetime | None = None,
) -> LearningRunReport:
    effective_created_at = created_at or datetime.now()
    _refuse_duplicate_run_id(request)

    active_reader = reader or LocalJsonlLearningJournalReader()
    read_result = active_reader.read_records(
        start_date=request.lookback_start,
        end_date=request.lookback_end,
        paths=request.journal_paths,
    )

    loaded_settings, settings_warnings = _load_settings_snapshot(
        request=request,
        settings_snapshot=settings_snapshot,
    )

    analysis = analyze_learning_records(read_result.records)
    fail_closed = _should_fail_closed(request, read_result, loaded_settings)
    proposals = generate_parameter_proposals(
        analysis=analysis,
        settings_snapshot=loaded_settings,
        policies=policies,
        mode=request.mode,
        execution_mode=request.execution_mode,
        fail_closed=fail_closed,
    )

    warnings = [
        *read_result.warnings,
        *settings_warnings,
        *analysis.warnings,
    ]
    if read_result.malformed_record_count > request.malformed_record_tolerance:
        warnings.append("malformed record tolerance exceeded; no settings were applied")
    if not read_result.records:
        warnings.append("no usable learning records were available; no settings were applied")
    if request.mode == LearningMode.AUTO_APPLY_SAFE and request.execution_mode == "live":
        warnings.append("live mode blocks auto-apply safe learning changes")

    overlay_path = None
    if request.mode in {LearningMode.SHADOW_OVERLAY, LearningMode.AUTO_APPLY_SAFE}:
        if request.overlay_output_path is not None:
            overlay_path = write_learning_overlay(
                path=request.overlay_output_path,
                run_id=request.run_id,
                effective_date=request.run_date,
                mode=request.mode,
                proposals=proposals,
            )
        else:
            warnings.append("overlay mode requested without overlay_output_path")

    report = LearningRunReport(
        run_id=request.run_id,
        run_date=request.run_date,
        prior_trading_date=request.prior_trading_date,
        lookback_start=request.lookback_start,
        lookback_end=request.lookback_end,
        created_at=effective_created_at,
        mode=request.mode,
        records_read=read_result.records_read,
        records_skipped=read_result.records_skipped,
        malformed_record_count=read_result.malformed_record_count,
        evaluated_decision_count=analysis.evaluated_decision_count,
        closed_outcome_count=analysis.closed_outcome_count,
        win_count=analysis.win_count,
        loss_count=analysis.loss_count,
        flat_count=analysis.flat_count,
        unknown_outcome_count=analysis.unknown_outcome_count,
        proposals=proposals,
        operational_recommendations=analysis.operational_recommendations,
        warnings=warnings,
        settings_overlay_path=overlay_path,
        candidate_ready_count=analysis.candidate_ready_count,
        executed_count=analysis.executed_count,
        average_realized_pnl=analysis.average_realized_pnl,
        median_realized_pnl=analysis.median_realized_pnl,
        win_rate=analysis.win_rate,
        average_win=analysis.average_win,
        average_loss=analysis.average_loss,
        payoff_ratio=analysis.payoff_ratio,
        largest_loss=analysis.largest_loss,
        decision_to_execution_dropoff_count=analysis.decision_to_execution_dropoff_count,
        rejection_counts=analysis.rejection_counts,
        data_provider_error_counts=analysis.data_provider_error_counts,
        excluded_from_tuning=analysis.excluded_from_tuning,
    )

    if request.journal_output_path is not None:
        _append_learning_report(report, request.journal_output_path)

    return report


def _load_settings_snapshot(
    *,
    request: LearningRunRequest,
    settings_snapshot: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], list[str]]:
    if settings_snapshot is not None:
        return settings_snapshot, []

    if request.settings_snapshot_path is None:
        return {}, ["settings snapshot was not provided"]

    path = Path(request.settings_snapshot_path)
    if not path.exists():
        return {}, [f"settings snapshot file missing: {path}"]

    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
        return {}, [f"settings snapshot file could not be parsed: {path.name}"]

    if not isinstance(loaded, Mapping):
        return {}, [f"settings snapshot file did not contain an object: {path.name}"]

    return loaded, []


def _should_fail_closed(
    request: LearningRunRequest,
    read_result: Any,
    settings_snapshot: Mapping[str, Any],
) -> bool:
    if read_result.malformed_record_count > request.malformed_record_tolerance:
        return True
    if not read_result.records:
        return True
    if not settings_snapshot:
        return True
    return False


def _refuse_duplicate_run_id(request: LearningRunRequest) -> None:
    if request.allow_overwrite or request.journal_output_path is None:
        return

    path = Path(request.journal_output_path)
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as journal_file:
        for line in journal_file:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                payload.get("record_type") == LearningRecordType.LEARNING_REPORT.value
                and payload.get("run_id") == request.run_id
            ):
                raise ValueError(f"Learning run ID already exists: {request.run_id}")


def _append_learning_report(report: LearningRunReport, path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    record = LearningJournalRecord(
        record_type=LearningRecordType.LEARNING_REPORT,
        run_id=report.run_id,
        trading_date=report.run_date,
        created_at=report.created_at,
        payload=report.model_dump(mode="json"),
    )
    with output_path.open("a", encoding="utf-8") as journal_file:
        journal_file.write(record.model_dump_json())
        journal_file.write("\n")
