from __future__ import annotations

from datetime import date

from prescient.data.alpaca_market import (
    AlpacaMarketDataAdapter,
    HistoricalOptionRow,
)


def _row(symbol, strike, ot, close, exp=date(2024, 6, 28), oi=1000):
    return HistoricalOptionRow(
        contract_symbol=symbol,
        strike=strike,
        expiration_date=exp,
        option_type=ot,
        close=close,
        open_interest=oi,
    )


def _adapter(rows):
    def reader(*, underlying_symbol, as_of_date, earnings_date, max_expiration_date):
        return rows
    return AlpacaMarketDataAdapter(historical_option_reader=reader)


def test_picks_atm_pair_and_prices_at_close() -> None:
    rows = [
        _row("MU_C_138", 138.0, "CALL", 10.0),
        _row("MU_C_141", 141.0, "CALL", 9.08),
        _row("MU_P_141", 141.0, "PUT", 8.95),
        _row("MU_C_145", 145.0, "CALL", 6.0),
    ]
    adapter = _adapter(rows)
    quotes = adapter.get_historical_atm_straddle(
        underlying_symbol="mu", as_of_date=date(2024, 6, 25),
        underlying_price=141.12, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert len(quotes) == 2
    by_type = {q.option_type: q for q in quotes}
    assert by_type["CALL"].strike == 141.0
    assert by_type["PUT"].strike == 141.0
    assert by_type["CALL"].bid == 9.08 and by_type["CALL"].ask == 9.08
    assert by_type["CALL"].mid == 9.08
    assert by_type["PUT"].mid == 8.95
    assert by_type["CALL"].quote_date == date(2024, 6, 25)
    assert by_type["CALL"].ticker == "MU"


def test_returns_empty_when_put_leg_missing() -> None:
    rows = [_row("MU_C_141", 141.0, "CALL", 9.08)]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_returns_empty_when_no_contracts() -> None:
    quotes = _adapter([]).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_returns_empty_when_leg_close_missing() -> None:
    rows = [
        _row("MU_C_141", 141.0, "CALL", None),
        _row("MU_P_141", 141.0, "PUT", 8.95),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_filters_out_contracts_outside_expiration_window() -> None:
    rows = [
        _row("MU_C_141_late", 141.0, "CALL", 9.0, exp=date(2024, 9, 20)),
        _row("MU_P_141_late", 141.0, "PUT", 8.0, exp=date(2024, 9, 20)),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_tie_break_prefers_lower_strike() -> None:
    rows = [
        _row("MU_C_140", 140.0, "CALL", 10.0),
        _row("MU_P_140", 140.0, "PUT", 9.0),
        _row("MU_C_142", 142.0, "CALL", 8.0),
        _row("MU_P_142", 142.0, "PUT", 11.0),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert {q.strike for q in quotes} == {140.0}
