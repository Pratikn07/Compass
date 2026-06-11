"""Pure-parse tests for the EDGAR companyfacts adapter (no network)."""
from datetime import date

from compass.adapters.edgar import parse_quarterly_fundamentals


def _entry(start, end, val, filed):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": "x"}


def _payload(revenues, op_income):
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": revenues}},
                "OperatingIncomeLoss": {"units": {"USD": op_income}},
            }
        }
    }


def test_direct_quarters_with_earliest_filed_wins():
    revenues = [
        _entry("2018-01-01", "2018-03-31", 100.0, "2018-04-25"),
        # Restated value in a later filing must NOT win:
        _entry("2018-01-01", "2018-03-31", 999.0, "2019-04-25"),
    ]
    rows = parse_quarterly_fundamentals("X", _payload(revenues, []))
    assert len(rows) == 1
    assert rows[0].fiscal_quarter_end == date(2018, 3, 31)
    assert rows[0].revenue == 100.0  # as originally reported
    assert rows[0].report_date == date(2018, 4, 25)
    assert rows[0].source == "edgar"


def test_q4_derived_from_annual_minus_three_quarters():
    revenues = [
        _entry("2018-01-01", "2018-03-31", 100.0, "2018-04-25"),
        _entry("2018-04-01", "2018-06-30", 110.0, "2018-07-25"),
        _entry("2018-07-01", "2018-09-30", 120.0, "2018-10-25"),
        _entry("2018-01-01", "2018-12-31", 450.0, "2019-02-15"),  # annual (10-K)
    ]
    rows = parse_quarterly_fundamentals("X", _payload(revenues, []))
    by_fqe = {r.fiscal_quarter_end: r for r in rows}
    q4 = by_fqe[date(2018, 12, 31)]
    assert q4.revenue == 450.0 - (100.0 + 110.0 + 120.0)
    # Q4 is only knowable once the 10-K is filed:
    assert q4.report_date == date(2019, 2, 15)


def test_q4_not_derived_when_a_quarter_is_missing():
    revenues = [
        _entry("2018-01-01", "2018-03-31", 100.0, "2018-04-25"),
        _entry("2018-04-01", "2018-06-30", 110.0, "2018-07-25"),
        # Q3 missing
        _entry("2018-01-01", "2018-12-31", 450.0, "2019-02-15"),
    ]
    rows = parse_quarterly_fundamentals("X", _payload(revenues, []))
    ends = {r.fiscal_quarter_end for r in rows}
    assert date(2018, 12, 31) not in ends  # skip, don't guess


def test_revenue_and_op_income_outer_join():
    revenues = [_entry("2018-01-01", "2018-03-31", 100.0, "2018-04-25")]
    op = [_entry("2018-04-01", "2018-06-30", 20.0, "2018-07-25")]
    rows = parse_quarterly_fundamentals("X", _payload(revenues, op))
    by_fqe = {r.fiscal_quarter_end: r for r in rows}
    assert by_fqe[date(2018, 3, 31)].revenue == 100.0
    assert by_fqe[date(2018, 3, 31)].operating_income is None
    assert by_fqe[date(2018, 6, 30)].operating_income == 20.0


def test_garbled_entries_skipped():
    revenues = [
        {"start": "bad", "end": "2018-03-31", "val": 1, "filed": "2018-04-25"},
        _entry("2018-01-01", "2018-03-31", 100.0, "2018-04-25"),
    ]
    rows = parse_quarterly_fundamentals("X", _payload(revenues, []))
    assert len(rows) == 1 and rows[0].revenue == 100.0
