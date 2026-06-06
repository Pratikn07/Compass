from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


def test_earnings_announcement_normalizes_ticker_and_reporttime() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(
        ticker="mu",
        report_date=date(2024, 6, 26),
        report_time="amc",
        eps_estimate=1.2,
        eps_actual=1.45,
        surprise_pct=20.8,
    )
    assert ann.ticker == "MU"
    assert ann.report_time == "AMC"
    assert ann.eps_actual == 1.45


def test_earnings_announcement_unknown_reporttime_default() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))
    assert ann.report_time == "UNKNOWN"
    assert ann.eps_estimate is None


def test_earnings_announcement_is_frozen() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))
    with pytest.raises(ValidationError):
        ann.ticker = "NVDA"  # type: ignore[misc]
