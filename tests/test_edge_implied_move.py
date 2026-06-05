from __future__ import annotations

from datetime import date

import pytest


def _quote(option_type, strike, bid, ask):
    from prescient.edge.models import OptionQuote

    return OptionQuote(
        ticker="MU",
        option_type=option_type,
        strike=strike,
        expiration_date=date(2024, 7, 19),
        quote_date=date(2024, 6, 25),
        bid=bid,
        ask=ask,
    )


def test_implied_move_from_atm_straddle() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, 3.9, 4.1)  # mid 4.0
    put = _quote("PUT", 100.0, 3.9, 4.1)    # mid 4.0
    result = compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=call, atm_put=put,
    )
    assert result is not None
    assert result.straddle_price == pytest.approx(8.0)
    assert result.implied_move_pct == pytest.approx(8.0)


def test_implied_move_none_when_quote_missing() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, None, None)  # mid None
    put = _quote("PUT", 100.0, 3.9, 4.1)
    assert compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=call, atm_put=put,
    ) is None


def test_implied_move_none_when_underlying_nonpositive() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, 3.9, 4.1)
    put = _quote("PUT", 100.0, 3.9, 4.1)
    assert compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=0.0, atm_call=call, atm_put=put,
    ) is None
