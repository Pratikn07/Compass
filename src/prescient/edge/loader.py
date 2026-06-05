from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.models import EventContext, OptionQuote
from prescient.edge.realized_move import compute_realized_move


@dataclass(frozen=True)
class PointInTimeDataset:
    """Holds historical bars and option quotes. Accessors refuse to return any
    row dated AFTER the requested as-of date - the anti-lookahead core."""

    bars: dict[str, list[DailyBarSnapshot]] = field(default_factory=dict)
    option_quotes: dict[str, list[OptionQuote]] = field(default_factory=dict)

    def bars_as_of(self, ticker: str, *, as_of_date: date) -> list[DailyBarSnapshot]:
        rows = self.bars.get(ticker.strip().upper(), [])
        return sorted(
            (b for b in rows if b.trading_date <= as_of_date),
            key=lambda b: b.trading_date,
        )

    def all_bars(self, ticker: str) -> list[DailyBarSnapshot]:
        return sorted(
            self.bars.get(ticker.strip().upper(), []),
            key=lambda b: b.trading_date,
        )

    def option_quotes_as_of(
        self, ticker: str, *, as_of_date: date
    ) -> list[OptionQuote]:
        rows = self.option_quotes.get(ticker.strip().upper(), [])
        return [q for q in rows if q.quote_date <= as_of_date]


def _latest_close(bars: list[DailyBarSnapshot], as_of_date: date) -> float | None:
    """Most recent close on or before as_of_date.

    `bars` are assumed already filtered to as-of (trading_date <= as_of_date) and
    sorted ascending by the caller. Walking from the end yields the latest visible
    close, which correctly handles an as_of_date that is itself a non-trading day
    (holiday/weekend) without ever looking ahead. Returns None when no usable
    close exists.
    """
    for bar in reversed(bars):
        if bar.trading_date <= as_of_date and bar.close is not None:
            return bar.close
    return None


def _atm_quote(
    quotes: list[OptionQuote], option_type: str, underlying_price: float
) -> OptionQuote | None:
    """ATM quote: the contract whose strike is closest to underlying_price.

    Ties (equidistant strikes) resolve to the first in list order. Returns None
    when no quote of the requested option_type exists.
    """
    candidates = [q for q in quotes if q.option_type == option_type]
    if not candidates:
        return None
    return min(candidates, key=lambda q: abs(q.strike - underlying_price))


def build_event_context(
    *,
    dataset: PointInTimeDataset,
    ticker: str,
    earnings_date: date,
    as_of_date: date,
    horizon_days: int,
) -> EventContext | None:
    """Assemble one EventContext. Inputs use ONLY as-of data; the realized move
    is computed from the full bar history (post-report). Returns None when the
    as-of underlying price is unavailable (skip, never guess)."""
    visible_bars = dataset.bars_as_of(ticker, as_of_date=as_of_date)
    underlying_price = _latest_close(visible_bars, as_of_date)
    if underlying_price is None:
        return None

    quotes = dataset.option_quotes_as_of(ticker, as_of_date=as_of_date)
    atm_call = _atm_quote(quotes, "CALL", underlying_price)
    atm_put = _atm_quote(quotes, "PUT", underlying_price)

    realized = compute_realized_move(
        ticker=ticker,
        as_of_date=as_of_date,
        bars=dataset.all_bars(ticker),
        horizon_days=horizon_days,
    )

    return EventContext(
        ticker=ticker,
        earnings_date=earnings_date,
        as_of_date=as_of_date,
        underlying_price=underlying_price,
        atm_call=atm_call,
        atm_put=atm_put,
        realized_move=realized,
    )
