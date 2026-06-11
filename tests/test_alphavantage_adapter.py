"""Pure-parse tests for the Alpha Vantage fundamentals adapter (no network)."""
from datetime import date

import pytest

from compass.adapters.alphavantage import (
    RateLimited,
    _check_throttle,
    merge_fundamentals,
    parse_earnings,
    parse_income_statement,
)

EARNINGS_FIXTURE = {
    "symbol": "MU",
    "quarterlyEarnings": [
        {
            "fiscalDateEnding": "2019-08-29",
            "reportedDate": "2019-09-26",
            "reportedEPS": "0.56",
            "estimatedEPS": "0.51",
            "surprise": "0.05",
            "surprisePercentage": "9.8039",
        },
        {
            "fiscalDateEnding": "2019-05-30",
            "reportedDate": "2019-06-25",
            "reportedEPS": "1.05",
            "estimatedEPS": "None",  # AV uses literal "None" strings
            "surprise": "None",
            "surprisePercentage": "None",
        },
        {"fiscalDateEnding": "garbled", "reportedDate": "2019-03-20"},  # skipped
    ],
}

INCOME_FIXTURE = {
    "symbol": "MU",
    "quarterlyReports": [
        {
            "fiscalDateEnding": "2019-08-29",
            "totalRevenue": "4870000000",
            "operatingIncome": "650000000",
        },
        {
            "fiscalDateEnding": "2019-02-28",  # income-only quarter (outer join)
            "totalRevenue": "5835000000",
            "operatingIncome": "None",
        },
    ],
}


def test_parse_earnings_normalizes_and_skips_garbled():
    out = parse_earnings(EARNINGS_FIXTURE)
    assert set(out) == {date(2019, 8, 29), date(2019, 5, 30)}
    q = out[date(2019, 8, 29)]
    assert q["report_date"] == date(2019, 9, 26)
    assert q["eps_actual"] == 0.56
    assert q["surprise_pct"] == pytest.approx(9.8039)
    # "None" strings become real Nones, never fabricated numbers
    assert out[date(2019, 5, 30)]["eps_estimate"] is None


def test_parse_income_statement():
    out = parse_income_statement(INCOME_FIXTURE)
    assert out[date(2019, 8, 29)]["revenue"] == 4870000000.0
    assert out[date(2019, 2, 28)]["operating_income"] is None


def test_merge_is_outer_join_with_nones():
    rows = merge_fundamentals(
        "MU", parse_earnings(EARNINGS_FIXTURE), parse_income_statement(INCOME_FIXTURE)
    )
    by_fqe = {r.fiscal_quarter_end: r for r in rows}
    assert set(by_fqe) == {date(2019, 2, 28), date(2019, 5, 30), date(2019, 8, 29)}
    # Both endpoints present
    full = by_fqe[date(2019, 8, 29)]
    assert full.report_date == date(2019, 9, 26)
    assert full.revenue == 4870000000.0
    # Earnings-only quarter: no revenue
    assert by_fqe[date(2019, 5, 30)].revenue is None
    # Income-only quarter: no report_date (unusable in Phase 2, kept honestly)
    assert by_fqe[date(2019, 2, 28)].report_date is None
    assert all(r.source == "alphavantage" for r in rows)


def test_throttle_detection_raises():
    with pytest.raises(RateLimited):
        _check_throttle({"Information": "API rate limit is 25 requests per day"})
    with pytest.raises(RateLimited):
        _check_throttle({"Note": "Thank you ... call frequency is 5 calls per minute"})
    _check_throttle({"quarterlyEarnings": []})  # no throttle -> no raise
