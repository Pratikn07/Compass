"""H1 theme trend (rulebook §3.1) and the shared timing engine.

The engine is generic over the signal so the Faber calibration (10-month SMA,
pre-tax) and H1 (200-day SMA, taxed) run through the SAME code path — if the
engine is broken, calibration fails and nothing gets judged.

Mechanics pinned by the rulebook:
- Signals are computed on an evaluation bar T and execute at the close of the
  NEXT trading day (never the bar that produced them).
- Exits realize taxes (gains only); entries pay one side of costs, exits the
  other. The final bar force-liquidates so strategy and buy-and-hold are
  compared on realized, after-tax terms.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .calendar import TradingCalendar
from .costs import after_tax_equity, apply_side_cost
from .scorecard import EquityScore, score_equity
from .series import Series, sma_at


class Signal(Protocol):
    def __call__(self, t: date) -> bool | None: ...


def sma_daily_signal(prices: Series, n: int) -> Signal:
    """close(T) > SMA(n) of daily closes. None while history < n bars."""

    def signal(t: date) -> bool | None:
        s = sma_at(prices, t, n)
        p = prices.value_on_or_before(t)
        if s is None or p is None:
            return None
        return p > s

    return signal


def sma_monthly_signal(monthly_closes: Series, m: int) -> Signal:
    """Faber-style: month-end close > mean of the last m month-end closes."""

    def signal(t: date) -> bool | None:
        s = sma_at(monthly_closes, t, m)
        p = monthly_closes.value_on_or_before(t)
        if s is None or p is None:
            return None
        return p > s

    return signal


def _cash_growth(cash: Series | None, a: date, b: date) -> float:
    """Growth factor of the cash leg between two dates. Flat (1.0) when the
    T-bill proxy has no data — pessimistic per the rulebook."""
    if cash is None:
        return 1.0
    va = cash.value_on_or_before(a)
    vb = cash.value_on_or_before(b)
    if va is None or vb is None or va <= 0:
        return 1.0
    return vb / va


@dataclass
class TimingResult:
    strategy: EquityScore
    buy_and_hold: EquityScore
    monthly_strategy: Series
    monthly_buy_and_hold: Series
    months_invested: int
    months_total: int


def run_timing(
    *,
    instrument: Series,
    cal: TradingCalendar,
    signal: Signal,
    start: date,
    end: date,
    cash: Series | None = None,
    taxed: bool = True,
    eval_dates: list[date] | None = None,
    name: str = "strategy",
) -> TimingResult | None:
    """Run the timing rule and its buy-and-hold twin over [start, end].

    Returns None if the instrument never produces a valid signal in window.
    """
    evals = eval_dates if eval_dates is not None else cal.month_ends(start, end)
    evals = [t for t in evals if instrument.value_on_or_before(t) is not None]

    # The curve starts at the first evaluation with a computable signal:
    # late-listed instruments (JETS, CIBR) enter at listing + SMA warmup.
    first_i = next((i for i, t in enumerate(evals) if signal(t) is not None), None)
    if first_i is None or first_i >= len(evals) - 1:
        return None
    evals = evals[first_i:]

    t0 = evals[0]
    e0 = cal.next_day(t0)
    if e0 is None:
        return None
    p0 = instrument.value_on_or_before(e0)
    if p0 is None or p0 <= 0:
        return None

    # ---- strategy ----
    equity = 1.0
    invested = False
    units = 0.0
    cost_basis = 0.0
    entry_date = e0
    last_cash_mark = e0
    months_invested = 0

    curve_dates: list[date] = []
    curve_vals: list[float] = []

    def mark(t: date) -> float:
        if invested:
            p = instrument.value_on_or_before(t)
            return units * p if p is not None else equity
        return equity * _cash_growth(cash, last_cash_mark, t)

    # Execute the initial signal at e0.
    if signal(t0):
        equity = apply_side_cost(equity)
        p_entry = instrument.value_on_or_before(e0)
        units = equity / p_entry
        cost_basis = equity
        invested = True
        entry_date = e0

    for t in evals[1:]:
        curve_dates.append(t)
        curve_vals.append(mark(t))
        if invested:
            months_invested += 1
        want = signal(t)
        if want is None or want == invested:
            continue
        e = cal.next_day(t)
        if e is None:
            continue  # signal at the last bar of history: nothing to execute
        if invested:
            p_exit = instrument.value_on_or_before(e)
            equity = apply_side_cost(units * p_exit)
            if taxed:
                equity = after_tax_equity(equity, cost_basis, entry_date, e)
            invested = False
            last_cash_mark = e
        else:
            equity = equity * _cash_growth(cash, last_cash_mark, e)
            equity = apply_side_cost(equity)
            p_entry = instrument.value_on_or_before(e)
            units = equity / p_entry
            cost_basis = equity
            invested = True
            entry_date = e

    # Force-liquidate on the final evaluation bar for honest comparison.
    t_final = evals[-1]
    if invested:
        p_exit = instrument.value_on_or_before(t_final)
        equity = apply_side_cost(units * p_exit)
        if taxed:
            equity = after_tax_equity(equity, cost_basis, entry_date, t_final)
    else:
        equity = equity * _cash_growth(cash, last_cash_mark, t_final)
    curve_vals[-1] = equity

    strategy_curve = Series(curve_dates, curve_vals)

    # ---- buy-and-hold twin (same costs, same tax treatment, same window) ----
    bh_equity0 = apply_side_cost(1.0)
    bh_units = bh_equity0 / p0
    bh_dates: list[date] = []
    bh_vals: list[float] = []
    for t in evals[1:]:
        p = instrument.value_on_or_before(t)
        bh_dates.append(t)
        bh_vals.append(bh_units * p if p is not None else bh_vals[-1])
    bh_final = apply_side_cost(bh_units * instrument.value_on_or_before(t_final))
    if taxed:
        bh_final = after_tax_equity(bh_final, bh_equity0, e0, t_final)
    bh_vals[-1] = bh_final
    bh_curve = Series(bh_dates, bh_vals)

    def monthly(curve: Series) -> Series:
        m_ends = cal.month_ends(curve.dates[0], curve.dates[-1])
        ds, vs = [], []
        for m in m_ends:
            v = curve.value_on_or_before(m)
            if v is not None:
                ds.append(m)
                vs.append(v)
        return Series(ds, vs)

    m_strat = monthly(strategy_curve)
    m_bh = monthly(bh_curve)
    return TimingResult(
        strategy=score_equity(name, m_strat),
        buy_and_hold=score_equity(f"{name}-buy-and-hold", m_bh),
        monthly_strategy=m_strat,
        monthly_buy_and_hold=m_bh,
        months_invested=months_invested,
        months_total=len(evals) - 1,
    )


@dataclass
class H1Verdict:
    instrument: str
    label: str  # "etf-primary" | "hindsight-curated"
    result: TimingResult
    bar1_sharpe: bool
    bar2_drawdown: bool
    bar3_cagr: bool
    survived_development: bool

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument,
            "label": self.label,
            "strategy": self.result.strategy.to_dict(),
            "buy_and_hold": self.result.buy_and_hold.to_dict(),
            "months_invested": self.result.months_invested,
            "months_total": self.result.months_total,
            "bar1_sharpe": self.bar1_sharpe,
            "bar2_drawdown_25pct_smaller": self.bar2_drawdown,
            "bar3_cagr_within_1pt": self.bar3_cagr,
            "survived_development": self.survived_development,
        }


def judge_h1(instrument: str, label: str, result: TimingResult) -> H1Verdict:
    """Success bars 1-3 of rulebook §3.1 (bar 4 is the validation window)."""
    s, b = result.strategy, result.buy_and_hold
    bar1 = (s.sharpe or float("-inf")) > (b.sharpe or float("-inf"))
    bar2 = (
        s.max_drawdown is not None
        and b.max_drawdown is not None
        and abs(s.max_drawdown) <= 0.75 * abs(b.max_drawdown)
    )
    bar3 = (
        s.cagr is not None and b.cagr is not None and s.cagr >= b.cagr - 0.01
    )
    return H1Verdict(
        instrument=instrument,
        label=label,
        result=result,
        bar1_sharpe=bar1,
        bar2_drawdown=bar2,
        bar3_cagr=bar3,
        survived_development=bar1 and bar2 and bar3,
    )


def monthly_closes(prices: Series, cal: TradingCalendar) -> Series:
    """Month-end close series over the instrument's full history (for the
    Faber monthly-SMA signal)."""
    if not prices.dates:
        return Series([], [])
    ends = cal.month_ends(prices.dates[0], prices.dates[-1])
    ds: list[date] = []
    vs: list[float] = []
    for m in ends:
        v = prices.value_on_or_before(m)
        if v is not None:
            ds.append(m)
            vs.append(v)
    return Series(ds, vs)


def build_eval_dates(
    cal: TradingCalendar, start: date, end: date, frequency: str
) -> list[date]:
    if frequency == "monthly":
        return cal.month_ends(start, end)
    if frequency == "weekly":
        out: list[date] = []
        for i, d in enumerate(cal.days):
            if d < start or d > end:
                continue
            is_last_of_week = (
                i + 1 >= len(cal.days)
                or cal.days[i + 1].isocalendar()[:2] != d.isocalendar()[:2]
            )
            if is_last_of_week:
                out.append(d)
        return out
    raise ValueError(f"unknown frequency {frequency!r}")


SignalFactory = Callable[[Series, TradingCalendar], Signal]
