from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    NewsArticle,
    NewsSentimentResult,
    NewsSentimentSnapshot,
    NewsTickerSentiment,
    NewsTopicSentiment,
)


_QUERY_PATH = "/query"
_NEWS_SENTIMENT_FUNCTION = "NEWS_SENTIMENT"
_NEWS_SENTIMENT_ENDPOINT = f"{_QUERY_PATH}?function={_NEWS_SENTIMENT_FUNCTION}"


class SyncHttpResponse(Protocol):
    status_code: int

    def json(self) -> Any:
        ...


class SyncHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> SyncHttpResponse:
        ...


class _DefaultHttpClient:
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> SyncHttpResponse:
        return httpx.get(url, params=params, timeout=timeout)


class AlphaVantageNewsSentimentAdapter:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://www.alphavantage.co",
        timeout_seconds: float = 10.0,
        http_client: SyncHttpClient | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client or _DefaultHttpClient()

    def get_news_sentiment(
        self,
        *,
        tickers: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> NewsSentimentResult:
        query_tickers = _normalize_tickers(tickers or [])
        query_topics = _normalize_topics(topics or [])
        error_symbol = _error_symbol(query_tickers)

        if not self._api_key:
            return _error_result(
                DataProviderErrorType.MISSING_API_KEY,
                symbol=error_symbol,
                message="Alpha Vantage API key is required for news sentiment.",
            )

        params: dict[str, Any] = {"function": _NEWS_SENTIMENT_FUNCTION}
        if query_tickers:
            params["tickers"] = ",".join(query_tickers)
        if query_topics:
            params["topics"] = ",".join(query_topics)
        if time_from is not None:
            params["time_from"] = time_from
        if time_to is not None:
            params["time_to"] = time_to
        if sort is not None:
            params["sort"] = sort.strip().upper()
        if limit is not None:
            params["limit"] = limit
        params["apikey"] = self._api_key

        response = self._get(symbol=error_symbol, params=params)
        if isinstance(response, NewsSentimentResult):
            return response

        return _parse_news_response(
            response,
            query_tickers=query_tickers,
            topics=query_topics,
            fetched_at=fetched_at,
            error_symbol=error_symbol,
        )

    def _get(
        self,
        *,
        symbol: str | None,
        params: dict[str, Any],
    ) -> SyncHttpResponse | NewsSentimentResult:
        try:
            response = self._http_client.get(
                f"{self._base_url}{_QUERY_PATH}",
                params=params,
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException):
            return _error_result(
                DataProviderErrorType.TIMEOUT,
                symbol=symbol,
                message="Alpha Vantage news sentiment request timed out.",
            )
        except httpx.HTTPError:
            return _error_result(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                symbol=symbol,
                message="Alpha Vantage news sentiment provider is unavailable.",
            )

        status_error = _status_error(response.status_code)
        if status_error is not None:
            return _error_result(
                status_error,
                symbol=symbol,
                status_code=response.status_code,
                message=_message_for_status_error(status_error),
            )

        return response


def _parse_news_response(
    response: SyncHttpResponse,
    *,
    query_tickers: list[str],
    topics: list[str],
    fetched_at: datetime | None,
    error_symbol: str | None,
) -> NewsSentimentResult:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return _error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            symbol=error_symbol,
            message="Alpha Vantage news sentiment response was not valid JSON.",
        )

    if not isinstance(payload, Mapping):
        return _error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            symbol=error_symbol,
            message="Alpha Vantage news sentiment response had an unsupported shape.",
        )

    provider_message_error = _provider_message_error(payload)
    if provider_message_error is not None:
        return _error_result(
            provider_message_error,
            symbol=error_symbol,
            message=_message_for_provider_payload_error(provider_message_error),
        )

    raw_feed = payload.get("feed")
    if not isinstance(raw_feed, list):
        return _error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            symbol=error_symbol,
            message="Alpha Vantage news sentiment response did not include a feed list.",
        )
    if not raw_feed:
        return _error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            symbol=error_symbol,
            message="Alpha Vantage news sentiment response was empty.",
        )

    articles: list[NewsArticle] = []
    for entry in raw_feed:
        if not isinstance(entry, Mapping):
            return _error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                symbol=error_symbol,
                message="Alpha Vantage news sentiment feed had an unsupported shape.",
            )
        article = _article_from_entry(entry)
        if article is None:
            return _error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                symbol=error_symbol,
                message="Alpha Vantage news sentiment article had an unsupported shape.",
            )
        articles.append(article)

    return NewsSentimentResult(
        snapshots=[
            NewsSentimentSnapshot(
                query_tickers=query_tickers,
                topics=topics,
                articles=articles,
                provider=DataProvider.ALPHA_VANTAGE,
                source_endpoint=_NEWS_SENTIMENT_ENDPOINT,
                provider_notes=_provider_notes(payload),
                fetched_at=fetched_at,
            )
        ],
        errors=[],
    )


def _article_from_entry(entry: Mapping[str, Any]) -> NewsArticle | None:
    title = _string_or_none(entry.get("title"))
    url = _string_or_none(entry.get("url"))
    if title is None or url is None:
        return None

    return NewsArticle(
        title=title,
        url=url,
        time_published=_parse_alpha_vantage_time(entry.get("time_published")),
        authors=_authors(entry.get("authors")),
        summary=_string_or_none(entry.get("summary")),
        banner_image=_string_or_none(entry.get("banner_image")),
        source=_string_or_none(entry.get("source")),
        category_within_source=_string_or_none(entry.get("category_within_source")),
        source_domain=_string_or_none(entry.get("source_domain")),
        overall_sentiment_score=_float_or_none(entry.get("overall_sentiment_score")),
        overall_sentiment_label=_string_or_none(entry.get("overall_sentiment_label")),
        topics=_topic_sentiments(entry.get("topics")),
        ticker_sentiment=_ticker_sentiments(entry.get("ticker_sentiment")),
    )


