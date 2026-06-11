"""H2 fixture tests: scoring, no-lookahead, terciles (no network)."""
from datetime import date

from compass.backtest.h2_reality import (
    cross_sectional_zscores,
    member_metrics,
    quarter_ends,
    terciles,
)
from compass.backtest.loader import FundRow, Market


def _market_with_fundamentals(rows_by_ticker) -> Market:
    return Market(prices={}, volumes={}, fundamentals=rows_by_ticker)


def _q(fqe: date, reported: date, revenue: float, op: float, surprise: float | None = 1.0):
    return FundRow(
        fiscal_quarter_end=fqe, report_date=reported,
        revenue=revenue, operating_income=op, surprise_pct=surprise,
    )


def test_member_metrics_yoy_growth_and_margin_delta():
    rows = [
        _q(date(2018, 12, 31), date(2019, 2, 1), revenue=100.0, op=10.0),
        _q(date(2019, 12, 31), date(2020, 2, 1), revenue=150.0, op=30.0),
    ]
    market = _market_with_fundamentals({"X": rows})
    m = member_metrics(market, "X", date(2020, 3, 1))
    assert abs(m["rev_growth"] - 0.5) < 1e-12
    assert abs(m["margin_delta"] - (30 / 150 - 10 / 100)) < 1e-12


def test_member_metrics_no_lookahead():
    rows = [
        _q(date(2018, 12, 31), date(2019, 2, 1), revenue=100.0, op=10.0),
        _q(date(2019, 12, 31), date(2020, 2, 1), revenue=150.0, op=30.0),
    ]
    market = _market_with_fundamentals({"X": rows})
    # As-of Jan 2020: Q4-2019 (reported Feb 1) must be invisible.
    m = member_metrics(market, "X", date(2020, 1, 15))
    assert m is not None
    # Latest visible quarter is 2018Q4, which has no year-ago row -> None
    assert m["rev_growth"] is None
    # As-of exactly the report date: still invisible (report_date < on, strict)
    m2 = member_metrics(market, "X", date(2020, 2, 1))
    assert m2["rev_growth"] is None


def test_member_with_no_reported_rows_is_excluded():
    rows = [
        FundRow(date(2019, 12, 31), None, 100.0, 10.0, None),  # no report_date
    ]
    market = _market_with_fundamentals({"X": rows})
    assert member_metrics(market, "X", date(2020, 6, 1)) is None


def test_zscores_skip_missing_and_handle_zero_variance():
    z = cross_sectional_zscores({"A": 1.0, "B": 3.0, "C": None})
    assert set(z) == {"A", "B"}
    assert z["A"] < 0 < z["B"]
    z_flat = cross_sectional_zscores({"A": 2.0, "B": 2.0})
    assert z_flat == {"A": 0.0, "B": 0.0}
    assert cross_sectional_zscores({"A": 1.0, "B": None}) == {}


def test_terciles_3_4_3_for_ten():
    ranked = [f"t{i}" for i in range(10)]
    top, mid, bot = terciles(ranked)
    assert (len(top), len(mid), len(bot)) == (3, 4, 3)
    assert top == ["t0", "t1", "t2"]
    assert bot == ["t7", "t8", "t9"]


def test_quarter_ends():
    qs = quarter_ends(date(2006, 1, 1), date(2007, 1, 1))
    assert qs == [
        date(2006, 3, 31), date(2006, 6, 30), date(2006, 9, 30), date(2006, 12, 31),
    ]
