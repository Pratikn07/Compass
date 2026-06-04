from __future__ import annotations

from prescient.rollout.models import (
    PaperPerformanceSnapshot,
    RolloutCapabilityDecision,
    RolloutGateDecision,
    RolloutGateStatus,
    RolloutPromotionRequest,
    RolloutRejectionReason,
    RolloutSettings,
    RolloutStage,
)


_STAGE_ORDER: tuple[RolloutStage, ...] = (
    RolloutStage.DASHBOARD_ONLY,
    RolloutStage.ALERTS_ONLY,
    RolloutStage.PAPER_TRADING,
    RolloutStage.TINY_LIVE,
)


def evaluate_rollout_capabilities(
    stage: RolloutStage | str,
    settings: RolloutSettings | None = None,
) -> RolloutCapabilityDecision:
    active_settings = settings or RolloutSettings()
    active_stage = _coerce_stage(stage)
    stage_index = _STAGE_ORDER.index(active_stage)
    paper_allowed = stage_index >= _STAGE_ORDER.index(RolloutStage.PAPER_TRADING)
    live_allowed = active_stage == RolloutStage.TINY_LIVE
    return RolloutCapabilityDecision(
        stage=active_stage,
        dashboard_allowed=True,
        alerts_allowed=stage_index >= _STAGE_ORDER.index(RolloutStage.ALERTS_ONLY),
        paper_orders_allowed=paper_allowed,
        live_orders_allowed=live_allowed,
        broker_writes_allowed=paper_allowed or live_allowed,
        tiny_live_cap_pct=active_settings.tiny_live_max_trade_loss_pct,
    )


def evaluate_rollout_promotion(
    request: RolloutPromotionRequest,
    settings: RolloutSettings | None = None,
) -> RolloutGateDecision:
    active_settings = settings or RolloutSettings()
    reasons: list[RolloutRejectionReason] = []

    if not _is_next_stage(request.from_stage, request.to_stage):
        reasons.append(RolloutRejectionReason.STAGE_SKIP_NOT_ALLOWED)

    if active_settings.require_manual_approval and not request.manual_approval:
        reasons.append(RolloutRejectionReason.MANUAL_APPROVAL_REQUIRED)

    if (
        request.from_stage == RolloutStage.PAPER_TRADING
        and request.to_stage == RolloutStage.TINY_LIVE
    ):
        evidence = _coerce_paper_performance(request.paper_performance)
        if evidence is None:
            reasons.append(RolloutRejectionReason.PAPER_EVIDENCE_MISSING)
        else:
            reasons.extend(_paper_gate_rejections(evidence, active_settings))

    if reasons:
        return RolloutGateDecision(
            status=RolloutGateStatus.BLOCKED,
            current_stage=request.from_stage,
            requested_stage=request.to_stage,
            approved_stage=None,
            tiny_live_cap_pct=active_settings.tiny_live_max_trade_loss_pct,
            rejection_reasons=reasons,
            explanation="Rollout promotion blocked.",
            payload={
                "requested_by": request.requested_by,
                "manual_approval": request.manual_approval,
            },
        )

    return RolloutGateDecision(
        status=RolloutGateStatus.APPROVED,
        current_stage=request.from_stage,
        requested_stage=request.to_stage,
        approved_stage=request.to_stage,
        tiny_live_cap_pct=active_settings.tiny_live_max_trade_loss_pct,
        broker_execution_allowed=False,
        explanation="Rollout promotion approved.",
        payload={
            "requested_by": request.requested_by,
            "manual_approval": request.manual_approval,
        },
    )


