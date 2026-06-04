from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path

from prescient.broker.interfaces import BrokerAdapter
from prescient.broker.models import BrokerError, OrderStatusFilter, BrokerPosition, BrokerOrder
from prescient.risk import (
    AccountRiskSnapshot,
    ConcentrationSettings,
    DailyHaltSettings,
    DailyRiskState,
    DailyHaltDecision,
    DailyHaltStatus,
    RiskGateDecision,
    RiskGateStatus,
    RiskOrderProposal,
    RiskPosition,
    RiskOrder,
    RiskRejectionReason,
    PositionSizingDecision,
    TradeProposal,
    TradeExpression,
    evaluate_risk_gate,
    size_position,
    evaluate_daily_halt,
)
from prescient.data import TranscriptProvider, TranscriptSummarizer
from prescient.analyst.claude import ClaudeCompletionClient, analyze_strategy_decision
from prescient.analyst.models import (
    ClaudeAnalysisResult,
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    SubAgentName,
    SubAgentReviewPacket,
)
from prescient.analyst.sub_agents import (
    DEFAULT_SUB_AGENTS,
    analyze_strategy_decision_with_sub_agents,
)
from prescient.journal import DecisionLayer, DecisionType
from prescient.risk.audit import risk_audit_trail
from prescient.runtime.decision_journal import (
    build_analyst_review_record,
    build_position_sizing_record,
    build_risk_decision_record,
    build_strategy_decision_record,
    build_sub_agent_review_record,
)
from prescient.runtime.journal import append_decision_journal_records
from prescient.runtime.models import (
    DecisionJournalRecord,
    DecisionJournalRecordType,
    PipelineJournalEvent,
    PipelineJournalEventType,
    PipelineRunResult,
)
from prescient.rollout import RolloutSettings, RolloutStage, evaluate_rollout_capabilities
from prescient.signal.core import evaluate_core_strategy
from prescient.signal.models import (
    CandidateBrief,
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyDecision,
    StrategySettings,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.strategy_types import PreferredExpression


_DEFAULT_STRATEGY_SETTINGS = StrategySettings()
_DEFAULT_CLAUDE_SETTINGS = ClaudeAnalystSettings()


def run_hot_cold_strategy_pipeline(
    *,
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    peer_results: list[PeerResult],
    target_market_data: Mapping[str, TargetMarketData] | None,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    current_date: date,
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None = None,
    settings: StrategySettings = _DEFAULT_STRATEGY_SETTINGS,
    preferred_expression: PreferredExpression = "CALL_OPTION",
    enable_claude_analysis: bool = False,
    claude_client: ClaudeCompletionClient | None = None,
    claude_settings: ClaudeAnalystSettings = _DEFAULT_CLAUDE_SETTINGS,
    enable_sub_agent_analysis: bool = False,
    sub_agent_clients: Mapping[SubAgentName, ClaudeCompletionClient] | None = None,
    enabled_sub_agents: Sequence[SubAgentName] = DEFAULT_SUB_AGENTS,
    journal_path: str | Path | None = None,
    transcript_provider: TranscriptProvider | None = None,
    transcript_summarizer: TranscriptSummarizer | None = None,
    broker_adapter: BrokerAdapter | None = None,
    concentration_settings: ConcentrationSettings | None = None,
    daily_halt_settings: DailyHaltSettings | None = None,
    run_id: str | None = None,
    storage_writer: object | None = None,
    storage_write_policy: object = "optional",
    alert_dispatcher: object | None = None,
    alert_recipients: Sequence[object] | None = None,
    alert_dry_run: bool = False,
    rollout_stage: RolloutStage | str | None = None,
    rollout_settings: RolloutSettings | None = None,
) -> PipelineRunResult:
    active_run_id = run_id or f"runtime:{current_date.isoformat()}"
    execution_mode = _execution_mode(broker_adapter)
    updated_peer_results = list(peer_results)
    if transcript_provider is not None and transcript_summarizer is not None:
        for idx, peer in enumerate(peer_results):
            if peer.transcript_summary is None:
                month = peer.earnings_event.earnings_date.month
                if month in {1, 2, 3}:
                    quarter = 4
                    year = peer.earnings_event.earnings_date.year - 1
                elif month in {4, 5, 6}:
                    quarter = 1
                    year = peer.earnings_event.earnings_date.year
                elif month in {7, 8, 9}:
                    quarter = 2
                    year = peer.earnings_event.earnings_date.year
                else:
                    quarter = 3
                    year = peer.earnings_event.earnings_date.year

                res = transcript_provider.get_transcript(
                    ticker=peer.ticker,
                    year=year,
                    quarter=quarter,
                )
                if res.snapshots and not res.errors:
                    themes = universe.themes_for_ticker(peer.ticker)
                    drivers = []
                    for t in themes:
                        drivers.extend(t.drivers)
                    drivers = list(dict.fromkeys(drivers))

                    try:
                        summary = transcript_summarizer.summarize_transcript(res, drivers)
                        updated_peer_results[idx] = peer.model_copy(
                            update={"transcript_summary": summary}
                        )
                    except Exception:
                        pass

    strategy_decisions = evaluate_core_strategy(
        universe=universe,
        upcoming_events=upcoming_events,
        peer_results=updated_peer_results,
        target_market_data=target_market_data,
        options_chains=options_chains,
        current_date=current_date,
        indicator_snapshots=indicator_snapshots,
        settings=settings,
        preferred_expression=preferred_expression,
    )

    hot_path_events = [
        _hot_path_event(
            run_id=active_run_id,
            decision_index=index,
            decision=decision,
        )
        for index, decision in enumerate(strategy_decisions)
    ]
    decision_journal_records: list[DecisionJournalRecord] = [
        build_strategy_decision_record(
            run_id=active_run_id,
            decision_index=index,
            decision=decision,
            trading_date=current_date,
            settings=settings,
            target_market_data=_target_data_for_decision(decision, target_market_data),
            options_chain=_options_for_decision(decision, options_chains),
            execution_mode=execution_mode,
        )
        for index, decision in enumerate(strategy_decisions)
    ]
    if journal_path is not None:
        append_decision_journal_records(decision_journal_records, journal_path)

    sub_agent_packets = (
        [
            analyze_strategy_decision_with_sub_agents(
                decision=decision,
                clients=sub_agent_clients,
                enabled_agents=enabled_sub_agents,
                settings=claude_settings,
            )
            for decision in strategy_decisions
        ]
        if enable_sub_agent_analysis
        else []
    )

    sub_agent_events = (
        [
            _sub_agent_event(
                run_id=active_run_id,
                decision_index=index,
                decision=decision,
                sub_agent_packet=sub_agent_packet,
            )
            for index, (decision, sub_agent_packet) in enumerate(
                zip(strategy_decisions, sub_agent_packets, strict=True)
            )
        ]
        if enable_sub_agent_analysis
        else []
    )
    if journal_path is not None and sub_agent_events:
        sub_agent_records = [
            build_sub_agent_review_record(
                run_id=active_run_id,
                decision_index=index,
                decision=decision,
                sub_agent_packet=sub_agent_packet,
                trading_date=current_date,
                execution_mode=execution_mode,
            )
            for index, (decision, sub_agent_packet) in enumerate(
                zip(strategy_decisions, sub_agent_packets, strict=True)
            )
        ]
        decision_journal_records.extend(sub_agent_records)
        append_decision_journal_records(sub_agent_records, journal_path)
    elif sub_agent_events:
        decision_journal_records.extend(
            [
                build_sub_agent_review_record(
                    run_id=active_run_id,
                    decision_index=index,
                    decision=decision,
                    sub_agent_packet=sub_agent_packet,
                    trading_date=current_date,
                    execution_mode=execution_mode,
                )
                for index, (decision, sub_agent_packet) in enumerate(
                    zip(strategy_decisions, sub_agent_packets, strict=True)
                )
            ]
        )

    claude_results = [
        _analyze_cold_path(
            decision=decision,
            enable_claude_analysis=enable_claude_analysis,
            claude_client=claude_client,
            claude_settings=claude_settings,
        )
        for decision in strategy_decisions
    ]

    cold_path_events = [
        _cold_path_event(
            run_id=active_run_id,
            decision_index=index,
            decision=decision,
            claude_result=claude_result,
        )
        for index, (decision, claude_result) in enumerate(
            zip(strategy_decisions, claude_results, strict=True)
        )
    ]
    cold_path_records = [
        build_analyst_review_record(
            run_id=active_run_id,
            decision_index=index,
            decision=decision,
            claude_result=claude_result,
            trading_date=current_date,
            execution_mode=execution_mode,
        )
        for index, (decision, claude_result) in enumerate(
            zip(strategy_decisions, claude_results, strict=True)
        )
    ]
    decision_journal_records.extend(cold_path_records)
    if journal_path is not None:
        append_decision_journal_records(cold_path_records, journal_path)

    risk_gate_decisions: list[RiskGateDecision] = []
    sizing_decisions: list[PositionSizingDecision] = []
    daily_halt_decision: DailyHaltDecision | None = None

    if broker_adapter is not None:
        try:
            account_snapshot = broker_adapter.get_account_snapshot()
            raw_positions = broker_adapter.get_positions()
            raw_orders = broker_adapter.get_orders(status=OrderStatusFilter.ALL)
        except BrokerError:
            # Fail closed: mark all decisions as NOT_EVALUABLE with BROKER_STATE_UNAVAILABLE
            for index, decision in enumerate(strategy_decisions):
                gate = _fail_closed_gate(decision)
                risk_gate_decisions.append(gate)
                decision_journal_records.append(
                    build_risk_decision_record(
                        run_id=active_run_id,
                        decision_index=index,
                        decision=decision,
                        risk_decision=gate,
                        trading_date=current_date,
                        execution_mode=execution_mode,
                    )
                )
        else:
            risk_positions = [_to_risk_position(p) for p in raw_positions]
            risk_orders = [_to_risk_order(o) for o in raw_orders]

            daily_risk_state = _compute_daily_risk_state(account_snapshot, risk_orders, current_date)
            daily_halt_decision = evaluate_daily_halt(daily_risk_state, daily_halt_settings)

            for index, decision in enumerate(strategy_decisions):
                if daily_halt_decision.status == DailyHaltStatus.HALTED:
                    gate = _daily_halted_gate(decision, daily_halt_decision)
                    risk_gate_decisions.append(gate)
                    decision_journal_records.append(
                        build_risk_decision_record(
                            run_id=active_run_id,
                            decision_index=index,
                            decision=decision,
                            risk_decision=gate,
                            trading_date=current_date,
                            execution_mode=execution_mode,
                        )
                    )
                    continue

                gate = evaluate_risk_gate(
                    decision,
                    account_snapshot=account_snapshot,
                    order_proposal=_build_order_proposal(decision, options_chains, settings),
                    broker_positions=risk_positions,
                    broker_orders=risk_orders,
                    concentration_settings=concentration_settings,
                )
                risk_gate_decisions.append(gate)
                decision_journal_records.append(
                    build_risk_decision_record(
                        run_id=active_run_id,
                        decision_index=index,
                        decision=decision,
                        risk_decision=gate,
                        trading_date=current_date,
                        execution_mode=execution_mode,
                    )
                )

                if gate.status == RiskGateStatus.APPROVED:
                    sizing = size_position(
                        decision,
                        account_snapshot=account_snapshot,
                        proposal=_build_trade_proposal(decision, options_chains, settings),
                        broker_positions=risk_positions,
                        concentration_settings=concentration_settings,
                    )
                    sizing_decisions.append(sizing)
                    decision_journal_records.append(
                        build_position_sizing_record(
                            run_id=active_run_id,
                            decision_index=index,
                            decision=decision,
                            sizing_decision=sizing,
                            trading_date=current_date,
                            execution_mode=execution_mode,
                        )
                    )

    if journal_path is not None and (
        risk_gate_decisions or sizing_decisions
    ):
        risk_and_sizing_records = [
            record
            for record in decision_journal_records
            if record.record_type
            in {
                DecisionJournalRecordType.RISK_DECISION,
                DecisionJournalRecordType.POSITION_SIZING,
            }
        ]
        if risk_and_sizing_records:
            append_decision_journal_records(risk_and_sizing_records, journal_path)

    storage_errors = _append_storage_records(
        storage_writer=storage_writer,
        records=decision_journal_records,
        storage_write_policy=storage_write_policy,
    )
    alert_delivery_results = _dispatch_alert_records(
        alert_dispatcher=alert_dispatcher,
        records=decision_journal_records,
        alert_recipients=alert_recipients or [],
        alert_dry_run=alert_dry_run,
        alerts_allowed=_alerts_allowed(rollout_stage, rollout_settings),
    )

    return PipelineRunResult(
        strategy_decisions=strategy_decisions,
        sub_agent_packets=sub_agent_packets,
        claude_results=claude_results,
        journal_events=[*hot_path_events, *sub_agent_events, *cold_path_events],
        decision_journal_records=decision_journal_records,
        storage_errors=storage_errors,
        alert_delivery_results=alert_delivery_results,
        risk_gate_decisions=risk_gate_decisions,
        sizing_decisions=sizing_decisions,
        daily_halt_decision=daily_halt_decision,
    )


def _append_storage_records(
    *,
    storage_writer: object | None,
    records: Sequence[DecisionJournalRecord],
    storage_write_policy: object,
) -> list[object]:
    if storage_writer is None or not records:
        return []

    append_records = getattr(storage_writer, "append_decision_journal_records", None)
    if not callable(append_records):
        raise TypeError("storage_writer must implement append_decision_journal_records().")

    result = append_records(records)
    errors = list(getattr(result, "errors", []))
    if errors and _storage_policy_required(storage_write_policy):
        raise_if_required = getattr(result, "raise_if_required", None)
        if callable(raise_if_required):
            raise_if_required()
        raise RuntimeError("Required storage writes failed.")
    return errors


def _storage_policy_required(storage_write_policy: object) -> bool:
    value = getattr(storage_write_policy, "value", storage_write_policy)
    return str(value).lower() == "required"


def _dispatch_alert_records(
    *,
    alert_dispatcher: object | None,
    records: Sequence[DecisionJournalRecord],
    alert_recipients: Sequence[object],
    alert_dry_run: bool,
    alerts_allowed: bool,
) -> list[object]:
    if not alerts_allowed or alert_dispatcher is None or not records or not alert_recipients:
        return []

    dispatch_records = getattr(alert_dispatcher, "dispatch_records", None)
    if not callable(dispatch_records):
        raise TypeError("alert_dispatcher must implement dispatch_records().")

    return list(
        dispatch_records(
            list(records),
            list(alert_recipients),
            dry_run=alert_dry_run,
        )
    )


def _alerts_allowed(
    rollout_stage: RolloutStage | str | None,
    rollout_settings: RolloutSettings | None,
) -> bool:
    settings = rollout_settings or RolloutSettings()
    stage = rollout_stage or settings.default_stage
    return evaluate_rollout_capabilities(stage, settings).alerts_allowed


def _analyze_cold_path(
    *,
    decision: StrategyDecision,
    enable_claude_analysis: bool,
    claude_client: ClaudeCompletionClient | None,
    claude_settings: ClaudeAnalystSettings,
) -> ClaudeAnalysisResult:
    if not enable_claude_analysis or claude_client is None:
        return ClaudeAnalysisResult(
            status=ClaudeAnalysisStatus.SKIPPED,
            analysis=None,
            error_message="Claude analysis was not enabled or no client was provided.",
        )

    return analyze_strategy_decision(
        decision=decision,
        client=claude_client,
        settings=claude_settings,
    )


def _hot_path_event(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
) -> PipelineJournalEvent:
    target, theme = _target_and_theme(decision)
    return PipelineJournalEvent(
        event_type=PipelineJournalEventType.HOT_PATH_DECISION,
        run_id=run_id,
        decision_id=decision.audit_trail.decision_id,
        decision_type=DecisionType.STRATEGY_DECISION,
        decision_layer=DecisionLayer.SIGNAL,
        source_citations=decision.audit_trail.source_citations,
        decision_index=decision_index,
        target=target,
        theme=theme,
        strategy_status=decision.status,
        strategy_decision=decision,
        claude_result=None,
    )


def _cold_path_event(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    claude_result: ClaudeAnalysisResult,
) -> PipelineJournalEvent:
    target, theme = _target_and_theme(decision)
    return PipelineJournalEvent(
        event_type=PipelineJournalEventType.COLD_PATH_ANALYSIS,
        run_id=run_id,
        decision_type=DecisionType.CLAUDE_ANALYSIS,
        decision_layer=DecisionLayer.ANALYST,
        parent_decision_ids=[decision.audit_trail.decision_id],
        source_citations=decision.audit_trail.source_citations,
        decision_index=decision_index,
        target=target,
        theme=theme,
        strategy_status=decision.status,
        strategy_decision=None,
        sub_agent_packet=None,
        claude_result=claude_result,
    )


def _sub_agent_event(
    *,
    run_id: str,
    decision_index: int,
    decision: StrategyDecision,
    sub_agent_packet: SubAgentReviewPacket,
) -> PipelineJournalEvent:
    target, theme = _target_and_theme(decision)
    return PipelineJournalEvent(
        event_type=PipelineJournalEventType.SUB_AGENT_REVIEW,
        run_id=run_id,
        decision_type=DecisionType.SUB_AGENT_REVIEW,
        decision_layer=DecisionLayer.ANALYST,
        parent_decision_ids=[decision.audit_trail.decision_id],
        source_citations=decision.audit_trail.source_citations,
        decision_index=decision_index,
        target=target,
        theme=theme,
        strategy_status=decision.status,
        strategy_decision=None,
        sub_agent_packet=sub_agent_packet,
        claude_result=None,
    )


def _target_and_theme(decision: StrategyDecision) -> tuple[str, str | None]:
    if decision.candidate is not None:
        return decision.candidate.target, decision.candidate.theme

    return decision.audit.target, decision.audit.theme


def _target_data_for_decision(
    decision: StrategyDecision,
    target_market_data: Mapping[str, TargetMarketData] | None,
) -> TargetMarketData | None:
    if target_market_data is None:
        return None

    target, _ = _target_and_theme(decision)
    return target_market_data.get(target)


def _options_for_decision(
    decision: StrategyDecision,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
) -> list[OptionContractSnapshot]:
    if options_chains is None:
        return []

    target, _ = _target_and_theme(decision)
    return list(options_chains.get(target, []))


def _execution_mode(broker_adapter: BrokerAdapter | None) -> str | None:
    if broker_adapter is None:
        return None

    mode = getattr(broker_adapter, "execution_mode", None)
    if mode is None:
        return None
    if isinstance(mode, str):
        return mode
    value = getattr(mode, "value", None)
    return value if isinstance(value, str) else None


def _to_risk_position(bp: BrokerPosition) -> RiskPosition:
    return RiskPosition(
        symbol=bp.symbol,
        expression=bp.expression,
        qty=bp.qty,
        market_value=bp.market_value,
        average_entry_price=bp.average_entry_price,
    )


def _to_risk_order(bo: BrokerOrder) -> RiskOrder:
    return RiskOrder(
        order_id=bo.order_id,
        symbol=bo.symbol,
        qty=bo.qty,
        filled_qty=bo.filled_qty,
        limit_price=bo.limit_price,
        status=bo.status.value,
        submitted_at=bo.submitted_at,
        side=bo.side,
    )


def _fail_closed_gate(decision: StrategyDecision) -> RiskGateDecision:
    target, theme = _target_and_theme(decision)
    return RiskGateDecision(
        target=target,
        theme=theme,
        strategy_status=decision.status,
        status=RiskGateStatus.NOT_EVALUABLE,
        rejection_reasons=[RiskRejectionReason.BROKER_STATE_UNAVAILABLE],
        explanation="Broker state unavailable. Risk evaluation failed closed.",
        broker_execution_allowed=False,
        claude_present=False,
        claude_override_attempted=False,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.RISK_GATE,
            rule_name="risk_gatekeeper",
            target=target,
            theme=theme,
            passed=False,
            reason=RiskRejectionReason.BROKER_STATE_UNAVAILABLE.value,
        ),
    )


