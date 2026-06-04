from __future__ import annotations

from datetime import date, timedelta

from prescient.scheduler.models import ScheduleTriggerType, ScheduledRunRequest
from prescient.signal.models import (
    EarningsCalendarEvent,
    PeerResult,
    StrategySettings,
    StrategyUniverse,
)


_DEFAULT_SETTINGS = StrategySettings()


def derive_scheduled_run_requests(
    *,
    universe: StrategyUniverse,
    upcoming_events: list[EarningsCalendarEvent],
    peer_results: list[PeerResult],
    current_date: date,
    settings: StrategySettings = _DEFAULT_SETTINGS,
    trigger_type: ScheduleTriggerType = ScheduleTriggerType.SCHEDULED,
) -> list[ScheduledRunRequest]:
    window_start = current_date
    window_end = current_date + timedelta(days=settings.earnings_window_days)
    peer_window_start = current_date - timedelta(days=settings.peer_result_window_days)

    relevant_tickers = {
        event.ticker
        for event in upcoming_events
        if _is_relevant_upcoming_event(
            event=event,
            universe=universe,
            window_start=window_start,
            window_end=window_end,
        )
    }
    relevant_tickers.update(
        peer.ticker
        for peer in peer_results
        if _is_relevant_peer_result(
            peer=peer,
            universe=universe,
            window_start=peer_window_start,
            window_end=current_date,
        )
    )

    if not relevant_tickers:
        return []

    return [
        ScheduledRunRequest(
            run_id=f"{trigger_type.value}:{current_date.isoformat()}",
            trigger_type=trigger_type,
            scheduled_date=current_date,
            current_date=current_date,
            window_start=window_start,
            window_end=window_end,
            relevant_tickers=sorted(relevant_tickers),
        )
    ]


def _is_relevant_upcoming_event(
    *,
    event: EarningsCalendarEvent,
    universe: StrategyUniverse,
    window_start: date,
    window_end: date,
) -> bool:
    return (
        event.earnings_date is not None
        and universe.contains_ticker(event.ticker)
        and window_start <= event.earnings_date <= window_end
    )


def _is_relevant_peer_result(
    *,
    peer: PeerResult,
    universe: StrategyUniverse,
    window_start: date,
    window_end: date,
) -> bool:
    earnings_date = peer.earnings_event.earnings_date
    return universe.contains_ticker(peer.ticker) and window_start <= earnings_date <= window_end
