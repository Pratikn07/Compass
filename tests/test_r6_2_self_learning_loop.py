from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from prescient.learning import (
    LearnableParameterPolicy,
    LearningJournalRecord,
    LearningMode,
    LearningRecordType,
    LearningRunRequest,
    LocalJsonlLearningJournalReader,
    ParameterProposalReason,
    ParameterProposalStatus,
    run_morning_learning_loop,
)


def _request(
    *,
    mode: LearningMode = LearningMode.REPORT_ONLY,
    journal_path: Path,
    overlay_path: Path | None = None,
    journal_output_path: Path | None = None,
    execution_mode: str = "paper",
    run_id: str = "learn-2026-06-03",
) -> LearningRunRequest:
    return LearningRunRequest(
        run_id=run_id,
        trigger_type="scheduled_morning",
        run_date=date(2026, 6, 3),
        prior_trading_date=date(2026, 6, 2),
        lookback_start=date(2026, 5, 20),
        lookback_end=date(2026, 6, 2),
        journal_paths=[str(journal_path)],
        settings_snapshot_path=None,
        mode=mode,
        execution_mode=execution_mode,
        journal_output_path=str(journal_output_path) if journal_output_path else None,
        overlay_output_path=str(overlay_path) if overlay_path else None,
    )


def _strategy_record(
    index: int,
    *,
    trading_date: date | None = None,
    decision_id: str | None = None,
    run_id: str = "signal-run",
    target: str = "NTNX",
    theme: str = "AI_STORAGE",
    peer_ratio: float = 0.60,
    avg_score: float = 1.50,
    target_runup: float = 12.0,
    status: str = "candidate_ready_for_analyst",
) -> LearningJournalRecord:
    return LearningJournalRecord(
        record_type=LearningRecordType.STRATEGY_DECISION,
        run_id=run_id,
        decision_id=decision_id or f"decision-{index}",
        trading_date=trading_date or date(2026, 5, 20 + (index % 10)),
        created_at=datetime(2026, 6, 2, 16, index % 60),
        target=target,
        theme=theme,
        strategy_type="bullish_earnings_readthrough",
        payload={
            "strategy_status": status,
            "thresholds": {
                "min_positive_peer_ratio": 0.67,
                "min_average_peer_score": 2.0,
                "max_target_runup_pct": 10.0,
            },
            "peer_signal": {
                "positive_peer_ratio": peer_ratio,
                "average_peer_score": avg_score,
            },
            "target_filters": {
                "target_runup_pct": target_runup,
            },
            "preferred_expression": "CALL_OPTION",
        },
    )


def _outcome_record(
    index: int,
    *,
    decision_id: str | None = None,
    order_id: str | None = None,
    run_id: str = "signal-run",
    trading_date: date | None = None,
    target: str = "NTNX",
    theme: str = "AI_STORAGE",
    realized_pnl: float = -25.0,
    outcome_status: str = "closed",
) -> LearningJournalRecord:
    return LearningJournalRecord(
        record_type=LearningRecordType.TRADE_OUTCOME,
        run_id=run_id,
        decision_id=decision_id or f"decision-{index}",
        order_id=order_id,
        trading_date=trading_date or date(2026, 5, 20 + (index % 10)),
        created_at=datetime(2026, 6, 2, 20, index % 60),
        target=target,
        theme=theme,
        strategy_type="bullish_earnings_readthrough",
        payload={
            "outcome_status": outcome_status,
            "realized_pnl": realized_pnl,
            "fees": 0.0,
        },
    )


