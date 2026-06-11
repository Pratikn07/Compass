from __future__ import annotations

from datetime import date

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


class FakeHistAdapter:
    def __init__(self):
        self.calls = []

    def get_historical_atm_straddle(self, *, underlying_symbol, as_of_date,
                                    underlying_price, earnings_date, max_expiration_date):
        self.calls.append({
            "symbol": underlying_symbol, "as_of_date": as_of_date,
            "underlying_price": underlying_price, "earnings_date": earnings_date,
            "max_expiration_date": max_expiration_date,
        })
        return [
            OptionQuote(ticker=underlying_symbol, option_type="CALL", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=as_of_date,
                        bid=9.0, ask=9.0),
            OptionQuote(ticker=underlying_symbol, option_type="PUT", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=as_of_date,
                        bid=8.0, ask=8.0),
        ]


def test_loads_straddle_per_event_threading_as_of_price() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    as_of_prices = {("MU", date(2024, 6, 26)): (date(2024, 6, 25), 141.12)}
    adapter = FakeHistAdapter()
    out = load_option_quotes_for_events(
        adapter, events=events, as_of_prices=as_of_prices, max_expiration_days=14,
    )
    assert len(out["MU"]) == 2
    call = adapter.calls[0]
    assert call["as_of_date"] == date(2024, 6, 25)
    assert call["underlying_price"] == 141.12
    assert call["max_expiration_date"] == date(2024, 7, 10)  # report + 14d


def test_skips_event_without_as_of_price() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    adapter = FakeHistAdapter()
    out = load_option_quotes_for_events(
        adapter, events=events, as_of_prices={}, max_expiration_days=14,
    )
    assert out == {}
    assert adapter.calls == []


def _bar(ticker, trading_date, close):
    from prescient.data.models import DailyBarSnapshot

    return DailyBarSnapshot(
        ticker=ticker, trading_date=trading_date,
        open=close, high=close, low=close, close=close, volume=1000,
    )


def _mu_bars():
    # Ten trading days ending at the exit as-of (2024-06-25). With
    # entry_lead_trading_days=5, the entry day is 2024-06-17 (6th from the end).
    days = [
        date(2024, 6, 11), date(2024, 6, 12), date(2024, 6, 13),
        date(2024, 6, 14), date(2024, 6, 17), date(2024, 6, 18),
        date(2024, 6, 20), date(2024, 6, 21), date(2024, 6, 24),
        date(2024, 6, 25),
    ]
    return {"MU": [_bar("MU", d, 100.0 + i) for i, d in enumerate(days)]}


class FakeVolRampAdapter:
    def __init__(self, result="quotes"):
        self.calls = []
        self.result = result

    def get_historical_vol_ramp_straddle(self, **kwargs):
        self.calls.append(kwargs)
        if self.result == "boom":
            raise RuntimeError("boom")
        if self.result == "empty":
            return []
        entry_d = kwargs["entry_as_of_date"]
        exit_d = kwargs["exit_as_of_date"]
        symbol = kwargs["underlying_symbol"]

        def q(ot, d, close):
            return OptionQuote(
                ticker=symbol, option_type=ot, strike=100.0,
                expiration_date=date(2024, 6, 28), quote_date=d,
                bid=close, ask=close,
            )

        return [
            q("CALL", entry_d, 2.0), q("PUT", entry_d, 2.1),
            q("CALL", exit_d, 3.0), q("PUT", exit_d, 3.2),
        ]


def test_vol_ramp_loader_threads_entry_day_and_price() -> None:
    from prescient.edge.data.option_loader import load_vol_ramp_straddles_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    as_of_prices = {("MU", date(2024, 6, 26)): (date(2024, 6, 25), 109.0)}
    adapter = FakeVolRampAdapter()
    out = load_vol_ramp_straddles_for_events(
        adapter, events=events, as_of_prices=as_of_prices, bars=_mu_bars(),
        entry_lead_trading_days=5, max_expiration_days=14,
    )
    key = ("MU", date(2024, 6, 26))
    assert key in out and len(out[key]) == 4
    call = adapter.calls[0]
    assert call["entry_as_of_date"] == date(2024, 6, 17)
    assert call["exit_as_of_date"] == date(2024, 6, 25)
    assert call["entry_underlying_price"] == 104.0  # close of the 6/17 bar
    assert call["earnings_date"] == date(2024, 6, 26)
    assert call["max_expiration_date"] == date(2024, 7, 10)  # report + 14d


