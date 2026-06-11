from datetime import date, datetime, timezone

from vanta import models


def test_news_item_to_row_includes_ticker_and_published():
    item = models.NewsItem(
        ticker="MU",
        source="finnhub",
        published_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        headline="Micron beats",
        url="http://example.com/a",
        sentiment=0.5,
        raw={"id": 1},
    )
    row = item.to_row()
    assert row["ticker"] == "MU"
    assert row["source"] == "finnhub"
    assert row["headline"] == "Micron beats"
    assert row["sentiment"] == 0.5
    assert row["url"] == "http://example.com/a"
    assert "published_at" in row
    assert row["raw"] == {"id": 1}


def test_price_bar_to_row():
    bar = models.PriceBar(
        ticker="MU", d=date(2026, 6, 1),
        open=100.0, high=105.0, low=99.0, close=104.0, volume=1000,
    )
    row = bar.to_row()
    assert row["ticker"] == "MU"
    assert row["date"] == "2026-06-01"
    assert row["close"] == 104.0
    assert row["volume"] == 1000


def test_filing_to_row():
    f = models.Filing(
        ticker="MU", form_type="8-K",
        filed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        url="http://sec.gov/x", raw={"accn": "1"},
    )
    row = f.to_row()
    assert row["ticker"] == "MU"
    assert row["form_type"] == "8-K"
    assert row["url"] == "http://sec.gov/x"


def test_earnings_date_to_row():
    e = models.EarningsDate(
        ticker="MU", report_date=date(2026, 6, 24), confirmed=True,
    )
    row = e.to_row()
    assert row["ticker"] == "MU"
    assert row["report_date"] == "2026-06-24"
    assert row["confirmed"] is True


def test_estimate_to_row():
    est = models.Estimate(
        ticker="MU", period="2026Q3", eps_est=1.5, rev_est=8.0e9,
        eps_actual=None, surprise_pct=None, as_of=date(2026, 6, 1),
    )
    row = est.to_row()
    assert row["ticker"] == "MU"
    assert row["period"] == "2026Q3"
    assert row["eps_est"] == 1.5
    assert row["as_of"] == "2026-06-01"
