from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def load_option_quotes_for_events(
    adapter: Any,
    *,
    events: Sequence[EarningsAnnouncement],
    as_of_prices: dict[tuple[str, date], tuple[date, float]],
    max_expiration_days: int,
) -> dict[str, list[OptionQuote]]:
    """Fetch the as-of ATM straddle per event via the historical reader; accumulate per
    ticker. Events without a known as-of price are skipped; a failed fetch is skipped
    (skip-not-guess), never zero-filled."""
    out: dict[str, list[OptionQuote]] = {}
    for event in events:
        key = (event.ticker, event.report_date)
        as_of = as_of_prices.get(key)
        if as_of is None:
            continue
        as_of_date, underlying_price = as_of
        max_exp = event.report_date + timedelta(days=max_expiration_days)
        try:
            quotes = adapter.get_historical_atm_straddle(
                underlying_symbol=event.ticker,
                as_of_date=as_of_date,
                underlying_price=underlying_price,
                earnings_date=event.report_date,
                max_expiration_date=max_exp,
            )
        except Exception:  # noqa: BLE001  # intentional skip-not-guess
            continue
        if quotes:
            out.setdefault(event.ticker, []).extend(quotes)
    return out
