"""Nightly brain: parity with the harness, idempotency, recommendation rules."""
from datetime import date, timedelta

from compass.backtest.calendar import TradingCalendar
from compass.backtest.loader import FundRow, Market
from compass.backtest.series import Series, sma_at
from compass.nightly import (
    H2_EVIDENCE,
    build_recommendations,
    build_theme_state_row,
)


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _rising(days, rate=0.001, base=100.0):
    vals, v = [], base
    for _ in days:
        vals.append(v)
        v *= 1 + rate
    return Series(days, vals)


# ---- parity: the nightly state IS the harness math ----

def test_state_row_parity_with_harness_sma():
    days = _weekdays(date(2024, 1, 1), 250)
    idx = _rising(days)
    on = days[-1]
    row = build_theme_state_row("synth", idx, on, prev=None)
    # Byte-equal numbers with the harness's own functions:
    assert row["index_level"] == idx.value_on_or_before(on)
    assert row["sma200"] == sma_at(idx, on, 200)
    assert row["trend_on"] is True  # rising series above its SMA
    assert row["days_in_state"] == 1


def test_state_row_days_in_state_counts_and_resets():
    days = _weekdays(date(2024, 1, 1), 250)
    idx = _rising(days)
    on = days[-1]
    same = build_theme_state_row("s", idx, on, prev={"trend_on": True, "days_in_state": 7})
    assert same["days_in_state"] == 8
    flipped = build_theme_state_row("s", idx, on, prev={"trend_on": False, "days_in_state": 7})
    assert flipped["days_in_state"] == 1


def test_state_row_no_sma_means_trend_unknown():
    days = _weekdays(date(2024, 1, 1), 50)  # < 200 bars
    idx = _rising(days)
    row = build_theme_state_row("s", idx, days[-1], prev=None)
    assert row["sma200"] is None
    assert row["trend_on"] is None  # unknown, never guessed


def test_state_builder_is_idempotent():
    days = _weekdays(date(2024, 1, 1), 250)
    idx = _rising(days)
    prev = {"trend_on": True, "days_in_state": 3}
    once = build_theme_state_row("s", idx, days[-1], prev)
    twice = build_theme_state_row("s", idx, days[-1], prev)
    assert once == twice  # same inputs -> same row -> upsert no-ops


# ---- recommendations ----

def _market_three_themes(days):
    """Growers boom, middlers drift, shrinkers decline. Reports filed Aug 1."""
    fast = _rising(days, 0.002)
    slow = _rising(days, 0.0001)

    def fund(rev_now, rev_prior):
        return [
            FundRow(date(2024, 6, 30), date(2024, 8, 1), rev_prior, rev_prior * 0.1, 1.0),
            FundRow(date(2025, 6, 30), date(2025, 8, 1), rev_now, rev_now * 0.15, 1.0),
        ]

    return Market(
        prices={t: fast for t in ("A1", "A2")} | {t: slow for t in ("M1", "M2", "B1", "B2")}
        | {"SPY": _rising(days)},
        volumes={},
        fundamentals={
            "A1": fund(200.0, 100.0), "A2": fund(190.0, 100.0),
            "M1": fund(110.0, 100.0), "M2": fund(105.0, 100.0),
            "B1": fund(80.0, 100.0), "B2": fund(85.0, 100.0),
        },
    )


def test_non_quarter_day_writes_explicit_none_row():
    days = _weekdays(date(2025, 1, 1), 300)
    cal = TradingCalendar(days)
    market = _market_three_themes(days)
    on = date(2025, 11, 18)  # mid-quarter
    rows = build_recommendations(market, cal, on)
    assert len(rows) == 1
    assert rows[0]["action"] == "none"
    assert rows[0]["hypothesis"] == "none"
    assert "nothing to do" in rows[0]["reasoning"]["note"]


def test_quarter_end_plus_one_ranks_and_recommends():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Theme:
        slug: str
        etf_ticker: str | None = None

    @dataclass(frozen=True)
    class _Member:
        ticker: str

    days = _weekdays(date(2025, 1, 1), 300)
    cal = TradingCalendar(days)
    market = _market_three_themes(days)
    q_end = date(2025, 9, 30)
    on = cal.next_day(q_end)

    import compass.nightly as nightly
    themes = [_Theme("growers"), _Theme("middlers"), _Theme("shrinkers")]
    rosters = {
        "growers": [_Member("A1"), _Member("A2")],
        "middlers": [_Member("M1"), _Member("M2")],
        "shrinkers": [_Member("B1"), _Member("B2")],
    }

    def fake_active(slug, d):
        return rosters[slug]

    orig_themes, orig_active = nightly.THEMES, nightly.active_members
    nightly.THEMES, nightly.active_members = themes, fake_active
    try:
        rows = nightly.build_recommendations(market, cal, on)
    finally:
        nightly.THEMES, nightly.active_members = orig_themes, orig_active

    by_slug = {r["instrument"]: r for r in rows}
    assert by_slug["growers"]["action"] == "consider_enter"
    assert by_slug["shrinkers"]["action"] == "consider_exit"
    # Honesty payload present: base rate + the magnitude-not-consistency claim
    assert by_slug["growers"]["base_rate"] == H2_EVIDENCE["combined_base_rate"]
    assert "magnitude" in by_slug["growers"]["reasoning"]["claim"]
    assert by_slug["growers"]["reasoning"]["rank"] == 1


def test_recommendations_are_idempotent():
    days = _weekdays(date(2025, 1, 1), 300)
    cal = TradingCalendar(days)
    market = _market_three_themes(days)
    on = date(2025, 11, 18)
    assert build_recommendations(market, cal, on) == build_recommendations(market, cal, on)