def test_vol_ramp_loader_skips_event_with_too_little_bar_history() -> None:
    from prescient.edge.data.option_loader import load_vol_ramp_straddles_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    as_of_prices = {("MU", date(2024, 6, 26)): (date(2024, 6, 25), 109.0)}
    bars = {"MU": _mu_bars()["MU"][-3:]}  # only 3 bars < lead 5 + 1
    adapter = FakeVolRampAdapter()
    out = load_vol_ramp_straddles_for_events(
        adapter, events=events, as_of_prices=as_of_prices, bars=bars,
        entry_lead_trading_days=5, max_expiration_days=14,
    )
    assert out == {}
    assert adapter.calls == []


def test_vol_ramp_loader_skips_event_without_as_of_price() -> None:
    from prescient.edge.data.option_loader import load_vol_ramp_straddles_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    adapter = FakeVolRampAdapter()
    out = load_vol_ramp_straddles_for_events(
        adapter, events=events, as_of_prices={}, bars=_mu_bars(),
        entry_lead_trading_days=5, max_expiration_days=14,
    )
    assert out == {}
    assert adapter.calls == []


def test_vol_ramp_loader_skips_failing_event_and_continues() -> None:
    from prescient.edge.data.option_loader import load_vol_ramp_straddles_for_events

    class Flaky(FakeVolRampAdapter):
        def get_historical_vol_ramp_straddle(self, **kwargs):
            if kwargs["underlying_symbol"] == "BAD":
                raise RuntimeError("boom")
            return super().get_historical_vol_ramp_straddle(**kwargs)

    bad_bars = {"BAD": [_bar("BAD", b.trading_date, b.close) for b in _mu_bars()["MU"]]}
    events = [
        EarningsAnnouncement(ticker="BAD", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
    ]
    as_of_prices = {
        ("BAD", date(2024, 6, 26)): (date(2024, 6, 25), 50.0),
        ("MU", date(2024, 6, 26)): (date(2024, 6, 25), 109.0),
    }
    out = load_vol_ramp_straddles_for_events(
        Flaky(), events=events, as_of_prices=as_of_prices,
        bars={**_mu_bars(), **bad_bars},
        entry_lead_trading_days=5, max_expiration_days=14,
    )
    assert ("MU", date(2024, 6, 26)) in out
    assert ("BAD", date(2024, 6, 26)) not in out


def test_vol_ramp_loader_omits_events_with_empty_result() -> None:
    from prescient.edge.data.option_loader import load_vol_ramp_straddles_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    as_of_prices = {("MU", date(2024, 6, 26)): (date(2024, 6, 25), 109.0)}
    out = load_vol_ramp_straddles_for_events(
        FakeVolRampAdapter(result="empty"), events=events,
        as_of_prices=as_of_prices, bars=_mu_bars(),
        entry_lead_trading_days=5, max_expiration_days=14,
    )
    assert out == {}


def test_continues_when_one_event_errors() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    class Flaky(FakeHistAdapter):
        def get_historical_atm_straddle(self, **kwargs):
            if kwargs["underlying_symbol"] == "BAD":
                raise RuntimeError("boom")
            return super().get_historical_atm_straddle(**kwargs)

    events = [
        EarningsAnnouncement(ticker="BAD", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
    ]
    as_of_prices = {
        ("BAD", date(2024, 6, 26)): (date(2024, 6, 25), 50.0),
        ("MU", date(2024, 6, 26)): (date(2024, 6, 25), 141.0),
    }
    out = load_option_quotes_for_events(
        Flaky(), events=events, as_of_prices=as_of_prices, max_expiration_days=14,
    )
    assert "MU" in out and "BAD" not in out
