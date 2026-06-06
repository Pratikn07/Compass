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