def _daily_halted_gate(
    decision: StrategyDecision,
    daily_halt: DailyHaltDecision,
) -> RiskGateDecision:
    target, theme = _target_and_theme(decision)
    return RiskGateDecision(
        target=target,
        theme=theme,
        strategy_status=decision.status,
        status=RiskGateStatus.BLOCKED,
        rejection_reasons=[RiskRejectionReason.STRATEGY_NOT_CANDIDATE_READY],
        explanation=f"Daily halt is active. Reasons: {', '.join(daily_halt.halt_reasons)}.",
        broker_execution_allowed=False,
        claude_present=False,
        claude_override_attempted=False,
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.RISK_GATE,
            rule_name="daily_halt",
            target=target,
            theme=theme,
            passed=False,
            reason="daily_halt_active",
        ),
    )


def _find_selected_option(
    candidate: CandidateBrief,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    settings: StrategySettings,
) -> OptionContractSnapshot | None:
    if not options_chains:
        return None
    chain = options_chains.get(candidate.target, [])
    max_expiration_date = candidate.earnings_date + timedelta(
        days=settings.max_option_expiration_days_after_earnings
    )
    for option in chain:
        if (
            option.ticker != candidate.target
            or option.option_type != "CALL"
            or option.expiration_date < candidate.earnings_date
            or option.expiration_date > max_expiration_date
        ):
            continue
        if (
            option.bid is not None
            and option.ask is not None
            and option.open_interest is not None
            and option.bid > 0
            and option.ask > 0
            and option.ask >= option.bid
            and option.open_interest >= settings.min_option_open_interest
        ):
            midpoint = (option.bid + option.ask) / 2
            spread_pct = ((option.ask - option.bid) / midpoint) * 100
            if spread_pct <= settings.max_options_bid_ask_spread_pct:
                return option
    return None


