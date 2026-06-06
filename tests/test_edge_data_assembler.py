from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def _bar(t, d, c):
    return DailyBarSnapshot(ticker=t, trading_date=d, close=c)


def _straddle(t, qd):
    return [
        OptionQuote(ticker=t, option_type="CALL", strike=100.0,
                    expiration_date=date(2024, 6, 28), quote_date=qd, bid=3.9, ask=4.1),
        OptionQuote(ticker=t, option_type="PUT", strike=100.0,
                    expiration_date=date(2024, 6, 28), quote_date=qd, bid=3.9, ask=4.1),
    ]


def test_assembles_context_with_peer_signals_and_drops_uncovered() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26),
                             eps_estimate=1.2, eps_actual=1.45, surprise_pct=20.8),
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                             surprise_pct=8.0),
        EarningsAnnouncement(ticker="GHOST", report_date=date(2024, 6, 20)),
    ]
    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 24), 99.0),
            _bar("MU", date(2024, 6, 25), 100.0),
            _bar("MU", date(2024, 6, 26), 103.0),
            _bar("MU", date(2024, 6, 27), 106.0),
        ],
        "NVDA": [
            _bar("NVDA", date(2024, 6, 11), 100.0),
            _bar("NVDA", date(2024, 6, 13), 106.0),
        ],
    }
    option_quotes = {"MU": _straddle("MU", date(2024, 6, 25))}

    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    assert len(result.event_contexts) == 1
    ctx = result.event_contexts[0]
    assert ctx.ticker == "MU"
    assert ctx.as_of_date == date(2024, 6, 25)
    assert ctx.underlying_price == 100.0
    assert ctx.peer_eps_surprises == {"NVDA": 8.0}
    assert ctx.peer_stock_reactions == {"NVDA": 6.0}
    assert ctx.realized_move is not None


def test_drops_event_without_asof_price() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    result = assemble_edge_dataset(
        announcements=announcements, bars={}, option_quotes={},
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    assert result.event_contexts == []
    assert result.events_dropped == 1
    assert result.drop_reasons.get("no_event_context", 0) == 1
