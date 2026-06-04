"""R5.5 / R5.6 — Broker as Source of Truth execution pipeline.

The orchestrator fetches fresh broker state before every risk evaluation.
If any broker call fails, execution halts (fail-closed).  The risk domain
models (RiskPosition, RiskOrder, AccountRiskSnapshot) never import broker
modules — the mapping happens here in the runtime layer.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from prescient.alerts import (
    NotificationAdapter,
    TradeNotificationResult,
    TradeNotificationSettings,
    build_trade_notification_request,
    dispatch_trade_notification,
)
from prescient.broker.interfaces import BrokerAdapter
from prescient.broker.models import (
    BrokerError,
    BrokerOrder,
    BrokerPosition,
    OrderExecutionResult,
)
from prescient.risk.gatekeeper import evaluate_risk_gate
from prescient.risk.models import (
    AccountRiskSnapshot,
    ConcentrationSettings,
    RiskGateStatus,
    RiskOrder,
    RiskOrderProposal,
    RiskPosition,
    RiskSettings,
    TradeExpression,
    TradeProposal,
)
from prescient.risk.position_sizing import PositionSizingStatus, size_position
from prescient.runtime.decision_journal import (
    build_decision_id,
    build_order_submitted_record,
    build_rollout_gate_decision_record,
    build_trade_notification_record,
)
from prescient.runtime.journal import append_decision_journal_records
from prescient.runtime.models import (
    DecisionJournalRecord,
    ExecutionDecisionResult,
    ExecutionPipelineResult,
    PipelineRunResult,
)
from prescient.rollout import (
    RolloutGateDecision,
    RolloutSettings,
    RolloutStage,
    evaluate_broker_write_allowed,
)
from prescient.safety import KillSwitchStatus
from prescient.signal.models import StrategyDecision, StrategyStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Broker → Risk domain mappers
# ---------------------------------------------------------------------------

def _map_position(bp: BrokerPosition) -> RiskPosition:
    return RiskPosition(
        symbol=bp.symbol,
        expression=bp.expression,
        qty=bp.qty,
        market_value=bp.market_value,
        average_entry_price=bp.average_entry_price,
    )


def _map_order(bo: BrokerOrder) -> RiskOrder:
    return RiskOrder(
        order_id=bo.order_id,
        symbol=bo.symbol,
        qty=bo.qty,
        filled_qty=bo.filled_qty,
        limit_price=bo.limit_price,
        status=str(bo.status),
        submitted_at=bo.submitted_at,
        side=bo.side,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_broker_state(
    broker: BrokerAdapter,
) -> tuple[AccountRiskSnapshot, list[RiskPosition], list[RiskOrder]]:
    """Fetch fresh account state from the broker adapter.

    Returns:
        Tuple of (snapshot, positions, orders) mapped into risk-domain models.

    Raises:
        BrokerError: Propagated if any broker call fails (fail-closed).
    """
    snapshot = broker.get_account_snapshot()
    positions = [_map_position(p) for p in broker.get_positions()]
    orders = [_map_order(o) for o in broker.get_orders()]
    return snapshot, positions, orders


def preflight_and_execute(
    *,
    decision: StrategyDecision,
    decision_index: int = 0,
    broker: BrokerAdapter,
    account_snapshot: AccountRiskSnapshot,
    risk_positions: Sequence[RiskPosition],
    risk_orders: Sequence[RiskOrder],
    risk_settings: RiskSettings | None = None,
    concentration_settings: ConcentrationSettings | None = None,
    claude_advisory: Mapping[str, Any] | None = None,
    kill_switch_provider: Any | None = None,
    rollout_stage: RolloutStage | str | None = None,
    rollout_settings: RolloutSettings | None = None,
    notification_adapter: NotificationAdapter | None = None,
    notification_settings: TradeNotificationSettings | None = None,
    processed_notification_keys: set[str] | None = None,
    journal_path: str | Path | None = None,
    run_id: str | None = None,
    trading_date: date | None = None,
) -> ExecutionDecisionResult | None:
    """Run preflight risk checks and execute a single strategy decision.

    Skips non-candidate decisions silently.
    """
    if risk_settings is None:
        risk_settings = RiskSettings()

    if decision.status != StrategyStatus.CANDIDATE_READY_FOR_ANALYST:
        return None

    candidate = decision.candidate
    if candidate is None:
        return None

    target = candidate.target
    expression = candidate.recommended_expression

    if expression not in ("CALL_OPTION", "STOCK", "PUT_OPTION"):
        logger.warning("Unsupported trade expression for sizing: %s", expression)
        return None
    trade_expr = TradeExpression(expression)

    # Build a TradeProposal for position sizing.
    # CandidateBrief does not carry entry/stop prices — those are filled
    # by a market-data lookup in a real deployment.  For now we pass None
    # so the sizer correctly returns NOT_EVALUABLE rather than sizing
    # blindly.
    trade_proposal = TradeProposal(
        target=target,
        expression=trade_expr,
        entry_price=None,
        stop_price=None,
    )

    sizing = size_position(
        strategy_decision=decision,
        account_snapshot=account_snapshot,
        proposal=trade_proposal,
        settings=risk_settings,
        claude_advisory=claude_advisory,
        broker_positions=list(risk_positions),
        concentration_settings=concentration_settings,
    )

    if sizing.status != PositionSizingStatus.SIZED:
        logger.warning(
            "Sizing blocked for %s: %s — %s",
            target,
            [r.value for r in sizing.rejection_reasons],
            sizing.explanation,
        )
        return None

    if expression not in ("CALL_OPTION", "STOCK"):
        logger.warning("Expression %s not supported for order proposal", expression)
        return None

    order_proposal = RiskOrderProposal(
        target=target,
        expression=expression,
        estimated_entry_cost=sizing.entry_cost_required or 0.0,
        maximum_loss=sizing.projected_max_loss or 0.0,
    )

    # R5.6 — Preflight buying-power check is implicit inside size_position
    # (INSUFFICIENT_CASH_OR_BUYING_POWER rejection). The gate adds
    # concentration / averaging-down / daily-halt checks.

    gate = evaluate_risk_gate(
        strategy_decision=decision,
        account_snapshot=account_snapshot,
        order_proposal=order_proposal,
        claude_advisory=claude_advisory,
        broker_positions=list(risk_positions),
        broker_orders=list(risk_orders),
        concentration_settings=concentration_settings,
    )

    if gate.status != RiskGateStatus.APPROVED:
        logger.warning(
            "Risk gate blocked for %s: %s — %s",
            target,
            [r.value for r in gate.rejection_reasons],
            gate.explanation,
        )
        return None

    execution_mode = _execution_mode(broker) or "paper"
    active_rollout_settings = rollout_settings or RolloutSettings()
    active_rollout_stage = rollout_stage or active_rollout_settings.default_stage
    rollout_gate = evaluate_broker_write_allowed(
        active_rollout_stage,
        execution_mode=execution_mode,
        proposed_max_loss_pct=_proposed_max_loss_pct(
            account_snapshot=account_snapshot,
            order_proposal=order_proposal,
        ),
        settings=active_rollout_settings,
    )
    if not rollout_gate.broker_execution_allowed:
        _journal_rollout_gate(
            decision=decision,
            decision_index=decision_index,
            rollout_gate=rollout_gate,
            journal_path=journal_path,
            run_id=run_id or "execution:unknown",
            trading_date=trading_date or date.today(),
            execution_mode=execution_mode,
        )
        logger.warning(
            "Rollout gate blocked broker write for %s: %s — %s",
            target,
            [reason.value for reason in rollout_gate.rejection_reasons],
            rollout_gate.explanation,
        )
        return None

    # --- All checks passed — submit order ---
    if kill_switch_provider is not None and not _kill_switch_allows_order(
        provider=kill_switch_provider,
        target=target,
    ):
        return None

    try:
        result = broker.place_order(order_proposal)
        logger.info(
            "Order placed for %s — id=%s status=%s filled=%d avg_price=%s",
            target,
            result.order_id,
            result.status,
            result.filled_qty,
            result.avg_fill_price,
        )
        return _record_and_notify_execution(
            decision=decision,
            decision_index=decision_index,
            broker=broker,
            order_proposal=order_proposal,
            order_result=result,
            notification_adapter=notification_adapter,
            notification_settings=notification_settings,
            processed_notification_keys=processed_notification_keys,
            journal_path=journal_path,
            run_id=run_id or "execution:unknown",
            trading_date=trading_date,
        )
    except BrokerError as exc:
        logger.error("Broker rejected order for %s: %s", target, exc)
        return None


def execute_pipeline_results(
    pipeline_result: PipelineRunResult,
    broker: BrokerAdapter,
    *,
    risk_settings: RiskSettings | None = None,
    concentration_settings: ConcentrationSettings | None = None,
    claude_advisory: Mapping[str, Any] | None = None,
    kill_switch_provider: Any | None = None,
    rollout_stage: RolloutStage | str | None = None,
    rollout_settings: RolloutSettings | None = None,
    notification_adapter: NotificationAdapter | None = None,
    notification_settings: TradeNotificationSettings | None = None,
    processed_notification_keys: set[str] | None = None,
    journal_path: str | Path | None = None,
    run_id: str | None = None,
    trading_date: date | None = None,
) -> ExecutionPipelineResult:
    """Top-level entry: fetch broker state once, then evaluate every decision.

    R5.5: The broker adapter is the **sole** source of account state.
    If state retrieval fails, the entire run is aborted (fail-closed).
    """
    try:
        snapshot, positions, orders = fetch_broker_state(broker)
    except BrokerError as exc:
        logger.error("Broker state retrieval failed — aborting run: %s", exc)
        return ExecutionPipelineResult()

    execution_results: list[ExecutionDecisionResult] = []
    notification_results: list[TradeNotificationResult] = []
    decision_journal_records: list[DecisionJournalRecord] = []
    active_run_id = run_id or "execution:unknown"

    for index, decision in enumerate(pipeline_result.strategy_decisions):
        execution_result = preflight_and_execute(
            decision=decision,
            decision_index=index,
            broker=broker,
            account_snapshot=snapshot,
            risk_positions=positions,
            risk_orders=orders,
            risk_settings=risk_settings,
            concentration_settings=concentration_settings,
            claude_advisory=claude_advisory,
            kill_switch_provider=kill_switch_provider,
            rollout_stage=rollout_stage,
            rollout_settings=rollout_settings,
            notification_adapter=notification_adapter,
            notification_settings=notification_settings,
            processed_notification_keys=processed_notification_keys,
            journal_path=journal_path,
            run_id=active_run_id,
            trading_date=trading_date,
        )
        if execution_result is None:
            continue
        execution_results.append(execution_result)
        if execution_result.notification_result is not None:
            notification_results.append(execution_result.notification_result)
        decision_journal_records.extend(execution_result.decision_journal_records)

    return ExecutionPipelineResult(
        execution_results=execution_results,
        notification_results=notification_results,
        decision_journal_records=decision_journal_records,
    )


def _record_and_notify_execution(
    *,
    decision: StrategyDecision,
    decision_index: int,
    broker: BrokerAdapter,
    order_proposal: RiskOrderProposal,
    order_result: OrderExecutionResult,
    notification_adapter: NotificationAdapter | None,
    notification_settings: TradeNotificationSettings | None,
    processed_notification_keys: set[str] | None,
    journal_path: str | Path | None,
    run_id: str,
    trading_date: date | None,
) -> ExecutionDecisionResult:
    active_trading_date = trading_date or date.today()
    execution_mode = _execution_mode(broker) or "paper"
    broker_name = _broker_name(broker, order_result)
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    order_record = build_order_submitted_record(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
        order_result=order_result,
        trading_date=active_trading_date,
        execution_mode=execution_mode,
    )
    if journal_path is not None:
        append_decision_journal_records([order_record], journal_path)

    request = build_trade_notification_request(
        decision=decision,
        order_proposal=order_proposal,
        order_result=order_result,
        run_id=run_id,
        decision_id=decision_id,
        decision_index=decision_index,
        broker=broker_name,
        execution_mode=execution_mode or "unknown",
    )
    notification_result = dispatch_trade_notification(
        request,
        adapter=notification_adapter,
        settings=notification_settings or TradeNotificationSettings(),
        processed_notification_keys=processed_notification_keys,
    )
    notification_record = build_trade_notification_record(
        notification_result=notification_result,
        trading_date=active_trading_date,
    )
    if journal_path is not None:
        append_decision_journal_records([notification_record], journal_path)

    target, theme = _target_and_theme(decision)
    return ExecutionDecisionResult(
        decision_index=decision_index,
        target=target,
        theme=theme,
        order_result=order_result,
        notification_result=notification_result,
        decision_journal_records=[order_record, notification_record],
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme
    return decision.audit.target, decision.audit.theme


def _proposed_max_loss_pct(
    *,
    account_snapshot: AccountRiskSnapshot,
    order_proposal: RiskOrderProposal,
) -> float | None:
    if account_snapshot.equity <= 0:
        return None
    return order_proposal.maximum_loss / account_snapshot.equity


def _journal_rollout_gate(
    *,
    decision: StrategyDecision,
    decision_index: int,
    rollout_gate: RolloutGateDecision,
    journal_path: str | Path | None,
    run_id: str,
    trading_date: date,
    execution_mode: str,
) -> None:
    if journal_path is None:
        return
    target, theme = _target_and_theme(decision)
    decision_id = build_decision_id(
        run_id=run_id,
        decision_index=decision_index,
        decision=decision,
    )
    record = build_rollout_gate_decision_record(
        run_id=run_id,
        trading_date=trading_date,
        gate_decision=rollout_gate,
        decision_id=decision_id,
        decision_index=decision_index,
        target=target,
        theme=theme,
        strategy_status=decision.status.value,
        execution_mode=execution_mode,
    )
    append_decision_journal_records([record], journal_path)


def _execution_mode(broker: BrokerAdapter) -> str | None:
    current: object | None = broker
    while current is not None:
        if current.__class__.__name__ == "ProposeOnlyBrokerWrapper":
            return "propose_only"
        mode = _instance_attr(current, "execution_mode")
        if isinstance(mode, str):
            return mode
        value = getattr(mode, "value", None)
        if isinstance(value, str):
            return value
        current = _instance_attr(current, "_inner")
    return None


def _broker_name(broker: BrokerAdapter, order_result: OrderExecutionResult) -> str:
    if order_result.broker:
        return order_result.broker
    current: object | None = broker
    while current is not None:
        broker_name = _instance_attr(current, "broker_name")
        if isinstance(broker_name, str) and broker_name:
            return broker_name
        current = _instance_attr(current, "_inner")
    return "unknown"


def _instance_attr(obj: object | None, name: str) -> object | None:
    if obj is None:
        return None
    values = getattr(obj, "__dict__", None)
    if isinstance(values, dict):
        return values.get(name)
    return None


def _kill_switch_allows_order(*, provider: Any, target: str) -> bool:
    try:
        state = provider.read_state()
    except Exception as exc:
        logger.error(
            "Kill switch state retrieval failed for %s — order placement blocked: %s",
            target,
            exc,
        )
        return False

    if state.status == KillSwitchStatus.ACTIVE:
        logger.error("Kill switch active for %s — order placement blocked.", target)
        return False

    return True
