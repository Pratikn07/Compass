from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from prescient.analyst.claude import ClaudeCompletionClient
from prescient.analyst.models import ClaudeAnalystSettings
from prescient.rollout import RolloutSettings, RolloutStage
from prescient.runtime import pipeline as runtime_pipeline
from prescient.runtime.models import PipelineRunResult
from prescient.scheduler.models import (
    ScheduledPipelineRunResult,
    ScheduledRunRequest,
    ScheduledRunSummary,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategySettings,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.strategy_types import PreferredExpression


_DEFAULT_STRATEGY_SETTINGS = StrategySettings()
_DEFAULT_CLAUDE_SETTINGS = ClaudeAnalystSettings()


def run_scheduled_strategy_pipeline(
    *,
    request: ScheduledRunRequest,
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    peer_results: list[PeerResult],
    target_market_data: Mapping[str, TargetMarketData] | None,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None = None,
    settings: StrategySettings = _DEFAULT_STRATEGY_SETTINGS,
    preferred_expression: PreferredExpression = "CALL_OPTION",
    enable_claude_analysis: bool = False,
    claude_client: ClaudeCompletionClient | None = None,
    claude_settings: ClaudeAnalystSettings = _DEFAULT_CLAUDE_SETTINGS,
    journal_path: str | Path | None = None,
    storage_writer: object | None = None,
    storage_write_policy: object = "optional",
    alert_dispatcher: object | None = None,
    alert_recipients: Sequence[object] | None = None,
    alert_dry_run: bool = False,
    rollout_stage: RolloutStage | str | None = None,
    rollout_settings: RolloutSettings | None = None,
) -> ScheduledPipelineRunResult:
    runtime_result = runtime_pipeline.run_hot_cold_strategy_pipeline(
        universe=universe,
        upcoming_events=upcoming_events,
        peer_results=peer_results,
        target_market_data=target_market_data,
        options_chains=options_chains,
        current_date=request.current_date,
        indicator_snapshots=indicator_snapshots,
        settings=settings,
        preferred_expression=preferred_expression,
        enable_claude_analysis=enable_claude_analysis,
        claude_client=claude_client,
        claude_settings=claude_settings,
        journal_path=journal_path,
        storage_writer=storage_writer,
        storage_write_policy=storage_write_policy,
        alert_dispatcher=alert_dispatcher,
        alert_recipients=alert_recipients,
        alert_dry_run=alert_dry_run,
        rollout_stage=rollout_stage,
        rollout_settings=rollout_settings,
        run_id=request.run_id,
    )

    return ScheduledPipelineRunResult(
        request=request,
        runtime_result=runtime_result,
        summary=_build_summary(
            request=request,
            runtime_result=runtime_result,
            upcoming_event_count=len(upcoming_events),
            journal_path=journal_path,
            enable_claude_analysis=enable_claude_analysis,
        ),
    )


def _build_summary(
    *,
    request: ScheduledRunRequest,
    runtime_result: PipelineRunResult,
    upcoming_event_count: int,
    journal_path: str | Path | None,
    enable_claude_analysis: bool,
) -> ScheduledRunSummary:
    decisions = runtime_result.strategy_decisions

    return ScheduledRunSummary(
        run_id=request.run_id,
        trigger_type=request.trigger_type,
        scheduled_date=request.scheduled_date,
        current_date=request.current_date,
        window_start=request.window_start,
        window_end=request.window_end,
        upcoming_event_count=upcoming_event_count,
        total_decision_count=len(decisions),
        candidate_ready_count=sum(
            decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
            for decision in decisions
        ),
        rejected_count=sum(
            decision.status == StrategyStatus.REJECTED_WITH_REASON for decision in decisions
        ),
        no_trade_count=sum(decision.status == StrategyStatus.NO_TRADE for decision in decisions),
        journal_path=str(journal_path) if journal_path is not None else None,
        claude_analysis_enabled=enable_claude_analysis,
    )