def evaluate_broker_write_allowed(
    stage: RolloutStage | str,
    *,
    execution_mode: str | object | None,
    proposed_max_loss_pct: float | None,
    settings: RolloutSettings | None = None,
) -> RolloutGateDecision:
    active_settings = settings or RolloutSettings()
    active_stage = _coerce_stage(stage)
    mode = _coerce_execution_mode(execution_mode)
    reasons: list[RolloutRejectionReason] = []

    if mode == "paper":
        if _STAGE_ORDER.index(active_stage) < _STAGE_ORDER.index(RolloutStage.PAPER_TRADING):
            reasons.append(RolloutRejectionReason.PAPER_TRADING_NOT_ALLOWED)
    elif mode == "live":
        if active_stage != RolloutStage.TINY_LIVE:
            reasons.append(RolloutRejectionReason.LIVE_TRADING_NOT_ALLOWED)
        elif proposed_max_loss_pct is None:
            reasons.append(RolloutRejectionReason.TINY_LIVE_RISK_CAP_MISSING)
        elif proposed_max_loss_pct > active_settings.tiny_live_max_trade_loss_pct:
            reasons.append(RolloutRejectionReason.TINY_LIVE_RISK_CAP_EXCEEDED)
    else:
        reasons.append(RolloutRejectionReason.UNSUPPORTED_EXECUTION_MODE)

    if reasons:
        return RolloutGateDecision(
            status=RolloutGateStatus.BLOCKED,
            current_stage=active_stage,
            requested_execution_mode=mode,
            proposed_max_loss_pct=proposed_max_loss_pct,
            tiny_live_cap_pct=active_settings.tiny_live_max_trade_loss_pct,
            broker_execution_allowed=False,
            rejection_reasons=reasons,
            explanation="Rollout stage blocks broker write.",
        )

    return RolloutGateDecision(
        status=RolloutGateStatus.APPROVED,
        current_stage=active_stage,
        requested_execution_mode=mode,
        proposed_max_loss_pct=proposed_max_loss_pct,
        tiny_live_cap_pct=active_settings.tiny_live_max_trade_loss_pct,
        broker_execution_allowed=True,
        explanation="Rollout stage allows broker write.",
    )


def _paper_gate_rejections(
    evidence: PaperPerformanceSnapshot,
    settings: RolloutSettings,
) -> list[RolloutRejectionReason]:
    reasons: list[RolloutRejectionReason] = []
    if evidence.paper_trading_days < settings.min_paper_trading_days:
        reasons.append(RolloutRejectionReason.PAPER_TRADING_DAYS_BELOW_MINIMUM)
    if evidence.closed_trade_count < settings.min_closed_paper_trades:
        reasons.append(RolloutRejectionReason.CLOSED_PAPER_TRADES_BELOW_MINIMUM)
    if (
        settings.require_positive_net_pnl
        and (evidence.net_realized_pnl is None or evidence.net_realized_pnl <= 0)
    ):
        reasons.append(RolloutRejectionReason.PAPER_NET_PNL_NOT_POSITIVE)
    if (
        settings.require_positive_expectancy
        and (
            evidence.average_realized_pnl is None
            or evidence.average_realized_pnl <= 0
        )
    ):
        reasons.append(RolloutRejectionReason.PAPER_EXPECTANCY_NOT_POSITIVE)
    if evidence.max_drawdown_pct is None:
        reasons.append(RolloutRejectionReason.PAPER_DRAWDOWN_MISSING)
    elif evidence.max_drawdown_pct > settings.max_paper_drawdown_pct:
        reasons.append(RolloutRejectionReason.PAPER_DRAWDOWN_EXCEEDED)
    if evidence.unresolved_critical_warnings:
        reasons.append(RolloutRejectionReason.UNRESOLVED_CRITICAL_WARNINGS)
    if settings.require_complete_journal_coverage and not evidence.journal_coverage_complete:
        reasons.append(RolloutRejectionReason.JOURNAL_COVERAGE_INCOMPLETE)
    return reasons


def _is_next_stage(from_stage: RolloutStage, to_stage: RolloutStage) -> bool:
    from_index = _STAGE_ORDER.index(from_stage)
    return from_index + 1 < len(_STAGE_ORDER) and _STAGE_ORDER[from_index + 1] == to_stage


def _coerce_stage(stage: RolloutStage | str) -> RolloutStage:
    return stage if isinstance(stage, RolloutStage) else RolloutStage(str(stage))


def _coerce_execution_mode(mode: str | object | None) -> str | None:
    if mode is None:
        return None
    value = getattr(mode, "value", mode)
    return str(value).strip().lower()


def _coerce_paper_performance(
    value: PaperPerformanceSnapshot | object | None,
) -> PaperPerformanceSnapshot | None:
    if value is None:
        return None
    if isinstance(value, PaperPerformanceSnapshot):
        return value
    return PaperPerformanceSnapshot.from_learning_report(value)  # type: ignore[arg-type]
