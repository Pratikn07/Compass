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
    assert result.drop_reasons.get("no_prior_bar", 0) == 1


def test_non_target_announcements_are_not_counted_or_assembled() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    # NVDA is present as an announcement but NOT in target_tickers -> it must not be
    # a target event (not counted in events_total, no context built for it).
    announcements = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26),
                             surprise_pct=20.8),
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                             surprise_pct=8.0),
    ]
    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 25), 100.0),
            _bar("MU", date(2024, 6, 26), 103.0),
            _bar("MU", date(2024, 6, 27), 106.0),
        ],
    }
    option_quotes = {"MU": _straddle("MU", date(2024, 6, 25))}
    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    # only MU is a target -> events_total counts 1, and the single context is MU
    assert result.events_total == 1
    assert [c.ticker for c in result.event_contexts] == ["MU"]


def test_as_of_anchors_to_prior_trading_day_for_monday_report() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    # MU reports Monday 2024-07-01. report_date-1 = Sunday 2024-06-30 (no bar).
    # as_of must anchor to Friday 2024-06-28 (last trading day <= 06-30), and the
    # event must remain evaluable (realized move computed from the as_of trading day).
    announcements = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 7, 1),
                             surprise_pct=10.0),
    ]
    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 27), 98.0),
            _bar("MU", date(2024, 6, 28), 100.0),   # Friday = real prior trading day
            _bar("MU", date(2024, 7, 1), 103.0),
            _bar("MU", date(2024, 7, 2), 106.0),     # horizon 2 -> +6%
        ],
    }
    option_quotes = {"MU": _straddle("MU", date(2024, 6, 28))}
    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    assert len(result.event_contexts) == 1
    ctx = result.event_contexts[0]
    assert ctx.as_of_date == date(2024, 6, 28)   # Friday, not Sunday 06-30
    assert ctx.underlying_price == 100.0
    assert ctx.realized_move is not None          # not silently dropped


def _vol_ramp_quotes(t, entry_d, exit_d):
    def q(ot, d, close):
        return OptionQuote(ticker=t, option_type=ot, strike=100.0,
                           expiration_date=date(2024, 6, 28), quote_date=d,
                           bid=close, ask=close)

    return [
        q("CALL", entry_d, 2.0), q("PUT", entry_d, 2.1),
        q("CALL", exit_d, 3.0), q("PUT", exit_d, 3.2),
    ]


def _mu_announcement_and_data():
    announcements = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26),
                             surprise_pct=20.8),
    ]
    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 18), 98.0),
            _bar("MU", date(2024, 6, 24), 99.0),
            _bar("MU", date(2024, 6, 25), 100.0),
            _bar("MU", date(2024, 6, 26), 103.0),
            _bar("MU", date(2024, 6, 27), 106.0),
        ],
    }
    option_quotes = {"MU": _straddle("MU", date(2024, 6, 25))}
    return announcements, bars, option_quotes


def test_assembler_threads_vol_ramp_quotes_into_context() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements, bars, option_quotes = _mu_announcement_and_data()
    entry_d, exit_d = date(2024, 6, 18), date(2024, 6, 25)
    vol_ramp = {("MU", date(2024, 6, 26)): _vol_ramp_quotes("MU", entry_d, exit_d)}

    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
        vol_ramp_quotes=vol_ramp,
    )
    assert len(result.event_contexts) == 1
    ctx = result.event_contexts[0]
    assert ctx.entry_as_of_date == entry_d
    assert ctx.vol_ramp_entry_call is not None
    assert ctx.vol_ramp_entry_call.bid == 2.0
    assert ctx.vol_ramp_entry_put.bid == 2.1
    assert ctx.vol_ramp_exit_call.bid == 3.0
    assert ctx.vol_ramp_exit_put.bid == 3.2
    # No-lookahead invariant: entry strictly before exit, exit before earnings.
    assert ctx.entry_as_of_date < ctx.as_of_date < ctx.earnings_date
    # Existing exit-ATM quotes are untouched.
    assert ctx.atm_call is not None and ctx.atm_call.bid == 3.9


def test_assembler_without_vol_ramp_quotes_is_unchanged() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements, bars, option_quotes = _mu_announcement_and_data()
    kwargs = dict(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    default_run = assemble_edge_dataset(**kwargs)
    explicit_none = assemble_edge_dataset(**kwargs, vol_ramp_quotes=None)
    assert default_run.event_contexts == explicit_none.event_contexts
    ctx = default_run.event_contexts[0]
    assert ctx.entry_as_of_date is None
    assert ctx.vol_ramp_entry_call is None


def test_assembler_event_without_vol_ramp_entry_gets_none_fields() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements, bars, option_quotes = _mu_announcement_and_data()
    vol_ramp = {("OTHER", date(2024, 6, 26)): _vol_ramp_quotes(
        "OTHER", date(2024, 6, 18), date(2024, 6, 25),
    )}
    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
        vol_ramp_quotes=vol_ramp,
    )
    ctx = result.event_contexts[0]
    assert ctx.entry_as_of_date is None
    assert ctx.vol_ramp_entry_call is None


def test_as_of_price_for_returns_prior_trading_day_and_close() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 27), 98.0),
            _bar("MU", date(2024, 6, 28), 100.0),  # Friday: prior trading day to 07-01
            _bar("MU", date(2024, 7, 1), 103.0),
        ]
    }
    # report Monday 2024-07-01 -> calendar prior Sunday 06-30 -> last trading day 06-28
    result = as_of_price_for("MU", date(2024, 7, 1), bars)
    assert result == (date(2024, 6, 28), 100.0)


def test_as_of_price_for_none_when_no_prior_bar() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    assert as_of_price_for("MU", date(2024, 7, 1), {}) is None


def test_as_of_price_for_none_when_close_missing() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    bars = {"MU": [_bar("MU", date(2024, 6, 28), None)]}
    assert as_of_price_for("MU", date(2024, 7, 1), bars) is None