def _build_order_proposal(
    decision: StrategyDecision,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    settings: StrategySettings,
) -> RiskOrderProposal | None:
    if decision.candidate is None:
        return None
    target = decision.candidate.target
    expr = decision.candidate.recommended_expression

    if expr not in ("CALL_OPTION", "STOCK"):
        return None

    # Defaults
    estimated_entry_cost = 100.0
    maximum_loss = 100.0

    if expr == "CALL_OPTION" and options_chains:
        opt = _find_selected_option(decision.candidate, options_chains, settings)
        if opt is not None and opt.ask is not None:
            estimated_entry_cost = opt.ask * 100
            maximum_loss = opt.ask * 100

    return RiskOrderProposal(
        target=target,
        expression=expr,
        estimated_entry_cost=estimated_entry_cost,
        maximum_loss=maximum_loss,
    )


def _build_trade_proposal(
    decision: StrategyDecision,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    settings: StrategySettings,
) -> TradeProposal | None:
    if decision.candidate is None:
        return None
    target = decision.candidate.target
    expr = decision.candidate.recommended_expression

    if expr not in ("CALL_OPTION", "PUT_OPTION", "STOCK"):
        return None
    trade_expr = TradeExpression(expr)

    entry_price = 1.00
    stop_price = None

    if expr == "CALL_OPTION" and options_chains:
        opt = _find_selected_option(decision.candidate, options_chains, settings)
        if opt is not None and opt.ask is not None:
            entry_price = opt.ask
    elif expr == "STOCK":
        entry_price = 100.0
        stop_price = 90.0

    return TradeProposal(
        target=target,
        expression=trade_expr,
        entry_price=entry_price,
        stop_price=stop_price,
        contract_multiplier=100 if expr == "CALL_OPTION" else 1,
        minimum_quantity=1,
    )


