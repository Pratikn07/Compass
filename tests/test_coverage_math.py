"""Coverage math used by the Phase 1 -> 2 gate evidence."""
from datetime import date, timedelta

from compass.ingest import expected_quarters, price_coverage


def _weekdays(start: date, n: int) -> list[date]:
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def test_full_coverage_is_100pct():
    spy = _weekdays(date(2006, 1, 2), 100)
    pct, have, expected = price_coverage(spy, spy)
    assert pct == 1.0
    assert have == expected == 100


def test_late_listing_not_penalized():
    spy = _weekdays(date(2006, 1, 2), 100)
    late = spy[60:]  # listed later, complete since listing
    pct, have, expected = price_coverage(late, spy)
    assert pct == 1.0
    assert expected == 40


def test_gaps_lower_coverage():
    spy = _weekdays(date(2006, 1, 2), 100)
    gappy = spy[:50] + spy[60:]  # missing 10 of 100 days
    pct, have, expected = price_coverage(gappy, spy)
    assert expected == 100
    assert have == 90
    assert pct == 0.9


def test_empty_ticker_days():
    spy = _weekdays(date(2006, 1, 2), 10)
    pct, have, expected = price_coverage([], spy)
    assert pct == 0.0 and have == 0


def test_expected_quarters_full_dev_window():
    # 2006-01-01 -> 2019-12-31 is 14 years horizontally = 55-56 quarters
    q = expected_quarters(date(2006, 1, 1), date(2019, 12, 31))
    assert q == 55


def test_expected_quarters_after_window_is_zero():
    assert expected_quarters(date(2020, 6, 1), date(2019, 12, 31)) == 0


def test_expected_quarters_partial():
    assert expected_quarters(date(2019, 1, 1), date(2019, 12, 31)) == 3
