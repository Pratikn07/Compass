from __future__ import annotations

from datetime import date, timedelta

from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    EarningsCalendarEvent,
    EarningsCandidateDecision,
    EarningsEvent,
    StrategyUniverse,
    ThemeConfig,
)


DEFAULT_EARNINGS_WINDOW_DAYS = 1
DEFAULT_PEER_RESULT_WINDOW_DAYS = 21
DEFAULT_MIN_REPORTED_PEERS = 3


def detect_earnings_candidates(
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    completed_events: list[EarningsEvent],
    current_date: date,
    earnings_window_days: int = DEFAULT_EARNINGS_WINDOW_DAYS,
    peer_result_window_days: int = DEFAULT_PEER_RESULT_WINDOW_DAYS,
    min_reported_peers: int = DEFAULT_MIN_REPORTED_PEERS,
) -> list[EarningsCandidateDecision]:
    decisions: list[EarningsCandidateDecision] = []

    for event in upcoming_events:
        themes = universe.themes_for_ticker(event.ticker)
        if not themes:
            decisions.append(
                _decision(
                    event=event,
                    theme=None,
                    status=CandidateDetectionStatus.REJECTED,
                    reported_peers=[],
                    rejection_reasons=[CandidateRejectionReason.THEME_NOT_CONFIGURED],
                )
            )
            continue

        for theme in themes:
            decisions.append(
                _detect_for_theme(
                    event=event,
                    theme=theme,
                    completed_events=completed_events,
                    current_date=current_date,
                    earnings_window_days=earnings_window_days,
                    peer_result_window_days=peer_result_window_days,
                    min_reported_peers=min_reported_peers,
                )
            )

    return decisions


def _detect_for_theme(
    event: EarningsCalendarEvent,
    theme: ThemeConfig,
    completed_events: list[EarningsEvent],
    current_date: date,
    earnings_window_days: int,
    peer_result_window_days: int,
    min_reported_peers: int,
) -> EarningsCandidateDecision:
    if event.earnings_date is None:
        return _decision(
            event=event,
            theme=theme,
            status=CandidateDetectionStatus.REJECTED,
            reported_peers=[],
            rejection_reasons=[CandidateRejectionReason.EARNINGS_DATE_MISSING],
        )

    if not _inside_earnings_window(event.earnings_date, current_date, earnings_window_days):
        return _decision(
            event=event,
            theme=theme,
            status=CandidateDetectionStatus.REJECTED,
            reported_peers=[],
            rejection_reasons=[CandidateRejectionReason.OUTSIDE_EARNINGS_WINDOW],
        )

    reported_peers = _qualified_reported_peers(
        target=event.ticker,
        theme=theme,
        completed_events=completed_events,
        current_date=current_date,
        target_earnings_date=event.earnings_date,
        peer_result_window_days=peer_result_window_days,
    )

    if len(reported_peers) < min_reported_peers:
        return _decision(
            event=event,
            theme=theme,
            status=CandidateDetectionStatus.REJECTED,
            reported_peers=reported_peers,
            rejection_reasons=[CandidateRejectionReason.INSUFFICIENT_REPORTED_PEERS],
        )

    return _decision(
        event=event,
        theme=theme,
        status=CandidateDetectionStatus.CANDIDATE,
        reported_peers=reported_peers,
        rejection_reasons=[],
    )


def _inside_earnings_window(
    earnings_date: date,
    current_date: date,
    earnings_window_days: int,
) -> bool:
    return current_date <= earnings_date <= current_date + timedelta(days=earnings_window_days)


def _qualified_reported_peers(
    target: str,
    theme: ThemeConfig,
    completed_events: list[EarningsEvent],
    current_date: date,
    target_earnings_date: date,
    peer_result_window_days: int,
) -> list[str]:
    seen: set[str] = set()
    peers: list[str] = []

    for event in completed_events:
        if event.ticker in seen:
            continue
        if not _is_qualified_peer(
            event=event,
            target=target,
            theme=theme,
            current_date=current_date,
            target_earnings_date=target_earnings_date,
            peer_result_window_days=peer_result_window_days,
        ):
            continue
        seen.add(event.ticker)
        peers.append(event.ticker)

    return peers


def _is_qualified_peer(
    event: EarningsEvent,
    target: str,
    theme: ThemeConfig,
    current_date: date,
    target_earnings_date: date,
    peer_result_window_days: int,
) -> bool:
    return (
        event.ticker != target
        and event.ticker in theme.tickers
        and event.earnings_date < target_earnings_date
        and event.earnings_date <= current_date
        and current_date - event.earnings_date <= timedelta(days=peer_result_window_days)
    )


def _decision(
    event: EarningsCalendarEvent,
    theme: ThemeConfig | None,
    status: CandidateDetectionStatus,
    reported_peers: list[str],
    rejection_reasons: list[CandidateRejectionReason],
) -> EarningsCandidateDecision:
    return EarningsCandidateDecision(
        target=event.ticker,
        theme=theme.name if theme is not None else None,
        status=status,
        earnings_date=event.earnings_date,
        report_time=event.report_time,
        reported_peers=reported_peers,
        rejection_reasons=rejection_reasons,
    )
