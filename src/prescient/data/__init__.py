"""Read-only market data adapters and normalized data models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol, Sequence

from prescient.data.alpha_vantage import AlphaVantageNewsSentimentAdapter
from prescient.data.finnhub import (
    FinnhubEarningsAdapter,
    to_completed_peer_events,
    to_upcoming_calendar_events,
)
from prescient.data.fmp import FmpMarketDataAdapter, FmpStockPeersAdapter, FmpTranscriptAdapter
from prescient.data.sec_edgar import SecEdgarFundamentalsAdapter
from prescient.data.financial_datasets import FinancialDatasetsFundamentalsAdapter
from prescient.data.daloopa import DaloopaFundamentalsAdapter
from prescient.data.gpt_summarizer import GptTranscriptSummarizer, MockTranscriptSummarizer

from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    CompanyEarningsResult,
    CompanyEarningsSnapshot,
    EarningsCalendarResult,
    EarningsCalendarSnapshot,
    EarningsEstimateResult,
    EarningsEstimateSnapshot,
    RevenueEstimateResult,
    RevenueEstimateSnapshot,
    NewsArticle,
    NewsSentimentResult,
    NewsSentimentSnapshot,
    NewsTickerSentiment,
    NewsTopicSentiment,
    PeerListResult,
    PeerListSnapshot,
    HistoricalPriceCandle,
    HistoricalPriceResult,
    XBRLMetric,
    CompanyFactsResult,
    SecFiling,
    FilingHistoryResult,
    CompanyConceptResult,
    FinancialDatasetsMetric,
    FinancialsResult,
    KpiMetric,
    KpiMetricsResult,
    FilingItem,
    FilingItemsResult,
    TranscriptSnapshot,
    TranscriptResult,
    DriverAlignment,
    TranscriptSummary,
)

class PeerListProvider(Protocol):
    def get_peers(
        self, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> PeerListResult:
        ...

    def get_peers_bulk(
        self, 
        tickers: Sequence[str], 
        fetched_at: datetime | None = None
    ) -> PeerListResult:
        ...


class EarningsProvider(Protocol):
    def get_earnings_calendar(
        self,
        date_from: date,
        date_to: date,
        tickers: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> EarningsCalendarResult:
        ...

    def get_company_earnings(
        self,
        ticker: str,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> CompanyEarningsResult:
        ...

    def get_eps_estimates(
        self,
        ticker: str,
        freq: str = "quarterly",
        fetched_at: datetime | None = None,
    ) -> EarningsEstimateResult:
        ...

    def get_revenue_estimates(
        self,
        ticker: str,
        freq: str = "quarterly",
        fetched_at: datetime | None = None,
    ) -> RevenueEstimateResult:
        ...


class NewsSentimentProvider(Protocol):
    def get_news_sentiment(
        self,
        tickers: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        sort: str | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> NewsSentimentResult:
        ...


class MarketDataProvider(Protocol):
    def get_historical_prices(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
        fetched_at: datetime | None = None,
    ) -> HistoricalPriceResult:
        ...


class FundamentalsProvider(Protocol):
    def get_company_facts(
        self, 
        cik: str | int, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> CompanyFactsResult:
        ...

    def get_filing_history(
        self, 
        cik: str | int, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> FilingHistoryResult:
        ...

    def get_company_concept(
        self,
        cik: str | int,
        taxonomy: str,
        concept: str,
        ticker: str,
        fetched_at: datetime | None = None,
    ) -> CompanyConceptResult:
        ...

    def get_financials(
        self,
        ticker: str,
        period: str = "annual",
        limit: int = 1,
        report_period_lte: str | None = None,
        fetched_at: datetime | None = None,
    ) -> FinancialsResult:
        ...

    def get_kpi_metrics(
        self,
        ticker: str,
        metric_name: str | None = None,
        period: str = "quarterly",
        limit: int = 4,
        fetched_at: datetime | None = None,
    ) -> KpiMetricsResult:
        ...

    def get_filing_items(
        self,
        ticker: str,
        filing_type: str = "10-K",
        year: int | None = None,
        items: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> FilingItemsResult:
        ...


class TranscriptProvider(Protocol):
    def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
        fetched_at: datetime | None = None,
    ) -> TranscriptResult:
        ...


class TranscriptSummarizer(Protocol):
    def summarize_transcript(
        self,
        transcript: TranscriptResult,
        theme_drivers: Sequence[str],
    ) -> TranscriptSummary:
        ...


PEER_PROVIDERS: dict[str, Any] = {
    "fmp": FmpStockPeersAdapter,
}

EARNINGS_PROVIDERS: dict[str, Any] = {
    "finnhub": FinnhubEarningsAdapter,
}

NEWS_PROVIDERS: dict[str, Any] = {
    "alpha_vantage": AlphaVantageNewsSentimentAdapter,
}

MARKET_DATA_PROVIDERS: dict[str, Any] = {
    "fmp": FmpMarketDataAdapter,
}

FUNDAMENTALS_PROVIDERS: dict[str, Any] = {
    "sec_edgar": SecEdgarFundamentalsAdapter,
    "financial_datasets": FinancialDatasetsFundamentalsAdapter,
    "daloopa": DaloopaFundamentalsAdapter,
}

TRANSCRIPT_PROVIDERS: dict[str, Any] = {
    "fmp": FmpTranscriptAdapter,
}

SUMMARIZER_PROVIDERS: dict[str, Any] = {
    "openai": GptTranscriptSummarizer,
    "mock": MockTranscriptSummarizer,
}


def get_peer_provider(name: str, **kwargs: Any) -> PeerListProvider:
    if name not in PEER_PROVIDERS:
        raise ValueError(f"Unknown peer provider: {name}. Supported: {list(PEER_PROVIDERS.keys())}")
    return PEER_PROVIDERS[name](**kwargs)


def get_earnings_provider(name: str, **kwargs: Any) -> EarningsProvider:
    if name not in EARNINGS_PROVIDERS:
        raise ValueError(
            f"Unknown earnings provider: {name}. Supported: {list(EARNINGS_PROVIDERS.keys())}"
        )
    return EARNINGS_PROVIDERS[name](**kwargs)


def get_news_provider(name: str, **kwargs: Any) -> NewsSentimentProvider:
    if name not in NEWS_PROVIDERS:
        raise ValueError(f"Unknown news provider: {name}. Supported: {list(NEWS_PROVIDERS.keys())}")
    return NEWS_PROVIDERS[name](**kwargs)


def get_market_data_provider(name: str, **kwargs: Any) -> MarketDataProvider:
    if name not in MARKET_DATA_PROVIDERS:
        raise ValueError(
            f"Unknown market data provider: {name}. "
            f"Supported: {list(MARKET_DATA_PROVIDERS.keys())}"
        )
    return MARKET_DATA_PROVIDERS[name](**kwargs)


def get_fundamentals_provider(name: str, **kwargs: Any) -> FundamentalsProvider:
    if name not in FUNDAMENTALS_PROVIDERS:
        raise ValueError(f"Unknown fundamentals provider: {name}. Supported: {list(FUNDAMENTALS_PROVIDERS.keys())}")
    return FUNDAMENTALS_PROVIDERS[name](**kwargs)


def get_transcript_provider(name: str, **kwargs: Any) -> TranscriptProvider:
    if name not in TRANSCRIPT_PROVIDERS:
        raise ValueError(f"Unknown transcript provider: {name}. Supported: {list(TRANSCRIPT_PROVIDERS.keys())}")
    return TRANSCRIPT_PROVIDERS[name](**kwargs)


def get_summarizer_provider(name: str, **kwargs: Any) -> TranscriptSummarizer:
    if name not in SUMMARIZER_PROVIDERS:
        raise ValueError(f"Unknown summarizer provider: {name}. Supported: {list(SUMMARIZER_PROVIDERS.keys())}")
    return SUMMARIZER_PROVIDERS[name](**kwargs)


def __getattr__(name: str) -> Any:
    if name in {"filter_peers_to_theme", "filter_peers_to_universe"}:
        from prescient.data.peers import filter_peers_to_theme, filter_peers_to_universe

        return {
            "filter_peers_to_theme": filter_peers_to_theme,
            "filter_peers_to_universe": filter_peers_to_universe,
        }[name]
    raise AttributeError(f"module 'prescient.data' has no attribute {name!r}")


__all__ = [
    "AlphaVantageNewsSentimentAdapter",
    "DataProvider",
    "DataProviderError",
    "DataProviderErrorType",
    "CompanyEarningsResult",
    "CompanyEarningsSnapshot",
    "EarningsCalendarResult",
    "EarningsCalendarSnapshot",
    "EarningsEstimateResult",
    "EarningsEstimateSnapshot",
    "RevenueEstimateResult",
    "RevenueEstimateSnapshot",
    "FinnhubEarningsAdapter",
    "FmpMarketDataAdapter",
    "FmpStockPeersAdapter",
    "FmpTranscriptAdapter",
    "GptTranscriptSummarizer",
    "MockTranscriptSummarizer",
    "SecEdgarFundamentalsAdapter",
    "FinancialDatasetsFundamentalsAdapter",
    "DaloopaFundamentalsAdapter",
    "NewsArticle",
    "NewsSentimentResult",
    "NewsSentimentSnapshot",
    "NewsTickerSentiment",
    "NewsTopicSentiment",
    "PeerListResult",
    "PeerListSnapshot",
    "HistoricalPriceCandle",
    "HistoricalPriceResult",
    "XBRLMetric",
    "CompanyFactsResult",
    "SecFiling",
    "FilingHistoryResult",
    "CompanyConceptResult",
    "FinancialDatasetsMetric",
    "FinancialsResult",
    "KpiMetric",
    "KpiMetricsResult",
    "FilingItem",
    "FilingItemsResult",
    "TranscriptSnapshot",
    "TranscriptResult",
    "DriverAlignment",
    "TranscriptSummary",
    "filter_peers_to_theme",
    "filter_peers_to_universe",
    "to_completed_peer_events",
    "to_upcoming_calendar_events",
    "EarningsProvider",
    "PeerListProvider",
    "NewsSentimentProvider",
    "MarketDataProvider",
    "FundamentalsProvider",
    "TranscriptProvider",
    "TranscriptSummarizer",
    "EARNINGS_PROVIDERS",
    "PEER_PROVIDERS",
    "NEWS_PROVIDERS",
    "MARKET_DATA_PROVIDERS",
    "FUNDAMENTALS_PROVIDERS",
    "TRANSCRIPT_PROVIDERS",
    "SUMMARIZER_PROVIDERS",
    "get_earnings_provider",
    "get_peer_provider",
    "get_news_provider",
    "get_market_data_provider",
    "get_fundamentals_provider",
    "get_transcript_provider",
    "get_summarizer_provider",
]