def _compute_daily_risk_state(
    account_snapshot: AccountRiskSnapshot,
    orders: Sequence[RiskOrder],
    current_date: date,
) -> DailyRiskState:
    filled_today = [
        o for o in orders
        if o.status == "filled" and o.submitted_at.date() == current_date and o.filled_qty > 0
    ]

    by_symbol: dict[str, list[RiskOrder]] = {}
    for o in filled_today:
        by_symbol.setdefault(o.symbol.upper(), []).append(o)

    realized_pnl = 0.0
    losing_trade_count = 0

    for symbol, sym_orders in by_symbol.items():
        buys = []
        sells = []
        for o in sym_orders:
            side = o.side.lower() if hasattr(o, "side") and o.side else "buy"
            if side == "buy":
                buys.append(o)
            elif side == "sell":
                sells.append(o)

        buy_idx = 0
        sell_idx = 0
        buy_rem = buys[buy_idx].filled_qty if buy_idx < len(buys) else 0
        sell_rem = sells[sell_idx].filled_qty if sell_idx < len(sells) else 0

        while buy_idx < len(buys) and sell_idx < len(sells):
            match_qty = min(buy_rem, sell_rem)
            buy_price = buys[buy_idx].limit_price or 0.0
            sell_price = sells[sell_idx].limit_price or 0.0
            pnl = (sell_price - buy_price) * match_qty
            realized_pnl += pnl
            if pnl < 0:
                losing_trade_count += 1

            buy_rem -= match_qty
            sell_rem -= match_qty

            if buy_rem == 0:
                buy_idx += 1
                if buy_idx < len(buys):
                    buy_rem = buys[buy_idx].filled_qty
            if sell_rem == 0:
                sell_idx += 1
                if sell_idx < len(sells):
                    sell_rem = sells[sell_idx].filled_qty

    return DailyRiskState(
        account_equity=account_snapshot.equity,
        trading_day=current_date,
        realized_pnl=round(realized_pnl, 2),
        losing_trade_count=losing_trade_count,
    )
