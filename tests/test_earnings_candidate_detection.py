from __future__ import annotations

from datetime import date

from prescient.signal.candidate import detect_earnings_candidates
from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    EarningsCalendarEvent,
    EarningsEvent,
    StrategyUniverse,
    ThemeConfig,
)


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTAP", "PSTG", "WDC", "STX", "NTNX"],
                drivers=[],
            ),
            ThemeConfig(
                name="ENTERPRISE_HARDWARE",
                tickers=["NTAP", "DELL", "HPE", "IBM"],
                drivers=[],
            ),
        ]
    )


def _calendar_event(ticker: str, earnings_date: date | None) -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker=ticker,
        earnings_date=earnings_date,
        report_time="AMC",
    )


def _completed_event(ticker: str, earnings_date: date) -> EarningsEvent:
    return EarningsEvent(
        ticker=ticker,
        earnings_date=earnings_date,
        report_time="AMC",
        eps_estimate=1.0,
        eps_actual=1.1,
    )


def test_default_window_finds_target_reporting_today_or_tomorrow() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[
            _calendar_event("NTNX", date(2026, 6, 1)),
            _calendar_event("NTAP", date(2026, 6, 2)),
        ],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 20)),
            _completed_event("PSTG", date(2026, 5, 21)),
            _completed_event("WDC", date(2026, 5, 22)),
            _completed_event("STX", date(2026, 5, 23)),
            _completed_event("DELL", date(2026, 5, 24)),
            _completed_event("HPE", date(2026, 5, 25)),
            _completed_event("IBM", date(2026, 5, 26)),
        ],
        current_date=date(2026, 6, 1),
    )

    candidate_pairs = {
        (decision.target, decision.theme)
        for decision in decisions
        if decision.status == CandidateDetectionStatus.CANDIDATE
    }

    assert candidate_pairs == {
        ("NTNX", "AI_STORAGE"),
        ("NTAP", "AI_STORAGE"),
        ("NTAP", "ENTERPRISE_HARDWARE"),
    }


def test_outside_window_target_is_rejected() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 3))],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 20)),
            _completed_event("PSTG", date(2026, 5, 21)),
            _completed_event("WDC", date(2026, 5, 22)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.REJECTED
    assert decisions[0].rejection_reasons == [CandidateRejectionReason.OUTSIDE_EARNINGS_WINDOW]


def test_missing_earnings_date_is_rejected() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", None)],
        completed_events=[],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.REJECTED
    assert decisions[0].rejection_reasons == [CandidateRejectionReason.EARNINGS_DATE_MISSING]


def test_out_of_universe_ticker_is_rejected() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NVDA", date(2026, 6, 1))],
        completed_events=[],
        current_date=date(2026, 6, 1),
    )

    assert [decision.model_dump() for decision in decisions] == [
        {
            "target": "NVDA",
            "theme": None,
            "status": CandidateDetectionStatus.REJECTED,
            "earnings_date": date(2026, 6, 1),
            "report_time": "AMC",
            "reported_peers": [],
            "rejection_reasons": [CandidateRejectionReason.THEME_NOT_CONFIGURED],
        }
    ]


def test_target_with_at_least_three_recent_same_theme_peers_becomes_candidate() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 20)),
            _completed_event("PSTG", date(2026, 5, 21)),
            _completed_event("WDC", date(2026, 5, 22)),
            _completed_event("DELL", date(2026, 5, 20)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.CANDIDATE
    assert decisions[0].target == "NTNX"
    assert decisions[0].theme == "AI_STORAGE"
    assert decisions[0].reported_peers == ["NTAP", "PSTG", "WDC"]
    assert decisions[0].rejection_reasons == []


def test_target_with_fewer_than_minimum_reported_peers_is_rejected() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 20)),
            _completed_event("PSTG", date(2026, 5, 21)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.REJECTED
    assert decisions[0].reported_peers == ["NTAP", "PSTG"]
    assert decisions[0].rejection_reasons == [
        CandidateRejectionReason.INSUFFICIENT_REPORTED_PEERS
    ]


def test_peer_events_outside_peer_result_window_are_ignored() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 10)),
            _completed_event("PSTG", date(2026, 5, 21)),
            _completed_event("WDC", date(2026, 5, 22)),
            _completed_event("STX", date(2026, 5, 23)),
        ],
        current_date=date(2026, 6, 1),
        peer_result_window_days=21,
    )

    assert decisions[0].status == CandidateDetectionStatus.CANDIDATE
    assert decisions[0].reported_peers == ["PSTG", "WDC", "STX"]


def test_peer_events_after_or_on_target_earnings_date_are_ignored() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTAP", date(2026, 6, 2)),
            _completed_event("PSTG", date(2026, 6, 3)),
            _completed_event("WDC", date(2026, 5, 22)),
            _completed_event("STX", date(2026, 5, 23)),
        ],
        current_date=date(2026, 6, 1),
        min_reported_peers=2,
    )

    assert decisions[0].status == CandidateDetectionStatus.CANDIDATE
    assert decisions[0].reported_peers == ["WDC", "STX"]


def test_target_ticker_is_never_counted_as_its_own_peer() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTNX", date(2026, 5, 20)),
            _completed_event("NTAP", date(2026, 5, 21)),
            _completed_event("PSTG", date(2026, 5, 22)),
            _completed_event("WDC", date(2026, 5, 23)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.CANDIDATE
    assert decisions[0].reported_peers == ["NTAP", "PSTG", "WDC"]


def test_duplicate_peer_events_are_counted_once_preserving_input_order() -> None:
    decisions = detect_earnings_candidates(
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        completed_events=[
            _completed_event("NTAP", date(2026, 5, 20)),
            _completed_event("PSTG", date(2026, 5, 21)),
            _completed_event("NTAP", date(2026, 5, 22)),
            _completed_event("WDC", date(2026, 5, 23)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == CandidateDetectionStatus.CANDIDATE
    assert decisions[0].reported_peers == ["NTAP", "PSTG", "WDC"]
