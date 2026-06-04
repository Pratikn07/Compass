from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

from prescient.events.classifier import classify_event, duplicate_classification
from prescient.events.models import EventTriggerResult, NormalizedEvent
from prescient.runtime import pipeline as runtime_pipeline
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategySettings,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.strategy_types import PreferredExpression


_DEFAULT_STRATEGY_SETTINGS = StrategySettings()


def handle_event_trigger(
    *,
    event: NormalizedEvent,
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    peer_results: list[PeerResult],
    target_market_data: Mapping[str, TargetMarketData] | None,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    current_date: date,
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None = None,
    active_tickers: Collection[str] | None = None,
    processed_fingerprints: set[str] | None = None,
    settings: StrategySettings = _DEFAULT_STRATEGY_SETTINGS,
    preferred_expression: PreferredExpression = "CALL_OPTION",
    enable_claude_analysis: bool = False,
    claude_client: object | None = None,
    claude_settings: object | None = None,
    journal_path: str | Path | None = None,
) -> EventTriggerResult:
    classification = classify_event(
        event,
        universe=universe,
        active_tickers=active_tickers,
    )

    if processed_fingerprints is not None and event.fingerprint in processed_fingerprints:
        classification = duplicate_classification(classification)

    if not classification.should_refresh_strategy:
        return EventTriggerResult(classification=classification, runtime_result=None)

    if claude_settings is None:
        runtime_result = runtime_pipeline.run_hot_cold_strategy_pipeline(
            universe=universe,
            upcoming_events=upcoming_events,
            peer_results=peer_results,
            target_market_data=target_market_data,
            options_chains=options_chains,
            current_date=current_date,
            indicator_snapshots=indicator_snapshots,
            settings=settings,
            preferred_expression=preferred_expression,
            enable_claude_analysis=enable_claude_analysis,
            claude_client=cast(Any, claude_client),
            journal_path=journal_path,
        )
    else:
        runtime_result = runtime_pipeline.run_hot_cold_strategy_pipeline(
            universe=universe,
            upcoming_events=upcoming_events,
            peer_results=peer_results,
            target_market_data=target_market_data,
            options_chains=options_chains,
            current_date=current_date,
            indicator_snapshots=indicator_snapshots,
            settings=settings,
            preferred_expression=preferred_expression,
            enable_claude_analysis=enable_claude_analysis,
            claude_client=cast(Any, claude_client),
            claude_settings=cast(Any, claude_settings),
            journal_path=journal_path,
        )

    if processed_fingerprints is not None:
        processed_fingerprints.add(event.fingerprint)

    return EventTriggerResult(
        classification=classification,
        runtime_result=runtime_result,
    )