def _authors(raw_authors: Any) -> list[str]:
    if isinstance(raw_authors, str):
        values: Sequence[Any] = [raw_authors]
    elif isinstance(raw_authors, list):
        values = raw_authors
    else:
        return []

    authors: list[str] = []
    for value in values:
        author = _string_or_none(value)
        if author is not None and author not in authors:
            authors.append(author)
    return authors


def _topic_sentiments(raw_topics: Any) -> list[NewsTopicSentiment]:
    if not isinstance(raw_topics, list):
        return []

    topics: list[NewsTopicSentiment] = []
    for entry in raw_topics:
        if not isinstance(entry, Mapping):
            continue
        topic = _string_or_none(entry.get("topic"))
        if topic is None:
            continue
        topics.append(
            NewsTopicSentiment(
                topic=topic,
                relevance_score=_float_or_none(entry.get("relevance_score")),
            )
        )
    return topics


def _ticker_sentiments(raw_sentiments: Any) -> list[NewsTickerSentiment]:
    if not isinstance(raw_sentiments, list):
        return []

    sentiments: list[NewsTickerSentiment] = []
    for entry in raw_sentiments:
        if not isinstance(entry, Mapping):
            continue
        ticker = _string_or_none(entry.get("ticker"))
        if ticker is None:
            continue
        sentiments.append(
            NewsTickerSentiment(
                ticker=ticker,
                relevance_score=_float_or_none(entry.get("relevance_score")),
                sentiment_score=_float_or_none(entry.get("ticker_sentiment_score")),
                sentiment_label=_string_or_none(entry.get("ticker_sentiment_label")),
            )
        )
    return sentiments


def _provider_notes(payload: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    for key in ["sentiment_score_definition", "relevance_score_definition"]:
        value = _string_or_none(payload.get(key))
        if value is not None:
            notes.append(f"{key}: {value}")
    return notes


def _provider_message_error(payload: Mapping[str, Any]) -> DataProviderErrorType | None:
    if isinstance(payload.get("Note"), str):
        return DataProviderErrorType.RATE_LIMITED

    information = _string_or_none(payload.get("Information"))
    if information is not None:
        lowered = information.lower()
        if any(term in lowered for term in ["premium", "entitlement", "unauthorized"]):
            return DataProviderErrorType.UNAUTHORIZED
        if any(term in lowered for term in ["frequency", "rate", "limit"]):
            return DataProviderErrorType.RATE_LIMITED
        return DataProviderErrorType.PROVIDER_UNAVAILABLE

    if isinstance(payload.get("Error Message"), str):
        return DataProviderErrorType.MALFORMED_RESPONSE

    return None


def _message_for_provider_payload_error(error_type: DataProviderErrorType) -> str:
    messages = {
        DataProviderErrorType.UNAUTHORIZED: (
            "Alpha Vantage news sentiment access is unauthorized."
        ),
        DataProviderErrorType.RATE_LIMITED: (
            "Alpha Vantage news sentiment request was rate limited."
        ),
        DataProviderErrorType.MALFORMED_RESPONSE: (
            "Alpha Vantage news sentiment request was rejected."
        ),
        DataProviderErrorType.PROVIDER_UNAVAILABLE: (
            "Alpha Vantage news sentiment provider is unavailable."
        ),
    }
    return messages.get(error_type, "Alpha Vantage news sentiment request failed.")


def _normalize_tickers(values: Sequence[str]) -> list[str]:
    tickers: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        ticker = value.strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _normalize_topics(values: Sequence[str]) -> list[str]:
    topics: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        topic = value.strip().lower()
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _error_symbol(query_tickers: Sequence[str]) -> str | None:
    if not query_tickers:
        return None
    return ",".join(query_tickers)


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_alpha_vantage_time(value: Any) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None

    for date_format in ["%Y%m%dT%H%M%S", "%Y%m%dT%H%M"]:
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _status_error(status_code: int) -> DataProviderErrorType | None:
    if status_code in {401, 403}:
        return DataProviderErrorType.UNAUTHORIZED
    if status_code == 404:
        return DataProviderErrorType.UNSUPPORTED_SYMBOL
    if status_code == 429:
        return DataProviderErrorType.RATE_LIMITED
    if status_code >= 500:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    if status_code >= 400:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    return None


def _message_for_status_error(error_type: DataProviderErrorType) -> str:
    messages = {
        DataProviderErrorType.UNAUTHORIZED: (
            "Alpha Vantage news sentiment access is unauthorized."
        ),
        DataProviderErrorType.RATE_LIMITED: (
            "Alpha Vantage news sentiment request was rate limited."
        ),
        DataProviderErrorType.UNSUPPORTED_SYMBOL: (
            "Alpha Vantage news sentiment symbol is unsupported."
        ),
        DataProviderErrorType.PROVIDER_UNAVAILABLE: (
            "Alpha Vantage news sentiment provider is unavailable."
        ),
    }
    return messages.get(error_type, "Alpha Vantage news sentiment request failed.")


def _error_result(
    error_type: DataProviderErrorType,
    *,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> NewsSentimentResult:
    return NewsSentimentResult(
        snapshots=[],
        errors=[
            DataProviderError(
                provider=DataProvider.ALPHA_VANTAGE,
                error_type=error_type,
                message=message,
                endpoint=_NEWS_SENTIMENT_ENDPOINT,
                status_code=status_code,
                symbol=symbol,
            )
        ],
    )