def _write_records(path: Path, records: list[LearningJournalRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n",
        encoding="utf-8",
    )


def _loss_cluster_records(count: int = 10) -> list[LearningJournalRecord]:
    records: list[LearningJournalRecord] = []
    for index in range(count):
        records.append(_strategy_record(index, peer_ratio=0.60, avg_score=1.50, target_runup=12.0))
        records.append(_outcome_record(index, realized_pnl=-25.0))
    return records


def _settings_snapshot() -> dict[str, object]:
    return {
        "strategy": {
            "min_positive_peer_ratio": 0.67,
            "min_average_peer_score": 2.0,
            "max_target_runup_pct": 10.0,
            "peer_result_window_days": 21,
            "min_reported_peers": 3,
        },
        "risk": {
            "max_trade_loss_pct": 0.03,
        },
    }


def test_report_only_reads_journal_and_does_not_write_overlay(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records())

    report = run_morning_learning_loop(
        _request(journal_path=journal_path, overlay_path=overlay_path),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert report.mode == LearningMode.REPORT_ONLY
    assert report.records_read == 20
    assert report.evaluated_decision_count == 10
    assert report.closed_outcome_count == 10
    assert report.loss_count == 10
    assert report.win_count == 0
    assert report.proposals
    assert all(proposal.applied is False for proposal in report.proposals)
    assert any(
        proposal.path == "strategy.min_positive_peer_ratio"
        and proposal.status == ParameterProposalStatus.PROPOSED
        and proposal.proposed_value == 0.72
        for proposal in report.proposals
    )
    assert report.settings_overlay_path is None
    assert not overlay_path.exists()


def test_shadow_overlay_writes_inactive_yaml_without_applying_proposals(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records())

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.SHADOW_OVERLAY,
            journal_path=journal_path,
            overlay_path=overlay_path,
        ),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    assert overlay["learning_overlay"]["active"] is False
    assert overlay["learning_overlay"]["mode"] == "shadow_overlay"
    assert "strategy.min_positive_peer_ratio" in overlay["learning_overlay"]["parameters"]
    assert report.settings_overlay_path == str(overlay_path)
    assert all(proposal.applied is False for proposal in report.proposals)


def test_auto_apply_safe_writes_active_yaml_and_marks_safe_proposals_applied(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records())

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.AUTO_APPLY_SAFE,
            journal_path=journal_path,
            overlay_path=overlay_path,
        ),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    applied_paths = {proposal.path for proposal in report.proposals if proposal.applied}
    assert overlay["learning_overlay"]["active"] is True
    assert overlay["learning_overlay"]["mode"] == "auto_apply_safe"
    assert "strategy.min_positive_peer_ratio" in applied_paths
    assert overlay["learning_overlay"]["parameters"]["strategy.min_positive_peer_ratio"][
        "previous_value"
    ] == 0.67
    assert overlay["learning_overlay"]["parameters"]["strategy.min_positive_peer_ratio"][
        "value"
    ] == 0.72


def test_auto_apply_safe_is_blocked_in_live_mode(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records())

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.AUTO_APPLY_SAFE,
            journal_path=journal_path,
            overlay_path=overlay_path,
            execution_mode="live",
        ),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert not overlay_path.exists()
    assert any("live mode" in warning for warning in report.warnings)
    assert all(proposal.applied is False for proposal in report.proposals)
    assert any(
        ParameterProposalReason.LIVE_MODE_BLOCKED in proposal.reasons
        for proposal in report.proposals
    )


def test_insufficient_sample_produces_no_applied_changes(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records(count=3))

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.AUTO_APPLY_SAFE,
            journal_path=journal_path,
            overlay_path=overlay_path,
        ),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert not overlay_path.exists()
    assert report.closed_outcome_count == 3
    assert all(proposal.applied is False for proposal in report.proposals)
    assert any(
        proposal.status == ParameterProposalStatus.NO_OP
        and ParameterProposalReason.INSUFFICIENT_SAMPLE in proposal.reasons
        for proposal in report.proposals
    )


