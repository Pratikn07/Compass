from __future__ import annotations

from datetime import date

from compass.research.edge.models import ImpliedMove, OptionQuote


def compute_implied_move(
    *,
    ticker: str,
    as_of_date: date,
    underlying_price: float,
    atm_call: OptionQuote | None,
    atm_put: OptionQuote | None,
) -> ImpliedMove | None:
    if underlying_price <= 0 or atm_call is None or atm_put is None:
        return None
    call_mid = atm_call.mid
    put_mid = atm_put.mid
    if call_mid is None or put_mid is None:
        return None
    straddle_price = call_mid + put_mid
    return ImpliedMove(
        ticker=ticker,
        as_of_date=as_of_date,
        underlying_price=underlying_price,
        straddle_price=straddle_price,
        implied_move_pct=(straddle_price / underlying_price) * 100.0,
    )
