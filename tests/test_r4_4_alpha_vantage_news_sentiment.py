from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prescient.data import (
    AlphaVantageNewsSentimentAdapter,
    DataProvider,
    DataProviderErrorType,
)


R4_4_PRD_PATH = Path("docs/prd/04-data-r4-4-alpha-vantage-news-sentiment-prd.md")


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_r4_4_prd_is_saved_and_keeps_alpha_vantage_news_as_read_only_enrichment() -> None:
    prd = R4_4_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R4.4 Alpha Vantage News & Sentiment" in prd
    assert "Alpha Vantage" in prd
    assert "function=NEWS_SENTIMENT" in prd
    assert "read-only enrichment" in prd
    assert "must not place trades" in prd
    assert "No automatic strategy decisions" in prd


def test_news_sentiment_response_normalizes_snapshot_and_provider_articles() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "items": "1",
                "sentiment_score_definition": "Score definition",
                "relevance_score_definition": "Relevance definition",
                "feed": [
                    {
                        "title": "Apple AI demand read-through",
                        "url": "https://example.com/aapl-ai",
                        "time_published": "20260603T173000",
                        "authors": ["Jane Doe", " ", None],
                        "summary": "Apple suppliers rallied after an AI demand report.",
                        "banner_image": "https://example.com/aapl-ai.jpg",
                        "source": "Example Markets",
                        "category_within_source": "Technology",
                        "source_domain": "example.com",
                        "topics": [
                            {"topic": "technology", "relevance_score": "0.913"},
                            {"topic": "earnings", "relevance_score": "not-a-number"},
                        ],
                        "overall_sentiment_score": "0.31",
                        "overall_sentiment_label": "Somewhat-Bullish",
                        "ticker_sentiment": [
                            {
                                "ticker": "aapl",
                                "relevance_score": "0.887",
                                "ticker_sentiment_score": "0.24",
                                "ticker_sentiment_label": "Bullish",
                            },
                            {
                                "ticker": " ",
                                "relevance_score": "0.1",
                                "ticker_sentiment_score": "0.1",
                                "ticker_sentiment_label": "Neutral",
                            },
                            {
                                "ticker": "msft",
                                "relevance_score": "0.045",
                                "ticker_sentiment_score": "bad-score",
                                "ticker_sentiment_label": "Neutral",
                            },
                        ],
                    }
                ],
            }
        )
    )
    fetched_at = datetime(2026, 6, 3, 17, 45, tzinfo=timezone.utc)
    adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=client,
    )

    result = adapter.get_news_sentiment(
        tickers=["aapl", "MSFT"],
        topics=["technology", "earnings"],
        time_from="20260603T0000",
        time_to="20260603T2359",
        sort="relevance",
        limit=25,
        fetched_at=fetched_at,
    )

    assert result.errors == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.provider == DataProvider.ALPHA_VANTAGE
    assert snapshot.source_endpoint == "/query?function=NEWS_SENTIMENT"
    assert snapshot.query_tickers == ["AAPL", "MSFT"]
    assert snapshot.topics == ["technology", "earnings"]
    assert snapshot.fetched_at == fetched_at
    assert snapshot.provider_notes == [
        "sentiment_score_definition: Score definition",
        "relevance_score_definition: Relevance definition",
    ]
    assert len(snapshot.articles) == 1

    article = snapshot.articles[0]
    assert article.title == "Apple AI demand read-through"
    assert article.url == "https://example.com/aapl-ai"
    assert article.time_published == datetime(2026, 6, 3, 17, 30, tzinfo=timezone.utc)
    assert article.authors == ["Jane Doe"]
    assert article.summary == "Apple suppliers rallied after an AI demand report."
    assert article.source == "Example Markets"
    assert article.source_domain == "example.com"
    assert article.overall_sentiment_score == 0.31
    assert article.overall_sentiment_label == "Somewhat-Bullish"
    assert [(topic.topic, topic.relevance_score) for topic in article.topics] == [
        ("technology", 0.913),
        ("earnings", None),
    ]
    assert [
        (
            sentiment.ticker,
            sentiment.relevance_score,
            sentiment.sentiment_score,
            sentiment.sentiment_label,
        )
        for sentiment in article.ticker_sentiment
    ] == [
        ("AAPL", 0.887, 0.24, "Bullish"),
        ("MSFT", 0.045, None, "Neutral"),
    ]
    assert client.calls == [
        {
            "url": "https://www.alphavantage.co/query",
            "params": {
                "function": "NEWS_SENTIMENT",
                "tickers": "AAPL,MSFT",
                "topics": "technology,earnings",
                "time_from": "20260603T0000",
                "time_to": "20260603T2359",
                "sort": "RELEVANCE",
                "limit": 25,
                "apikey": "secret-key",
            },
            "timeout": 10.0,
        }
    ]