def test_ambiguous_outcomes_are_excluded_from_parameter_tuning(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    ambiguous_date = date(2026, 6, 2)
    records = [
        _strategy_record(1, decision_id=None, trading_date=ambiguous_date, run_id="run-a"),
        _strategy_record(2, decision_id=None, trading_date=ambiguous_date, run_id="run-b"),
        _outcome_record(
            99,
            decision_id=None,
            run_id="run-c",
            trading_date=ambiguous_date,
            target="NTNX",
            theme="AI_STORAGE",
            realized_pnl=-50.0,
        ),
    ]
    records[0] = records[0].model_copy(update={"decision_id": None})
    records[1] = records[1].model_copy(update={"decision_id": None})
    records[2] = records[2].model_copy(update={"decision_id": None})
    _write_records(journal_path, records)

    report = run_morning_learning_loop(
        _request(journal_path=journal_path),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert report.closed_outcome_count == 0
    assert report.unknown_outcome_count == 2
    assert any("ambiguous_outcome_match" in warning for warning in report.warnings)
    assert all(proposal.applied is False for proposal in report.proposals)


def test_reader_counts_malformed_lines_without_leaking_payload(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    raw_secret = "SECRET_API_KEY_SHOULD_NOT_LEAK"
    journal_path.write_text(
        _strategy_record(1).model_dump_json()
        + "\n"
        + "{ bad json "
        + raw_secret
        + "\n",
        encoding="utf-8",
    )

    result = LocalJsonlLearningJournalReader().read_records(
        start_date=date(2026, 5, 20),
        end_date=date(2026, 6, 2),
        paths=[str(journal_path)],
    )

    assert result.records_read == 1
    assert result.malformed_record_count == 1
    assert result.records_skipped == 1
    assert raw_secret not in json.dumps(result.warnings)


def test_missing_journal_file_fails_closed_with_warning(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.AUTO_APPLY_SAFE,
            journal_path=missing_path,
            overlay_path=overlay_path,
        ),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert report.records_read == 0
    assert report.records_skipped == 1
    assert not overlay_path.exists()
    assert any("missing journal file" in warning for warning in report.warnings)
    assert all(proposal.applied is False for proposal in report.proposals)


def test_duplicate_run_id_is_refused_without_overwrite(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    output_path = tmp_path / "learning-output.jsonl"
    _write_records(journal_path, _loss_cluster_records())

    request = _request(
        mode=LearningMode.REPORT_ONLY,
        journal_path=journal_path,
        journal_output_path=output_path,
    )
    run_morning_learning_loop(
        request,
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    with pytest.raises(ValueError, match="already exists"):
        run_morning_learning_loop(
            request,
            settings_snapshot=_settings_snapshot(),
            created_at=datetime(2026, 6, 3, 13, 0),
        )


def test_reader_normalizes_existing_pipeline_journal_event(tmp_path: Path) -> None:
    journal_path = tmp_path / "runtime-journal.jsonl"
    journal_path.write_text(
        json.dumps(
            {
                "event_type": "hot_path_decision",
                "decision_index": 0,
                "target": "ntnx",
                "theme": "ai_storage",
                "strategy_status": "candidate_ready_for_analyst",
                "strategy_decision": {
                    "status": "candidate_ready_for_analyst",
                    "audit": {
                        "target": "NTNX",
                        "theme": "AI_STORAGE",
                        "thresholds": {
                            "min_positive_peer_ratio": 0.67,
                            "min_average_peer_score": 2.0,
                            "max_target_runup_pct": 10.0,
                        },
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = LocalJsonlLearningJournalReader().read_records(
        start_date=date(2026, 5, 20),
        end_date=date(2026, 6, 2),
        paths=[str(journal_path)],
    )

    assert result.records_read == 1
    assert result.records[0].record_type == LearningRecordType.STRATEGY_DECISION
    assert result.records[0].target == "NTNX"
    assert result.records[0].theme == "AI_STORAGE"


def test_forbidden_safety_parameters_are_rejected_even_when_policy_is_supplied(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    overlay_path = tmp_path / "learning-overlay.yaml"
    _write_records(journal_path, _loss_cluster_records())
    unsafe_policy = LearnableParameterPolicy(
        path="risk.max_trade_loss_pct",
        min_value=0.01,
        max_value=0.05,
        max_daily_delta=0.01,
        min_closed_outcomes=1,
        min_distinct_trading_days=1,
        auto_apply_allowed=True,
    )

    report = run_morning_learning_loop(
        _request(
            mode=LearningMode.AUTO_APPLY_SAFE,
            journal_path=journal_path,
            overlay_path=overlay_path,
        ),
        settings_snapshot=_settings_snapshot(),
        policies=[unsafe_policy],
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert not overlay_path.exists()
    assert report.proposals[0].status == ParameterProposalStatus.REJECTED
    assert ParameterProposalReason.SAFETY_PARAMETER_FORBIDDEN in report.proposals[0].reasons


def test_learning_report_metrics_are_preserved_by_shared_analytics_refactor(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    records: list[LearningJournalRecord] = []
    for index, pnl in enumerate([10.0, 20.0, -5.0, 0.0]):
        records.append(_strategy_record(index))
        records.append(_outcome_record(index, realized_pnl=pnl))
    _write_records(journal_path, records)

    report = run_morning_learning_loop(
        _request(journal_path=journal_path),
        settings_snapshot=_settings_snapshot(),
        created_at=datetime(2026, 6, 3, 13, 0),
    )

    assert report.closed_outcome_count == 4
    assert report.win_count == 2
    assert report.loss_count == 1
    assert report.flat_count == 1
    assert report.win_rate == 0.5
    assert report.average_realized_pnl == 6.25
    assert report.median_realized_pnl == 5.0
    assert report.average_win == 15.0
    assert report.average_loss == -5.0
    assert report.payoff_ratio == 3.0
    assert report.largest_loss == -5.0
