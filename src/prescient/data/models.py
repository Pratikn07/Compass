from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prescient.journal import SourceCitation


class DataProvider(StrEnum):
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    FMP = "fmp"
    SEC_EDGAR = "sec_edgar"
    FINANCIAL_DATASETS = "financial_datasets"
    DALOOPA = "daloopa"


class DataProviderErrorType(StrEnum):
    MISSING_API_KEY = "missing_api_key"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PAYMENT_REQUIRED = "payment_required"
    FILING_PARSE_IN_PROGRESS = "filing_parse_in_progress"
    MISSING_USER_AGENT = "missing_user_agent"
    TRANSCRIPT_NOT_FOUND = "transcript_not_found"
    INVALID_SCHEMA_RESPONSE = "invalid_schema_response"


class DataProviderError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: DataProvider
    error_type: DataProviderErrorType
    message: str
    endpoint: str | None = None
    status_code: int | None = None
    symbol: str | None = None
    retry_after_seconds: int | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class PeerListSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    peers: list[str]
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("peers")
    @classmethod
    def normalize_peers(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            peer = str(value).strip().upper()
            if peer and peer not in normalized:
                normalized.append(peer)
        return normalized


class PeerListResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[PeerListSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class HistoricalPriceCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    trading_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: int | None = None
    vwap: float | None = None
    change: float | None = None
    change_percent: float | None = None
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class HistoricalPriceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candles: list[HistoricalPriceCandle] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class EarningsCalendarSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    earnings_date: date | None
    report_time: str = "UNKNOWN"
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("report_time")
    @classmethod
    def normalize_report_time(cls, value: str) -> str:
        normalized = value.strip().upper()
        return normalized if normalized in {"BMO", "AMC", "UNKNOWN"} else "UNKNOWN"


class EarningsCalendarResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[EarningsCalendarSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class CompanyEarningsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    fiscal_period: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_surprise: float | None = None
    eps_surprise_percent: float | None = None
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class CompanyEarningsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[CompanyEarningsSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class EarningsEstimateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    fiscal_period: str | None = None
    freq: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    eps_average: float | None = None
    eps_high: float | None = None
    eps_low: float | None = None
    analyst_count: int | None = None
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("freq")
    @classmethod
    def normalize_freq(cls, value: str) -> str:
        return value.strip().lower()


class EarningsEstimateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[EarningsEstimateSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class RevenueEstimateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    fiscal_period: str | None = None
    freq: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    revenue_average: float | None = None
    revenue_high: float | None = None
    revenue_low: float | None = None
    analyst_count: int | None = None
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("freq")
    @classmethod
    def normalize_freq(cls, value: str) -> str:
        return value.strip().lower()


class RevenueEstimateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[RevenueEstimateSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class NewsTopicSentiment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str
    relevance_score: float | None = None

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        return value.strip()


class NewsTickerSentiment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    relevance_score: float | None = None
    sentiment_score: float | None = None
    sentiment_label: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sentiment_label")
    @classmethod
    def normalize_sentiment_label(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class NewsArticle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    url: str
    time_published: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    summary: str | None = None
    banner_image: str | None = None
    source: str | None = None
    category_within_source: str | None = None
    source_domain: str | None = None
    overall_sentiment_score: float | None = None
    overall_sentiment_label: str | None = None
    topics: list[NewsTopicSentiment] = Field(default_factory=list)
    ticker_sentiment: list[NewsTickerSentiment] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator(
        "title",
        "url",
        "summary",
        "banner_image",
        "source",
        "category_within_source",
        "source_domain",
        "overall_sentiment_label",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("authors")
    @classmethod
    def normalize_authors(cls, values: list[str]) -> list[str]:
        authors: list[str] = []
        for value in values:
            author = value.strip()
            if author and author not in authors:
                authors.append(author)
        return authors


class NewsSentimentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_tickers: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    articles: list[NewsArticle] = Field(default_factory=list)
    provider: DataProvider
    source_endpoint: str
    provider_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("query_tickers")
    @classmethod
    def normalize_query_tickers(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            ticker = value.strip().upper()
            if ticker and ticker not in normalized:
                normalized.append(ticker)
        return normalized

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            topic = value.strip().lower()
            if topic and topic not in normalized:
                normalized.append(topic)
        return normalized


class NewsSentimentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[NewsSentimentSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class XBRLMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: DataProvider
    source_endpoint: str
    ticker: str
    cik: str
    metric_name: str
    taxonomy: str
    concept: str
    value: float
    unit: str
    period: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    filing_form: str | None = None
    accession_number: str | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        return str(value).strip().zfill(10)


class CompanyFactsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[XBRLMetric] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class SecFiling(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    form_type: str
    accession_number: str
    ticker: str
    cik: str
    filing_date: str
    report_period: str
    provider: DataProvider
    source_url: str
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        return str(value).strip().zfill(10)


class FilingHistoryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filings: list[SecFiling] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class CompanyConceptResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[XBRLMetric] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class FinancialDatasetsMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    statement_type: str
    metric_name: str
    value: float
    provider: DataProvider
    source_endpoint: str
    ticker: str
    unit: str
    period: str
    fiscal_period: str
    accession_number: str | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class FinancialsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[FinancialDatasetsMetric] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class KpiMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: DataProvider
    source_endpoint: str
    ticker: str
    metric_name: str
    value: float
    unit: str
    period: str
    period_type: str
    segment: str | None = None
    yoy_value: float | None = None
    yoy_change_pct: float | None = None
    source_text: str | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class KpiMetricsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[KpiMetric] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class FilingItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    cik: str
    filing_type: str
    accession_number: str
    item_number: str
    item_name: str
    text: str
    provider: DataProvider
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        return str(value).strip().zfill(10)


class FilingItemsResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[FilingItem] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class TranscriptSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    quarter: int
    year: int
    content: str
    provider: DataProvider
    source_endpoint: str
    fetched_at: datetime | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("quarter")
    @classmethod
    def validate_quarter(cls, value: int) -> int:
        if not (1 <= value <= 4):
            raise ValueError("Quarter must be between 1 and 4.")
        return value


class TranscriptResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshots: list[TranscriptSnapshot] = Field(default_factory=list)
    errors: list[DataProviderError] = Field(default_factory=list)


class DriverAlignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver: str
    status: str  # "confirmed" | "contradicted" | "unmentioned"
    summary: str
    supporting_quotes: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"confirmed", "contradicted", "unmentioned"}:
            raise ValueError("Status must be confirmed, contradicted, or unmentioned.")
        return val


class TranscriptSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    quarter: int
    year: int
    guidance_sentiment: str  # "BULLISH" | "NEUTRAL" | "BEARISH" | "UNKNOWN"
    driver_alignments: list[DriverAlignment] = Field(default_factory=list)
    management_tone: str
    key_takeaways: list[str] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("guidance_sentiment")
    @classmethod
    def normalize_sentiment(cls, value: str) -> str:
        val = value.strip().upper()
        if val not in {"BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN"}:
            raise ValueError("Guidance sentiment must be BULLISH, NEUTRAL, BEARISH, or UNKNOWN.")
        return val
