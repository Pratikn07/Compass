from __future__ import annotations

from datetime import date

from prescient.data.alpaca_market import AlpacaMarketDataAdapter, OptionChainEntry


def _entry(symbol, ot, strike):
    return OptionChainEntry(
        contract_symbol=f"{symbol}{ot}{int(strike)}",
        strike_price=strike,
        expiration_date=date(2024, 7, 19),
        option_type=ot,
        bid=3.9,
        ask=4.1,
        open_interest=1500,
    )


def test_get_atm_option_quotes_returns_both_types_with_strike() -> None:
    entries = [
        _entry("MU", "CALL", 100.0),
        _entry("MU", "PUT", 100.0),
        _entry("MU", "CALL", 105.0),
    ]
    adapter = AlpacaMarketDataAdapter(
        option_chain_reader=lambda *, underlying_symbol, feed: entries
    )
    quotes = adapter.get_atm_option_quotes(
        underlying_symbol="mu",
        quote_date=date(2024, 6, 25),
        earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 8, 1),
    )
    types = {(q.option_type, q.strike) for q in quotes}
    assert ("CALL", 100.0) in types
    assert ("PUT", 100.0) in types
    assert all(q.quote_date == date(2024, 6, 25) for q in quotes)
    assert all(q.ticker == "MU" for q in quotes)
