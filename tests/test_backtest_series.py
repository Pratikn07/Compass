"""Series math, calendar, and the point-in-time theme index (no I/O)."""
from datetime import date, timedelta

from compass.backtest.calendar import TradingCalendar
from compass.backtest.series import Series, return_over_bars, sma_at, theme_index, total_return


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_value_lookups_are_point_in_time_safe():
    days = _weekdays(date(2020, 1, 1), 5)
    s = Series(days, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert s.value_at(days[2]) == 3.0
    assert s.value_at(date(2020, 1, 4)) is None  # Saturday: no bar, no guess
    assert s.value_on_or_before(date(2020, 1, 4)) == 3.0  # Friday's bar
    assert s.value_on_or_before(date(2019, 12, 31)) is None  # before history


def test_sma_requires_full_window():
    days = _weekdays(date(2020, 1, 1), 5)
    s = Series(days, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert sma_at(s, days[4], 5) == 3.0
    assert sma_at(s, days[4], 3) == 4.0
    assert sma_at(s, days[2], 5) is None  # only 3 bars exist -> skip, don't guess


def test_total_return_and_bars_return():
    days = _weekdays(date(2020, 1, 1), 10)
    s = Series(days, [100 + i for i in range(10)])
    assert total_return(s, days[0], days[9]) == (109 / 100) - 1
    r, exit_d = return_over_bars(s, days[2], 3)
    assert r == (105 / 102) - 1
    assert exit_d == days[5]
    assert return_over_bars(s, days[8], 5) is None  # not enough future bars


def test_month_ends_and_execution_day():
    days = _weekdays(date(2020, 1, 1), 45)  # Jan + Feb 2020
    cal = TradingCalendar(days)
    ends = cal.month_ends(date(2020, 1, 1), date(2020, 2, 28))
    assert ends[0] == date(2020, 1, 31)
    assert ends[1] == date(2020, 2, 28)
    # Execution: first trading day strictly after the signal bar
    assert cal.next_day(date(2020, 1, 31)) == date(2020, 2, 3)  # Monday


def test_theme_index_equal_weight_two_members():
    days = _weekdays(date(2020, 1, 1), 6)
    a = Series(days, [100, 110, 120, 130, 140, 150])  # +50% over the window
    b = Series(days, [100, 100, 100, 100, 100, 100])  # flat
    idx = theme_index({"A": a, "B": b}, lambda d: ["A", "B"], days, days[0], days[-1])
    # Equal-weight: mean(1.5, 1.0) = 1.25
    assert abs(idx.values[-1] - 1.25) < 1e-12


def test_theme_index_point_in_time_membership():
    # 2 months of days; member B "joins" at the start of month 2.
    days = _weekdays(date(2020, 1, 1), 45)
    feb_first = next(d for d in days if d.month == 2)
    a = Series(days, [100.0] * len(days))
    b_days = [d for d in days if d >= feb_first]
    b = Series(b_days, [100.0 * (1.1 ** i) for i in range(len(b_days))])

    def active(d):
        return ["A", "B"] if d >= feb_first else ["A"]

    idx = theme_index({"A": a, "B": b}, active, days, days[0], days[-1])
    jan_end_val = idx.value_on_or_before(date(2020, 1, 31))
    assert jan_end_val == 1.0  # January: only flat A — B's rise is invisible
    assert idx.values[-1] > 1.0  # February: B in the roster moves the index


def test_theme_index_member_without_price_on_rebalance_day_is_skipped():
    days = _weekdays(date(2020, 1, 1), 6)
    a = Series(days, [100, 101, 102, 103, 104, 105])
    b = Series(days[3:], [100, 110, 120])  # lists later in the month
    idx = theme_index({"A": a, "B": b}, lambda d: ["A", "B"], days, days[0], days[-1])
    # B had no price on the month's rebalance day -> excluded all month
    assert abs(idx.values[-1] - 1.05) < 1e-12
