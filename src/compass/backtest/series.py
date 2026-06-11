"""Price series and indicator math. Pure, fixture-testable, no I/O."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Series:
    """A daily series with sorted dates; lookups are point-in-time safe
    (on-or-before never sees the future)."""

    dates: list[date]
    values: list[float]

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.values):
            raise ValueError("dates and values must align")

    def __len__(self) -> int:
        return len(self.dates)

    def idx_on_or_before(self, d: date) -> int | None:
        i = bisect_right(self.dates, d) - 1
        return i if i >= 0 else None

    def value_on_or_before(self, d: date) -> float | None:
        i = self.idx_on_or_before(d)
        return self.values[i] if i is not None else None

    def value_at(self, d: date) -> float | None:
        i = bisect_left(self.dates, d)
        if i < len(self.dates) and self.dates[i] == d:
            return self.values[i]
        return None

    def first_date(self) -> date | None:
        return self.dates[0] if self.dates else None

    def slice(self, start: date, end: date) -> Series:
        lo = bisect_left(self.dates, start)
        hi = bisect_right(self.dates, end)
        return Series(self.dates[lo:hi], self.values[lo:hi])


def sma_at(series: Series, d: date, n: int) -> float | None:
    """Simple moving average of the last n bars ending at the bar on-or-before d.
    Returns None if fewer than n bars exist (skip, don't guess)."""
    i = series.idx_on_or_before(d)
    if i is None or i + 1 < n:
        return None
    window = series.values[i + 1 - n : i + 1]
    return sum(window) / n


def total_return(series: Series, start: date, end: date) -> float | None:
    """Return from the bar on-or-before start to the bar on-or-before end."""
    a = series.value_on_or_before(start)
    b = series.value_on_or_before(end)
    if a is None or b is None or a == 0:
        return None
    return b / a - 1.0


def return_over_bars(series: Series, entry: date, n_bars: int) -> tuple[float, date] | None:
    """Return over exactly n_bars trading bars starting at the bar on-or-before
    `entry`. Returns (return, exit_date) or None if history is insufficient."""
    i = series.idx_on_or_before(entry)
    if i is None or i + n_bars >= len(series):
        return None
    a = series.values[i]
    b = series.values[i + n_bars]
    if a == 0:
        return None
    return b / a - 1.0, series.dates[i + n_bars]


def theme_index(
    member_series: dict[str, Series],
    active_tickers,
    trading_days: list[date],
    start: date,
    end: date,
) -> Series:
    """Equal-weighted, monthly-rebalanced theme index (rulebook §3.1).

    - Roster is fixed at each rebalance day (the first trading day of the
      month) using point-in-time membership: `active_tickers(day)` must return
      only members visible on that date (rulebook §4).
    - A member joins the month's roster only if it has a price on the rebalance
      day (skip, don't guess).
    - Within a month: level(t) = level(rebalance) * mean_i(p_i(t) / p_i(rebalance)).
    """
    days = [d for d in trading_days if start <= d <= end]
    if not days:
        return Series([], [])

    out_dates: list[date] = []
    out_values: list[float] = []
    level = 1.0

    current_month: tuple[int, int] | None = None
    roster: list[tuple[Series, float]] = []  # (series, price at rebalance)
    month_base_level = 1.0

    for d in days:
        ym = (d.year, d.month)
        if ym != current_month:
            current_month = ym
            month_base_level = level
            roster = []
            for ticker in active_tickers(d):
                s = member_series.get(ticker)
                if s is None:
                    continue
                p = s.value_at(d)
                if p is not None and p > 0:
                    roster.append((s, p))
        if roster:
            rels = []
            for s, base in roster:
                p = s.value_on_or_before(d)
                if p is not None:
                    rels.append(p / base)
            if rels:
                level = month_base_level * (sum(rels) / len(rels))
        out_dates.append(d)
        out_values.append(level)

    return Series(out_dates, out_values)
