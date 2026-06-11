import responses

from vanta.adapters import finnhub


@responses.activate
def test_fetch_returns_news_and_earnings(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://finnhub.io/api/v1/company-news",
        json=[{
            "datetime": 1748779200,  # 2025-06-01 UTC
            "headline": "Micron news",
            "url": "http://finnhub/news/1",
            "summary": "x",
        }],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://finnhub.io/api/v1/calendar/earnings",
        json={"earningsCalendar": [
            {"symbol": "MU", "date": "2026-06-24",
             "epsEstimate": 1.5, "revenueEstimate": 8000000000,
             "epsActual": None, "quarter": 3, "year": 2026},
        ]},
        status=200,
    )

    result = finnhub.fetch("MU", days=30)

    assert len(result.news) == 1
    assert result.news[0].ticker == "MU"
    assert result.news[0].source == "finnhub"
    assert result.news[0].url == "http://finnhub/news/1"

    assert len(result.earnings_dates) == 1
    assert result.earnings_dates[0].report_date.isoformat() == "2026-06-24"

    assert len(result.estimates) == 1
    assert result.estimates[0].eps_est == 1.5
    assert result.estimates[0].period == "2026Q3"


@responses.activate
def test_fetch_handles_empty_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    responses.add(responses.GET,
                  "https://finnhub.io/api/v1/company-news",
                  json=[], status=200)
    responses.add(responses.GET,
                  "https://finnhub.io/api/v1/calendar/earnings",
                  json={"earningsCalendar": []}, status=200)
    result = finnhub.fetch("MU", days=30)
    assert result.news == []
    assert result.earnings_dates == []
    assert result.estimates == []
