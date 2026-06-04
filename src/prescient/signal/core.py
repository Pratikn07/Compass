from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from prescient.signal.candidate import detect_earnings_candidates
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyDecision,
    StrategySettings,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.peer_scoring import aggregate_peer_scores, score_peer_result
from prescient.signal.strategy_output import build_strategy_decision
from prescient.signal.strategy_types import PreferredExpression


_DEFAULT_SETTINGS = StrategySettings()


def evaluate_core_strategy(
    *,
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    peer_results: list[PeerResult],
    target_market_data: Mapping[str, TargetMarketData] | None,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
    current_date: date,
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None = None,
    settings: StrategySettings = _DEFAULT_SETTINGS,
    preferred_expression: PreferredExpression = "CALL_OPTION",
) -> list[StrategyDecision]:
    peer_result_by_ticker = _first_peer_result_by_ticker(peer_results)
    completed_events = [peer.earnings_event for peer in peer_results]

    candidate_decisions = detect_earnings_candidates(
        universe=universe,
        upcoming_events=upcoming_events,
        completed_events=completed_events,
        current_date=current_date,
        earnings_window_days=settings.earnings_window_days,
        peer_result_window_days=settings.peer_result_window_days,
        min_reported_peers=settings.min_reported_peers,
    )

    strategy_decisions: list[StrategyDecision] = []
    for candidate in candidate_decisions:
        peer_scores = [
            score_peer_result(peer_result_by_ticker[ticker], settings=settings)
            for ticker in candidate.reported_peers
            if ticker in peer_result_by_ticker
        ]
        peer_signal = aggregate_peer_scores(peer_scores, settings=settings)

        peer_summaries = [
            summary
            for ticker in candidate.reported_peers
            if ticker in peer_result_by_ticker
            for summary in [peer_result_by_ticker[ticker].transcript_summary]
            if summary is not None
        ]

        strategy_decisions.append(
            build_strategy_decision(
                candidate=candidate,
                peer_signal=peer_signal,
                target=_target_data_for(candidate.target, target_market_data),
                indicator_snapshot=_indicator_snapshot_for(
                    candidate.target,
                    indicator_snapshots,
                ),
                options_chain=_options_chain_for(candidate.target, options_chains),
                preferred_expression=preferred_expression,
                settings=settings,
                peer_summaries=peer_summaries,
            )
        )

    return strategy_decisions


def _first_peer_result_by_ticker(peer_results: list[PeerResult]) -> dict[str, PeerResult]:
    results: dict[str, PeerResult] = {}
    for peer in peer_results:
        results.setdefault(peer.ticker, peer)
    return results


def _target_data_for(
    ticker: str,
    target_market_data: Mapping[str, TargetMarketData] | None,
) -> TargetMarketData | None:
    if target_market_data is None:
        return None
    return target_market_data.get(ticker)


def _indicator_snapshot_for(
    ticker: str,
    indicator_snapshots: Mapping[str, TechnicalIndicatorSnapshot] | None,
) -> TechnicalIndicatorSnapshot | None:
    if indicator_snapshots is None:
        return None
    return indicator_snapshots.get(ticker)


def _options_chain_for(
    ticker: str,
    options_chains: Mapping[str, list[OptionContractSnapshot]] | None,
) -> list[OptionContractSnapshot]:
    if options_chains is None:
        return []
    return options_chains.get(ticker, [])