def test_topic_only_news_sentiment_request_omits_tickers_parameter() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "feed": [
                    {
                        "title": "AI infrastructure update",
                        "url": "https://example.com/ai",
                        "time_published": "20260603T120000",
                    }
                ]
            }
        )
    )
    adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=client,
    )

    result = adapter.get_news_sentiment(topics=["technology"])

    assert result.errors == []
    assert result.snapshots[0].query_tickers == []
    assert result.snapshots[0].topics == ["technology"]
    assert "tickers" not in client.calls[0]["params"]
    assert client.calls[0]["params"]["topics"] == "technology"


def test_missing_api_key_returns_news_error_without_http_call() -> None:
    client = FakeHttpClient(FakeHttpResponse(payload={"feed": []}))
    adapter = AlphaVantageNewsSentimentAdapter(api_key="", http_client=client)

    result = adapter.get_news_sentiment(tickers=["AAPL"])

    assert result.snapshots == []
    assert len(result.errors) == 1
    assert result.errors[0].provider == DataProvider.ALPHA_VANTAGE
    assert result.errors[0].error_type == DataProviderErrorType.MISSING_API_KEY
    assert result.errors[0].symbol == "AAPL"
    assert client.calls == []


def test_provider_http_errors_map_to_alpha_vantage_structured_error_types() -> None:
    cases = [
        (401, DataProviderErrorType.UNAUTHORIZED),
        (403, DataProviderErrorType.UNAUTHORIZED),
        (429, DataProviderErrorType.RATE_LIMITED),
        (500, DataProviderErrorType.PROVIDER_UNAVAILABLE),
        (503, DataProviderErrorType.PROVIDER_UNAVAILABLE),
    ]

    for status_code, expected_error in cases:
        adapter = AlphaVantageNewsSentimentAdapter(
            api_key="secret-key",
            http_client=FakeHttpClient(FakeHttpResponse(status_code=status_code, payload={})),
        )

        result = adapter.get_news_sentiment(tickers=["AAPL"])

        assert result.snapshots == []
        assert [error.error_type for error in result.errors] == [expected_error]
        assert result.errors[0].status_code == status_code


def test_alpha_vantage_message_errors_are_structured_without_raw_payload_leakage() -> None:
    cases = [
        ({"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is ..."}, DataProviderErrorType.RATE_LIMITED),
        ({"Information": "This endpoint is only available for premium subscribers."}, DataProviderErrorType.UNAUTHORIZED),
        ({"Error Message": "Invalid API call. Please retry."}, DataProviderErrorType.MALFORMED_RESPONSE),
    ]

    for payload, expected_error in cases:
        adapter = AlphaVantageNewsSentimentAdapter(
            api_key="secret-key",
            http_client=FakeHttpClient(FakeHttpResponse(payload=payload)),
        )

        result = adapter.get_news_sentiment(tickers=["AAPL"])
        serialized = result.errors[0].model_dump(mode="json")
        rendered = repr(serialized).lower()

        assert result.snapshots == []
        assert result.errors[0].error_type == expected_error
        assert "secret-key" not in rendered
        assert "standard api call frequency" not in rendered
        assert "premium subscribers" not in rendered
        assert "invalid api call" not in rendered
        assert "raw_payload" not in rendered


def test_timeout_malformed_and_empty_news_responses_are_structured() -> None:
    timeout_adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(TimeoutError("request timed out")),
    )
    malformed_json_adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(payload=None, json_error=ValueError("bad json"))
        ),
    )
    malformed_feed_adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload={"feed": {}})),
    )
    empty_adapter = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload={"feed": []})),
    )

    assert timeout_adapter.get_news_sentiment(tickers=["AAPL"]).errors[0].error_type == (
        DataProviderErrorType.TIMEOUT
    )
    assert malformed_json_adapter.get_news_sentiment(tickers=["AAPL"]).errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert malformed_feed_adapter.get_news_sentiment(tickers=["AAPL"]).errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert empty_adapter.get_news_sentiment(tickers=["AAPL"]).errors[0].error_type == (
        DataProviderErrorType.EMPTY_RESPONSE
    )


def test_same_alpha_vantage_fake_response_serializes_deterministically() -> None:
    response = FakeHttpResponse(
        payload={
            "feed": [
                {
                    "title": "Apple update",
                    "url": "https://example.com/aapl",
                    "time_published": "20260603T120000",
                    "ticker_sentiment": [
                        {
                            "ticker": "aapl",
                            "ticker_sentiment_score": "0.1",
                            "ticker_sentiment_label": "Neutral",
                        }
                    ],
                }
            ]
        }
    )
    first = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(response),
    ).get_news_sentiment(tickers=["AAPL"])
    second = AlphaVantageNewsSentimentAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(response),
    ).get_news_sentiment(tickers=["AAPL"])

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
