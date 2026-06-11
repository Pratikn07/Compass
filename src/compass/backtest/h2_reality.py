"""H2 financial reality (rulebook §3.2): do themes with real fundamentals beat
hype-only themes over the next 3-6 months? A ranking test, not a trading rule.

No-lookahead: a quarter's numbers exist only after its report_date (loader
enforces report_date < as-of). Missing metrics are omitted from the mean,
never fabricated.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from .calendar import TradingCalendar
from .costs import TRADING_COST_PER_SIDE
from .loader import Market
from .scorecard import mean_median, sample_label
from .series import Series

ROUND_TRIP_COST = (1.0 - TRADING_COST_PER_SIDE) ** 2


def member_metrics(market: Market, ticker: str, on: date) -> dict[str, float | None] | None:
    """rev_growth (YoY %), margin_delta (YoY pp), surprise (%) from the latest
    quarter reported strictly before `on`."""
    rows = market.reported_fundamentals(ticker, on)
    if not rows:
        return None
    latest = rows[-1]

    def year_ago_row():
        target = latest.fiscal_quarter_end - timedelta(days=365)
        candidates = [
            r for r in rows
            if abs((r.fiscal_quarter_end - target).days) <= 45
        ]
        return candidates[-1] if candidates else None

    prior = year_ago_row()

    rev_growth = None
    if prior is not None and latest.revenue and prior.revenue:
        rev_growth = latest.revenue / prior.revenue - 1.0

    margin_delta = None
    if (
        prior is not None
        and latest.revenue and prior.revenue
        and latest.operating_income is not None and prior.operating_income is not None
    ):
        margin_delta = (
            latest.operating_income / latest.revenue
            - prior.operating_income / prior.revenue
        )

    return {
        "rev_growth": rev_growth,
        "margin_delta": margin_delta,
        "surprise": latest.surprise_pct,
    }


def cross_sectional_zscores(values: dict[str, float | None]) -> dict[str, float]:
    present = {k: v for k, v in values.items() if v is not None}
    if len(present) < 2:
        return {}
    mean = statistics.mean(present.values())
    sd = statistics.pstdev(present.values())
    if sd == 0:
        return {k: 0.0 for k in present}
    return {k: (v - mean) / sd for k, v in present.items()}


def theme_scores(
    market: Market, themes: list, active_members_fn, on: date,
    use_median_member: bool = True,
) -> dict[str, float | None]:
    """theme_slug -> median (or mean, for the sensitivity sweep) member score
    (rulebook §3.2). Metrics are z-scored across ALL universe members visible
    that quarter."""
    member_rows: dict[str, dict[str, float | None]] = {}
    member_theme: dict[str, str] = {}
    for theme in themes:
        for m in active_members_fn(theme.slug, on):
            metrics = member_metrics(market, m.ticker, on)
            if metrics is not None:
                member_rows[m.ticker] = metrics
                member_theme[m.ticker] = theme.slug

    z_by_metric = {
        metric: cross_sectional_zscores(
            {t: rows.get(metric) for t, rows in member_rows.items()}
        )
        for metric in ("rev_growth", "margin_delta", "surprise")
    }

    member_score: dict[str, float] = {}
    for ticker in member_rows:
        zs = [z[ticker] for z in z_by_metric.values() if ticker in z]
        if zs:
            member_score[ticker] = sum(zs) / len(zs)

    out: dict[str, float | None] = {}
    agg = statistics.median if use_median_member else statistics.mean
    for theme in themes:
        scores = [
            member_score[t] for t, slug in member_theme.items()
            if slug == theme.slug and t in member_score
        ]
        out[theme.slug] = agg(scores) if scores else None
    return out


def terciles(ranked: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Top/middle/bottom; remainders go to the middle (3/4/3 for 10)."""
    n = len(ranked)
    k = n // 3
    return ranked[:k], ranked[k : n - k], ranked[n - k :]


