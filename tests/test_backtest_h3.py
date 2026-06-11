"""H3 fixture tests: trigger, filters, and excess-vs-basket scoring."""
from dataclasses import dataclass
from datetime import date, timedelta

from compass.backtest.calendar import TradingCalendar
from compass.backtest.h3_laggard import run_h3
from compass.backtest.loader import FundRow, Market
from compass.backtest.series import Series


@dataclass(frozen=True)
class _Theme:
    slug: str


@dataclass(frozen=True)
class _Member:
    ticker: str


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(days, growth_per_bar, base=100.0):
    vals, v = [], base
    for _ in days:
        vals.append(v)
        v *= 1 + growth_per_bar
    return Series(days, vals)


def _fund(rev_now: float, rev_prior: float):
    return [
        FundRow(date(2019, 6, 30), date(2019, 8, 1), rev_prior, 10.0, None),
        FundRow(date(2020, 6, 30), date(2020, 8, 1), rev_now, 12.0, None),
    ]


def _setup(laggard_growth=0.004, laggard_rev=(120.0, 100.0), laggard_volume=1_000_000.0):
    """Leader rips (+~0.5%/bar), laggard flat-then-specified, theme trending up."""
    days = _weekdays(date(2020, 1, 1), 500)
    cal = TradingCalendar(days)

    leader = _series(days, 0.005)
    # Laggard: flat for the first 300 bars, then grows at laggard_growth
    lag_vals, v = [], 100.0
    for i in range(len(days)):
        if i >= 300:
            v *= 1 + laggard_growth
        lag_vals.append(v)
    laggard = Series(days, lag_vals)

    volume = Series(days, [laggard_volume] * len(days))
    big_volume = Series(days, [10_000_000.0] * len(days))

    market = Market(
        prices={"LEAD": leader, "LAG": laggard},
        volumes={"LEAD": big_volume, "LAG": volume},
        fundamentals={
            "LEAD": _fund(150.0, 100.0),            # +50% rev growth
            "LAG": _fund(laggard_rev[0], laggard_rev[1]),
        },
    )
    idx = _series(days, 0.003)  # rising theme index, comfortably above SMA
    themes = [_Theme("synth")]

    def active(slug, on):
        return [_Member("LEAD"), _Member("LAG")]

    return market, themes, active, {"synth": idx}, cal, days


def test_trade_fires_and_catchup_wins():
    market, themes, active, idxs, cal, days = _setup(
        laggard_growth=0.006,                 # catches up hard after entry
        laggard_rev=(120.0, 100.0),           # +20% growth, median is 35% -> within 5pt? no:
    )
    # median growth of {50%, 20%} = 35%; tolerance 5pt -> LAG (20%) excluded.
    # Use a generous tolerance to verify the mechanics fire at all.
    result = run_h3(
        market=market, themes=themes, active_members_fn=active,
        theme_indexes=idxs, cal=cal, start=days[250], end=days[-1],
        sma_n=50, hold_bars=60, rev_tolerance=0.20,
    )
    assert result.n_trades >= 1
    tr = result.trades[0]
    assert tr.ticker == "LAG" and tr.leader == "LEAD"
    assert tr.entry > days[250]  # executes after the signal bar
    assert result.mean_excess is not None


def test_fundamentals_comparability_filter_excludes_weak_laggard():
    market, themes, active, idxs, cal, days = _setup(laggard_rev=(80.0, 100.0))  # -20%
    result = run_h3(
        market=market, themes=themes, active_members_fn=active,
        theme_indexes=idxs, cal=cal, start=days[250], end=days[-1],
        sma_n=50, hold_bars=60, rev_tolerance=0.05,
    )
    assert result.n_trades == 0  # lagging for a reason -> no trade


def test_dollar_volume_floor_excludes_illiquid():
    market, themes, active, idxs, cal, days = _setup(laggard_volume=10.0)
    result = run_h3(
        market=market, themes=themes, active_members_fn=active,
        theme_indexes=idxs, cal=cal, start=days[250], end=days[-1],
        sma_n=50, hold_bars=60, rev_tolerance=0.20,
    )
    assert result.n_trades == 0


def test_no_trade_when_theme_trend_off():
    market, themes, active, idxs, cal, days = _setup()
    falling_idx = Series(days, [100.0 * (1 - 0.002) ** i for i in range(len(days))])
    result = run_h3(
        market=market, themes=themes, active_members_fn=active,
        theme_indexes={"synth": falling_idx}, cal=cal,
        start=days[250], end=days[-1], sma_n=50, hold_bars=60, rev_tolerance=0.20,
    )
    assert result.n_trades == 0
