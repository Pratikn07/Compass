from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path

from prescient.learning.models import LearningMode, LearningRunReport
from prescient.rollout import (
    PaperPerformanceSnapshot,
    RolloutGateStatus,
    RolloutRejectionReason,
    RolloutSettings,
    RolloutStage,
    evaluate_broker_write_allowed,
    evaluate_rollout_capabilities,
    evaluate_rollout_promotion,
)
from prescient.rollout.models import RolloutPromotionRequest
from prescient.runtime import (
    DecisionJournalRecordType,
    build_rollout_gate_decision_record,
    build_rollout_promotion_record,
)


def test_default_stage_is_dashboard_only() -> None:
    settings = RolloutSettings()

    assert settings.default_stage == RolloutStage.DASHBOARD_ONLY
    assert settings.tiny_live_max_trade_loss_pct == 0.0025


def test_capability_matrix_for_all_rollout_stages() -> None:
    dashboard = evaluate_rollout_capabilities(RolloutStage.DASHBOARD_ONLY)
    alerts = evaluate_rollout_capabilities(RolloutStage.ALERTS_ONLY)
    paper = evaluate_rollout_capabilities(RolloutStage.PAPER_TRADING)
    tiny_live = evaluate_rollout_capabilities(RolloutStage.TINY_LIVE)

    assert dashboard.dashboard_allowed is True
    assert dashboard.alerts_allowed is False
    assert dashboard.broker_writes_allowed is False

    assert alerts.dashboard_allowed is True
    assert alerts.alerts_allowed is True
    assert alerts.broker_writes_allowed is False

    assert paper.alerts_allowed is True
    assert paper.paper_orders_allowed is True
    assert paper.live_orders_allowed is False
    assert paper.broker_writes_allowed is True

    assert tiny_live.paper_orders_allowed is True
    assert tiny_live.live_orders_allowed is True
    assert tiny_live.tiny_live_cap_pct == 0.0025


def test_promotion_blocks_stage_skipping_and_requires_manual_approval() -> None:
    skipped = evaluate_rollout_promotion(
        RolloutPromotionRequest(
            from_stage=RolloutStage.DASHBOARD_ONLY,
            to_stage=RolloutStage.PAPER_TRADING,
            requested_by="operator",
            manual_approval=True,
        )
    )
    missing_approval = evaluate_rollout_promotion(
        RolloutPromotionRequest(
            from_stage=RolloutStage.DASHBOARD_ONLY,
            to_stage=RolloutStage.ALERTS_ONLY,
            requested_by="operator",
            manual_approval=False,
        )
    )

    assert skipped.status == RolloutGateStatus.BLOCKED
    assert RolloutRejectionReason.STAGE_SKIP_NOT_ALLOWED in skipped.rejection_reasons
    assert missing_approval.status == RolloutGateStatus.BLOCKED
    assert RolloutRejectionReason.MANUAL_APPROVAL_REQUIRED in missing_approval.rejection_reasons


def test_paper_to_tiny_live_requires_positive_paper_results() -> None:
    failed = evaluate_rollout_promotion(
        RolloutPromotionRequest(
            from_stage=RolloutStage.PAPER_TRADING,
            to_stage=RolloutStage.TINY_LIVE,
            requested_by="operator",
            manual_approval=True,
            paper_performance=PaperPerformanceSnapshot(
                paper_trading_days=89,
                closed_trade_count=19,
                net_realized_pnl=-1.0,
                average_realized_pnl=0.0,
                max_drawdown_pct=0.06,
                unresolved_critical_warnings=["journal_gap"],
                journal_coverage_complete=False,
            ),
        )
    )
    passed = evaluate_rollout_promotion(
        RolloutPromotionRequest(
            from_stage=RolloutStage.PAPER_TRADING,
            to_stage=RolloutStage.TINY_LIVE,
            requested_by="operator",
            manual_approval=True,
            paper_performance=PaperPerformanceSnapshot(
                paper_trading_days=90,
                closed_trade_count=20,
                net_realized_pnl=125.0,
                average_realized_pnl=6.25,
                max_drawdown_pct=0.03,
                unresolved_critical_warnings=[],
                journal_coverage_complete=True,
            ),
        )
    )

    assert failed.status == RolloutGateStatus.BLOCKED
    assert failed.rejection_reasons == [
        RolloutRejectionReason.PAPER_TRADING_DAYS_BELOW_MINIMUM,
        RolloutRejectionReason.CLOSED_PAPER_TRADES_BELOW_MINIMUM,
        RolloutRejectionReason.PAPER_NET_PNL_NOT_POSITIVE,
        RolloutRejectionReason.PAPER_EXPECTANCY_NOT_POSITIVE,
        RolloutRejectionReason.PAPER_DRAWDOWN_EXCEEDED,
        RolloutRejectionReason.UNRESOLVED_CRITICAL_WARNINGS,
        RolloutRejectionReason.JOURNAL_COVERAGE_INCOMPLETE,
    ]
    assert passed.status == RolloutGateStatus.APPROVED
    assert passed.approved_stage == RolloutStage.TINY_LIVE