@dataclass
class H2Result:
    horizon_bars: int
    n_quarters: int
    spread_annualized: float | None  # top minus bottom
    top_mean: float | None
    middle_mean: float | None
    bottom_mean: float | None
    all_themes_mean: float | None  # baseline: own everything
    monotonic: bool
    bar1_spread: bool
    bar2_monotonic: bool
    survived_development: bool
    sample: str
    per_quarter: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def quarter_ends(start: date, end: date) -> list[date]:
    out = []
    y, q = start.year, (start.month - 1) // 3 + 1
    while True:
        month = q * 3
        day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
        d = date(y, month, day)
        if d > end:
            return out
        if d >= start:
            out.append(d)
        q += 1
        if q == 5:
            q, y = 1, y + 1


def run_h2(
    *,
    market: Market,
    themes: list,
    active_members_fn,
    theme_indexes: dict[str, Series],
    cal: TradingCalendar,
    start: date,
    end: date,
    horizon_bars: int = 126,
    use_median_member: bool = True,
) -> H2Result:
    per_quarter: list[dict] = []
    tops, mids, bots, alls = [], [], [], []

    for t in quarter_ends(start, end):
        scores = theme_scores(
            market, themes, active_members_fn, t, use_median_member=use_median_member
        )
        scored = [(slug, s) for slug, s in scores.items() if s is not None]
        if len(scored) < 3:
            continue
        ranked = [slug for slug, _ in sorted(scored, key=lambda x: x[1], reverse=True)]
        top, mid, bot = terciles(ranked)

        entry = cal.next_day(t)
        if entry is None:
            continue

        def fwd(slug: str, entry: date = entry) -> float | None:
            idx = theme_indexes.get(slug)
            if idx is None:
                return None
            i = idx.idx_on_or_before(entry)
            if i is None or i + horizon_bars >= len(idx):
                return None
            gross = idx.values[i + horizon_bars] / idx.values[i] - 1.0
            return (1.0 + gross) * ROUND_TRIP_COST - 1.0

        def bucket(slugs: list[str]) -> float | None:
            rets = [r for r in (fwd(s) for s in slugs) if r is not None]
            return sum(rets) / len(rets) if rets else None

        rt, rm, rb = bucket(top), bucket(mid), bucket(bot)
        ra = bucket(ranked)
        if rt is None or rb is None:
            continue
        tops.append(rt)
        mids.append(rm if rm is not None else 0.0)
        bots.append(rb)
        if ra is not None:
            alls.append(ra)
        per_quarter.append(
            {"as_of": t.isoformat(), "top": rt, "middle": rm, "bottom": rb,
             "ranking": ranked}
        )

    n = len(tops)
    if n == 0:
        return H2Result(
            horizon_bars=horizon_bars, n_quarters=0, spread_annualized=None,
            top_mean=None, middle_mean=None, bottom_mean=None, all_themes_mean=None,
            monotonic=False, bar1_spread=False, bar2_monotonic=False,
            survived_development=False, sample="too_few", per_quarter=[],
        )

    top_mean, _ = mean_median(tops)
    mid_mean, _ = mean_median(mids)
    bot_mean, _ = mean_median(bots)
    all_mean, _ = mean_median(alls)
    periods_per_year = 252 / horizon_bars
    spread_ann = (top_mean - bot_mean) * periods_per_year
    monotonic = top_mean >= mid_mean >= bot_mean
    bar1 = spread_ann >= 0.02
    return H2Result(
        horizon_bars=horizon_bars,
        n_quarters=n,
        spread_annualized=spread_ann,
        top_mean=top_mean,
        middle_mean=mid_mean,
        bottom_mean=bot_mean,
        all_themes_mean=all_mean,
        monotonic=monotonic,
        bar1_spread=bar1,
        bar2_monotonic=monotonic,
        survived_development=bar1 and monotonic,
        sample=sample_label(n),
        per_quarter=per_quarter,
    )
