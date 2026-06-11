"""Trading calendar derived from SPY bars (the same calendar the coverage
gate uses). Pure, fixture-testable."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date


class TradingCalendar:
    def __init__(self, days: list[date]) -> None:
        if days != sorted(days):
            raise ValueError("trading days must be sorted")
        self.days = days

    def month_ends(self, start: date, end: date) -> list[date]:
        """Last trading day of each calendar month within [start, end]."""
        out: list[date] = []
        for i, d in enumerate(self.days):
            if d < start or d > end:
                continue
            is_last = i + 1 >= len(self.days) or (
                (self.days[i + 1].year, self.days[i + 1].month) != (d.year, d.month)
            )
            if is_last:
                out.append(d)
        return out

    def next_day(self, after: date) -> date | None:
        """First trading day strictly after `after` (the execution-day rule:
        signals never trade on the bar that produced them)."""
        i = bisect_right(self.days, after)
        return self.days[i] if i < len(self.days) else None

    def shift(self, d: date, n_bars: int) -> date | None:
        """The trading day n_bars after the day on-or-before d."""
        i = bisect_right(self.days, d) - 1
        if i < 0 or i + n_bars >= len(self.days):
            return None
        return self.days[i + n_bars]

    def count_between(self, start: date, end: date) -> int:
        lo = bisect_left(self.days, start)
        hi = bisect_right(self.days, end)
        return max(hi - lo, 0)
