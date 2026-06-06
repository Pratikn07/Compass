from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement


def _bar(t, d, c):
    return DailyBarSnapshot(ticker=t, trading_date=d, close=c)


def test_excludes_peer_reporting_on_or_after_target_as_of() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    target_as_of = date(2024, 6, 25)
    anns = [
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                             surprise_pct=8.0),
        EarningsAnnouncement(ticker="AVGO", report_date=date(2024, 6, 26),
                             surprise_pct=5.0),
    ]
    bars = {
        "NVDA": [
            _bar("NVDA", date(2024, 6, 11), 100.0),
            _bar("NVDA", date(2024, 6, 12), 101.0),
            _bar("NVDA", date(2024, 6, 13), 106.0),
        ],
    }
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=target_as_of, announcements=anns,
        bars=bars, peer_window_days=21,
    )
    assert "NVDA" in surprises and "AVGO" not in surprises
    assert surprises["NVDA"] == 8.0
    assert reactions["NVDA"] == 6.0


def test_excludes_peer_outside_trailing_window() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 5, 1),
                             surprise_pct=8.0),
    ]
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises == {} and reactions == {}


def test_target_itself_never_a_peer() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 12),
                                 surprise_pct=3.0)]
    surprises, _ = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises == {}


def test_surprise_computed_from_eps_when_pct_absent() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                                 eps_estimate=1.0, eps_actual=1.1)]
    surprises, _ = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert round(surprises["NVDA"], 4) == 10.0


def test_peer_omitted_when_reaction_bars_missing() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                                 surprise_pct=8.0)]
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises["NVDA"] == 8.0
    assert "NVDA" not in reactions
