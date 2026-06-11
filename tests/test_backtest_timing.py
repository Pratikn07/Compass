"""Timing engine tests on synthetic data: the rule must dodge a crash it can
see coming, charge costs/taxes honestly, and never trade the signal bar."""
from datetime import date, timedelta

import pytest

from compass.backtest.calendar import TradingCalendar
from compass.backtest.h1_trend import (
    judge_h1,
    monthly_closes,
    run_timing,
    sma_daily_signal,
)
from compass.backtest.series import Series


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _make_crash_series(days):
    """Rises for ~2 years, crashes 50% over 6 months, recovers slowly.
    A 100-day SMA rule should sidestep most of the crash."""
    n = len(days)
    rise = int(n * 0.5)
    crash = int(n * 0.25)
    vals = []
    v = 100.0
    for i in range(n):
        if i < rise:
            v *= 1.0008
        elif i < rise + crash:
            v *= 0.9972
        else:
            v *= 1.0006
        vals.append(v)
    return Series(days, vals)


def test_timing_cuts_drawdown_in_a_crash():
    days = _weekdays(date(2010, 1, 1), 1000)
    cal = TradingCalendar(days)
    prices = _make_crash_series(days)
    result = run_timing(
        instrument=prices,
        cal=cal,
        signal=sma_daily_signal(prices, 100),
        start=days[0],
        end=days[-1],
        taxed=False,
    )
    assert result is not None
    s_dd = abs(result.strategy.max_drawdown)
    b_dd = abs(result.buy_and_hold.max_drawdown)
    assert s_dd < b_dd  # the whole point of the seatbelt
    assert s_dd <= 0.75 * b_dd


def test_no_valid_signal_returns_none():
    days = _weekdays(date(2020, 1, 1), 50)  # < 100 bars: SMA never computable
    cal = TradingCalendar(days)
    prices = Series(days, [100.0] * 50)
    assert run_timing(
        instrument=prices, cal=cal, signal=sma_daily_signal(prices, 100),
        start=days[0], end=days[-1],
    ) is None


def test_buy_and_hold_charges_costs_and_long_term_tax():
    days = _weekdays(date(2010, 1, 1), 600)
    cal = TradingCalendar(days)
    # Steady riser: timing stays invested throughout -> equals buy-and-hold
    prices = Series(days, [100.0 * 1.001**i for i in range(600)])
    result = run_timing(
        instrument=prices, cal=cal, signal=sma_daily_signal(prices, 100),
        start=days[0], end=days[-1], taxed=True,
    )
    assert result is not None
    bh = result.monthly_buy_and_hold
    p_entry_day = cal.next_day(  # first eval with valid signal -> next day
        cal.month_ends(days[0], days[-1])[4]
    )
    # Final equity must reflect: buy cost, sell cost, and 20% long-term tax.
    gross = prices.value_on_or_before(bh.dates[-1]) / prices.value_on_or_before(p_entry_day)
    invested = 0.999
    after_exit = invested * gross * 0.999
    expected = invested + (after_exit - invested) * 0.80
    assert bh.values[-1] == pytest.approx(expected, rel=1e-6)
    # Strategy that never exits should equal its buy-and-hold twin.
    assert result.monthly_strategy.values[-1] == pytest.approx(bh.values[-1], rel=1e-9)


def test_judge_h1_bars():
    days = _weekdays(date(2010, 1, 1), 1000)
    cal = TradingCalendar(days)
    prices = _make_crash_series(days)
    result = run_timing(
        instrument=prices, cal=cal, signal=sma_daily_signal(prices, 100),
        start=days[0], end=days[-1], taxed=True,
    )
    verdict = judge_h1("SYNTH", "etf-primary", result)
    assert verdict.bar2_drawdown  # crash dodged
    assert isinstance(verdict.survived_development, bool)


def test_monthly_closes_picks_month_ends():
    days = _weekdays(date(2020, 1, 1), 45)
    cal = TradingCalendar(days)
    prices = Series(days, [float(i) for i in range(45)])
    mc = monthly_closes(prices, cal)
    assert mc.dates[0] == date(2020, 1, 31)
    assert mc.values[0] == prices.value_at(date(2020, 1, 31))
