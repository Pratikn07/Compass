from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from compass.research.edge.models import DailyBar, EventContext, OptionQuote
from compass.research.edge.realized_move import compute_realized_move


@dataclass(frozen=True)
class PointInTimeDataset:
    """Historical data whose accessors enforce the requested as-of boundary."""

    bars: dict[str, list[DailyBar]] = field(default_factory=dict)
    option_quotes: dict[str, list[OptionQuote]] = field(default_factory=dict)

    def bars_as_of(self, ticker: str, *, as_of_date: date) -> list[DailyBar]:
        rows = self.bars.get(ticker.strip().upper(), [])
        return sorted(
            (bar for bar in rows if bar.trading_date <= as_of_date),
            key=lambda bar: bar.trading_date,
        )

    def all_bars(self, ticker: str) -> list[DailyBar]:
        return sorted(
            self.bars.get(ticker.strip().upper(), []),
            key=lambda bar: bar.trading_date,
        )

    def option_quotes_as_of(
        self,
        ticker: str,
        *,
        as_of_date: date,
    ) -> list[OptionQuote]:
        rows = self.option_quotes.get(ticker.strip().upper(), [])
        return [row for row in rows if row.quote_date <= as_of_date]


def _latest_bar(bars: list[DailyBar], as_of_date: date) -> DailyBar | None:
    return next(
        (
            bar
            for bar in reversed(bars)
            if bar.trading_date <= as_of_date and bar.close is not None
        ),
        None,
    )


def _atm_quote(
    quotes: list[OptionQuote],
    option_type: str,
    underlying_price: float,
) -> OptionQuote | None:
    candidates = [quote for quote in quotes if quote.option_type == option_type]
    if not candidates:
        return None
    return min(candidates, key=lambda quote: abs(quote.strike - underlying_price))


def build_event_context(
    *,
    dataset: PointInTimeDataset,
    ticker: str,
    earnings_date: date,
    as_of_date: date,
    horizon_days: int,
) -> EventContext | None:
    visible_bars = dataset.bars_as_of(ticker, as_of_date=as_of_date)
    latest_bar = _latest_bar(visible_bars, as_of_date)
    if latest_bar is None or latest_bar.close is None:
        return None
    quotes = dataset.option_quotes_as_of(ticker, as_of_date=as_of_date)
    realized = compute_realized_move(
        ticker=ticker,
        as_of_date=latest_bar.trading_date,
        bars=dataset.all_bars(ticker),
        horizon_days=horizon_days,
    )
    return EventContext(
        ticker=ticker,
        earnings_date=earnings_date,
        as_of_date=as_of_date,
        underlying_price=latest_bar.close,
        atm_call=_atm_quote(quotes, "CALL", latest_bar.close),
        atm_put=_atm_quote(quotes, "PUT", latest_bar.close),
        realized_move=realized,
    )
