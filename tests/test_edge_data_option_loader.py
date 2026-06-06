from __future__ import annotations

from datetime import date

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


class FakeOptionAdapter:
    def __init__(self):
        self.calls = []

    def get_atm_option_quotes(self, *, underlying_symbol, quote_date, earnings_date,
                              max_expiration_date, feed="indicative"):
        self.calls.append({
            "symbol": underlying_symbol, "quote_date": quote_date,
            "earnings_date": earnings_date, "max_expiration_date": max_expiration_date,
        })
        return [
            OptionQuote(ticker=underlying_symbol, option_type="CALL", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=quote_date,
                        bid=3.9, ask=4.1),
            OptionQuote(ticker=underlying_symbol, option_type="PUT", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=quote_date,
                        bid=3.9, ask=4.1),
        ]


def test_loads_quotes_per_event_and_accumulates_by_ticker() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 3, 20)),
    ]
    adapter = FakeOptionAdapter()
    out = load_option_quotes_for_events(adapter, events=events, max_expiration_days=14)
    assert set(out.keys()) == {"MU"}
    assert len(out["MU"]) == 4  # 2 legs x 2 events
    assert len(adapter.calls) == 2
    # max_expiration_date = report_date + 14 days
    assert adapter.calls[0]["max_expiration_date"] == date(2024, 7, 10)


def test_continues_when_one_event_errors() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    class FlakyAdapter(FakeOptionAdapter):
        def get_atm_option_quotes(self, **kwargs):
            if kwargs["underlying_symbol"] == "BAD":
                raise RuntimeError("boom")
            return super().get_atm_option_quotes(**kwargs)

    events = [
        EarningsAnnouncement(ticker="BAD", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
    ]
    out = load_option_quotes_for_events(FlakyAdapter(), events=events, max_expiration_days=14)
    assert "MU" in out and "BAD" not in out