def test_learning_report_can_be_used_as_paper_evidence() -> None:
    report = LearningRunReport(
        run_id="learning:2026-06-03",
        run_date=date(2026, 6, 3),
        prior_trading_date=date(2026, 6, 2),
        lookback_start=date(2026, 3, 1),
        lookback_end=date(2026, 6, 3),
        created_at=datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
        mode=LearningMode.REPORT_ONLY,
        records_read=100,
        records_skipped=0,
        malformed_record_count=0,
        evaluated_decision_count=80,
        closed_outcome_count=20,
        win_count=12,
        loss_count=8,
        flat_count=0,
        unknown_outcome_count=0,
        average_realized_pnl=4.0,
    )

    snapshot = PaperPerformanceSnapshot.from_learning_report(
        report,
        max_drawdown_pct=0.02,
    )

    assert snapshot.paper_trading_days == 95
    assert snapshot.closed_trade_count == 20
    assert snapshot.net_realized_pnl == 80.0
    assert snapshot.average_realized_pnl == 4.0


def test_tiny_live_rejects_broker_write_above_selected_cap() -> None:
    blocked = evaluate_broker_write_allowed(
        RolloutStage.TINY_LIVE,
        execution_mode="live",
        proposed_max_loss_pct=0.003,
    )
    allowed = evaluate_broker_write_allowed(
        RolloutStage.TINY_LIVE,
        execution_mode="live",
        proposed_max_loss_pct=0.0025,
    )

    assert blocked.status == RolloutGateStatus.BLOCKED
    assert RolloutRejectionReason.TINY_LIVE_RISK_CAP_EXCEEDED in blocked.rejection_reasons
    assert allowed.status == RolloutGateStatus.APPROVED


def test_rollout_journal_builders_produce_json_safe_stable_records() -> None:
    gate = evaluate_broker_write_allowed(
        RolloutStage.DASHBOARD_ONLY,
        execution_mode="paper",
        proposed_max_loss_pct=0.001,
    )
    promotion = evaluate_rollout_promotion(
        RolloutPromotionRequest(
            from_stage=RolloutStage.DASHBOARD_ONLY,
            to_stage=RolloutStage.ALERTS_ONLY,
            requested_by="operator",
            manual_approval=True,
        )
    )

    gate_record = build_rollout_gate_decision_record(
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
        gate_decision=gate,
        decision_id="decision-1",
        decision_index=0,
        target="ntnx",
        theme="ai_storage",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="paper",
    )
    same_gate_record = build_rollout_gate_decision_record(
        run_id="scheduled:2026-06-03",
        trading_date=date(2026, 6, 3),
        gate_decision=gate,
        decision_id="decision-1",
        decision_index=0,
        target="ntnx",
        theme="ai_storage",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="paper",
    )
    promotion_record = build_rollout_promotion_record(
        run_id="rollout:2026-06-03",
        trading_date=date(2026, 6, 3),
        gate_decision=promotion,
    )

    assert gate_record.record_type == DecisionJournalRecordType.ROLLOUT_GATE_DECISION
    assert promotion_record.record_type == DecisionJournalRecordType.ROLLOUT_PROMOTION
    assert gate_record.journal_record_id == same_gate_record.journal_record_id
    assert gate_record.payload["rejection_reasons"] == ["paper_trading_not_allowed"]
    assert gate_record.model_dump_json()
    assert promotion_record.model_dump_json()


def test_boundary_packages_do_not_import_rollout_runtime_or_alert_writers() -> None:
    forbidden_roots = {
        "prescient.rollout",
        "prescient.runtime.decision_journal",
        "prescient.runtime.journal",
        "prescient.alerts.adapters",
        "prescient.alerts.dispatcher",
        "prescient.storage",
    }
    roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/analyst"),
    ]

    for root in roots:
        for path in root.glob("*.py"):
            active_forbidden_roots = (
                forbidden_roots - {"prescient.storage"}
                if path == Path("src/prescient/data/runtime.py")
                else forbidden_roots
            )
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
                for forbidden in active_forbidden_roots
            ), f"{path} imports forbidden rollout/runtime writer dependency: {imports}"
