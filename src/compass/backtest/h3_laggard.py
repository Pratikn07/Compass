"""H3 laggard radar (rulebook §3.3): when a theme leader has run hard and a
fundamentally comparable peer badly lags, does buying the laggard beat just
holding the theme basket?

Each trade is an independent, equal-notional unit (no sizing — Phase 2 judges
the signal). Known approximation, recorded: the $2B market-cap floor is
approximated by the $10M median-dollar-volume floor (free data has no
point-in-time market cap); this is noted in every result file.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from .calendar import TradingCalendar
from .costs import net_trade_return
from .h2_reality import member_metrics
from .loader import Market
from .scorecard import binomial_ci_95, mean_median, sample_label
from .series import Series, sma_at


@dataclass(frozen=True)
class H3Trade:
    theme: str
    ticker: str
    leader: str
    entry: date
    exit: date
    exit_reason: str  # "held_126_bars" | "trend_off"
    laggard_net: float
    basket_net: float

    @property
    def excess(self) -> float:
        return self.laggard_net - self.basket_net

    def to_dict(self) -> dict:
        return {
            "theme": self.theme, "ticker": self.ticker, "leader": self.leader,
            "entry": self.entry.isoformat(), "exit": self.exit.isoformat(),
            "exit_reason": self.exit_reason, "laggard_net": self.laggard_net,
            "basket_net": self.basket_net, "excess": self.excess,
        }


@dataclass
class H3Result:
    n_trades: int
    mean_excess: float | None
    median_excess: float | None
    base_rate: float | None
    ci_95: tuple[float, float] | None
    sample: str
    bar1_mean_excess: bool
    bar2_base_rate: bool
    bar3_sample: bool
    survived_development: bool
    trades: list[H3Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "mean_excess": self.mean_excess,
            "median_excess": self.median_excess,
            "base_rate": self.base_rate,
            "ci_95": list(self.ci_95) if self.ci_95 else None,
            "sample": self.sample,
            "bar1_mean_excess": self.bar1_mean_excess,
            "bar2_base_rate_beats_coinflip": self.bar2_base_rate,
            "bar3_sample_at_least_suggestive": self.bar3_sample,
            "survived_development": self.survived_development,
            "market_cap_floor_note": (
                "approximated by $10M median dollar volume (no point-in-time "
                "market cap on free data)"
            ),
            "trades": [t.to_dict() for t in self.trades],
        }


def _r_over_lookback(prices: Series, t: date, lookback: int) -> float | None:
    i = prices.idx_on_or_before(t)
    if i is None or i < lookback:
        return None
    base = prices.values[i - lookback]
    return prices.values[i] / base - 1.0 if base > 0 else None


def _median_dollar_volume(
    prices: Series, volumes: Series, t: date, bars: int
) -> float | None:
    i = prices.idx_on_or_before(t)
    if i is None or i + 1 < bars:
        return None
    window_dates = prices.dates[i + 1 - bars : i + 1]
    dvs = []
    for d in window_dates:
        p = prices.value_at(d)
        v = volumes.value_at(d)
        if p is not None and v is not None:
            dvs.append(p * v)
    return statistics.median(dvs) if dvs else None


def _gross_return(prices: Series, entry: date, exit: date) -> float | None:
    a = prices.value_on_or_before(entry)
    b = prices.value_on_or_before(exit)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def run_h3(
    *,
    market: Market,
    themes: list,
    active_members_fn,
    theme_indexes: dict[str, Series],
    cal: TradingCalendar,
    start: date,
    end: date,
    lookback: int = 90,
    leader_min: float = 0.30,
    gap: float = 0.25,
    hold_bars: int = 126,
    rev_tolerance: float = 0.05,
    dollar_volume_min: float = 10_000_000.0,
    sma_n: int = 200,
) -> H3Result:
    trades: list[H3Trade] = []
    open_until: dict[str, date] = {}  # ticker -> exit date of open position

    month_ends_all = cal.month_ends(start, end)

    for t in month_ends_all:
        for theme in themes:
            idx = theme_indexes.get(theme.slug)
            if idx is None:
                continue
            # Theme must be in H1 uptrend at T.
            idx_val = idx.value_on_or_before(t)
            idx_sma = sma_at(idx, t, sma_n)
            if idx_val is None or idx_sma is None or idx_val <= idx_sma:
                continue

            members = active_members_fn(theme.slug, t)
            r90: dict[str, float] = {}
            for m in members:
                p = market.prices.get(m.ticker)
                if p is None:
                    continue
                r = _r_over_lookback(p, t, lookback)
                if r is not None:
                    r90[m.ticker] = r
            if len(r90) < 2:
                continue
            leader, leader_r = max(r90.items(), key=lambda kv: kv[1])
            if leader_r < leader_min:
                continue

            # Theme median rev growth as of T (reported data only).
            growths = {}
            for m in members:
                mm = member_metrics(market, m.ticker, t)
                if mm is not None and mm["rev_growth"] is not None:
                    growths[m.ticker] = mm["rev_growth"]
            if not growths:
                continue
            median_growth = statistics.median(growths.values())

            for ticker, r in r90.items():
                if ticker == leader or r > leader_r - gap:
                    continue
                if ticker in open_until and t < open_until[ticker]:
                    continue
                g = growths.get(ticker)
                if g is None or g < median_growth - rev_tolerance:
                    continue
                prices = market.prices[ticker]
                vols = market.volumes.get(ticker)
                if vols is None:
                    continue
                dv = _median_dollar_volume(prices, vols, t, lookback)
                if dv is None or dv < dollar_volume_min:
                    continue

                entry = cal.next_day(t)
                if entry is None:
                    continue
                # Exit: 126 bars, or the theme trend turning off at a later
                # monthly evaluation (exit executes the next trading day).
                exit_bar = cal.shift(entry, hold_bars)
                if exit_bar is None:
                    continue
                exit_date, reason = exit_bar, "held_126_bars"
                for t2 in month_ends_all:
                    if t2 <= t or t2 >= exit_bar:
                        continue
                    v2, s2 = idx.value_on_or_before(t2), sma_at(idx, t2, sma_n)
                    if v2 is not None and s2 is not None and v2 <= s2:
                        early = cal.next_day(t2)
                        if early is not None and early < exit_bar:
                            exit_date, reason = early, "trend_off"
                        break

                lag_gross = _gross_return(prices, entry, exit_date)
                bask_gross = _gross_return(idx, entry, exit_date)
                if lag_gross is None or bask_gross is None:
                    continue
                trades.append(
                    H3Trade(
                        theme=theme.slug, ticker=ticker, leader=leader,
                        entry=entry, exit=exit_date, exit_reason=reason,
                        laggard_net=net_trade_return(lag_gross, entry, exit_date),
                        basket_net=net_trade_return(bask_gross, entry, exit_date),
                    )
                )
                open_until[ticker] = exit_date

    n = len(trades)
    if n == 0:
        return H3Result(
            n_trades=0, mean_excess=None, median_excess=None, base_rate=None,
            ci_95=None, sample="too_few", bar1_mean_excess=False,
            bar2_base_rate=False, bar3_sample=False,
            survived_development=False, trades=[],
        )

    excesses = [tr.excess for tr in trades]
    mean_x, median_x = mean_median(excesses)
    wins = sum(1 for x in excesses if x > 0)
    base = wins / n
    ci = binomial_ci_95(wins, n)
    bar1 = mean_x is not None and mean_x > 0
    bar2 = ci is not None and ci[0] > 0.5
    bar3 = n >= 30
    return H3Result(
        n_trades=n, mean_excess=mean_x, median_excess=median_x,
        base_rate=base, ci_95=ci, sample=sample_label(n),
        bar1_mean_excess=bar1, bar2_base_rate=bar2, bar3_sample=bar3,
        survived_development=bar1 and bar2 and bar3, trades=trades,
    )
