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


def _vol_ramp_adapter(rows_by_as_of):
    """Fake reader that returns different rows per as-of date (entry vs exit)."""

    def reader(*, underlying_symbol, as_of_date, earnings_date, max_expiration_date):
        return rows_by_as_of.get(as_of_date, [])

    return AlpacaMarketDataAdapter(historical_option_reader=reader)


_ENTRY_D = date(2024, 6, 18)
_EXIT_D = date(2024, 6, 25)


def _vol_ramp_kwargs(**overrides):
    base = dict(
        underlying_symbol="mu",
        entry_as_of_date=_ENTRY_D,
        exit_as_of_date=_EXIT_D,
        entry_underlying_price=99.7,
        earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    base.update(overrides)
    return base


def test_vol_ramp_returns_four_strike_locked_quotes() -> None:
    exp = date(2024, 6, 28)
    rows_by_as_of = {
        _ENTRY_D: [
            _row("MU_C_95", 95.0, "CALL", 5.0, exp=exp),
            _row("MU_C_100", 100.0, "CALL", 2.0, exp=exp),
            _row("MU_P_100", 100.0, "PUT", 2.1, exp=exp),
            _row("MU_C_105", 105.0, "CALL", 0.9, exp=exp),
        ],
        _EXIT_D: [
            _row("MU_C_100", 100.0, "CALL", 3.0, exp=exp),
            _row("MU_P_100", 100.0, "PUT", 3.2, exp=exp),
        ],
    }
    quotes = _vol_ramp_adapter(rows_by_as_of).get_historical_vol_ramp_straddle(
        **_vol_ramp_kwargs()
    )
    assert [q.option_type for q in quotes] == ["CALL", "PUT", "CALL", "PUT"]
    assert [q.quote_date for q in quotes] == [_ENTRY_D, _ENTRY_D, _EXIT_D, _EXIT_D]
    assert {q.strike for q in quotes} == {100.0}
    assert {q.expiration_date for q in quotes} == {exp}
    assert [q.bid for q in quotes] == [2.0, 2.1, 3.0, 3.2]
    assert all(q.bid == q.ask for q in quotes)
    assert all(q.ticker == "MU" for q in quotes)


def test_vol_ramp_picks_earliest_expiration_in_window() -> None:
    near, far = date(2024, 6, 28), date(2024, 7, 5)
    rows_entry = [
        _row("MU_C_100_far", 100.0, "CALL", 2.5, exp=far),
        _row("MU_P_100_far", 100.0, "PUT", 2.6, exp=far),
        _row("MU_C_100_near", 100.0, "CALL", 2.0, exp=near),
        _row("MU_P_100_near", 100.0, "PUT", 2.1, exp=near),
    ]
    rows_exit = [
        _row("MU_C_100_far", 100.0, "CALL", 3.5, exp=far),
        _row("MU_P_100_far", 100.0, "PUT", 3.6, exp=far),
        _row("MU_C_100_near", 100.0, "CALL", 3.0, exp=near),
        _row("MU_P_100_near", 100.0, "PUT", 3.1, exp=near),
    ]
    quotes = _vol_ramp_adapter(
        {_ENTRY_D: rows_entry, _EXIT_D: rows_exit}
    ).get_historical_vol_ramp_straddle(**_vol_ramp_kwargs())
    assert {q.expiration_date for q in quotes} == {near}
    assert [q.bid for q in quotes] == [2.0, 2.1, 3.0, 3.1]


def test_vol_ramp_missing_exit_leg_returns_empty() -> None:
    exp = date(2024, 6, 28)
    rows_by_as_of = {
        _ENTRY_D: [
            _row("MU_C_100", 100.0, "CALL", 2.0, exp=exp),
            _row("MU_P_100", 100.0, "PUT", 2.1, exp=exp),
        ],
        _EXIT_D: [
            _row("MU_C_100", 100.0, "CALL", 3.0, exp=exp),
            # PUT close missing at exit
            _row("MU_P_100", 100.0, "PUT", None, exp=exp),
        ],
    }
    quotes = _vol_ramp_adapter(rows_by_as_of).get_historical_vol_ramp_straddle(
        **_vol_ramp_kwargs()
    )
    assert quotes == []


def test_vol_ramp_missing_entry_put_returns_empty() -> None:
    exp = date(2024, 6, 28)
    rows_by_as_of = {
        _ENTRY_D: [_row("MU_C_100", 100.0, "CALL", 2.0, exp=exp)],
        _EXIT_D: [
            _row("MU_C_100", 100.0, "CALL", 3.0, exp=exp),
            _row("MU_P_100", 100.0, "PUT", 3.2, exp=exp),
        ],
    }
    quotes = _vol_ramp_adapter(rows_by_as_of).get_historical_vol_ramp_straddle(
        **_vol_ramp_kwargs()
    )
    assert quotes == []


def test_vol_ramp_out_of_window_expirations_return_empty() -> None:
    late = date(2024, 9, 20)
    rows = [
        _row("MU_C_100", 100.0, "CALL", 2.0, exp=late),
        _row("MU_P_100", 100.0, "PUT", 2.1, exp=late),
    ]
    quotes = _vol_ramp_adapter(
        {_ENTRY_D: rows, _EXIT_D: rows}
    ).get_historical_vol_ramp_straddle(**_vol_ramp_kwargs())
    assert quotes == []


def test_vol_ramp_no_reader_records_error_and_returns_empty() -> None:
    adapter = AlpacaMarketDataAdapter()
    quotes = adapter.get_historical_vol_ramp_straddle(**_vol_ramp_kwargs())
    assert quotes == []
    assert adapter.errors


def test_vol_ramp_reader_exception_returns_empty() -> None:
    def boom(**kwargs):
        raise RuntimeError("transport down")

    adapter = AlpacaMarketDataAdapter(historical_option_reader=boom)
    quotes = adapter.get_historical_vol_ramp_straddle(**_vol_ramp_kwargs())
    assert quotes == []
    assert adapter.errors


def test_returns_empty_when_put_missing_at_atm_strike() -> None:
    # Puts exist, but not at the ATM strike the call selects -> no same-strike
    # straddle -> []. (Distinct from the no-puts-at-all path.)
    rows = [
        _row("MU_C_141", 141.0, "CALL", 9.08),
        _row("MU_P_140", 140.0, "PUT", 8.95),  # different strike
        _row("MU_P_145", 145.0, "PUT", 7.50),  # different strike
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []
