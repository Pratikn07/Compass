# PRD: R4.6 Pluggable Data Adapters

## Ownership

Owner: Ours

Source note: Requirement from Ours: all data sources must be pluggable adapters implementing standardized interfaces (Protocols/ABCs). The system must support swapping providers via configuration without modifying core strategy logic, risk rules, or orchestrators.

## Objective

Define the architecture and technical requirements for pluggable, interface-based data adapters under `prescient.data`. Swapping a data provider (e.g., switching from FMP to a mock provider, or from Alpha Vantage news to SEC RSS news) must be configuration-driven and require zero changes to the core deterministic strategy engine, risk gatekeepers, or runtime pipelines.

R4.6 answers:
```text
How can the system define uniform data-fetching interfaces so that the core strategy and pipelines are isolated from external API schemas and concrete classes?
```

## Background

Currently, adapters like `FmpStockPeersAdapter` and `AlphaVantageNewsSentimentAdapter` exist as concrete classes returning normalized data models. However:
1. Callers (e.g., tests, pipelines, and future schedulers) import these concrete adapter classes directly, violating the dependency inversion principle.
2. Upcoming PRD R4.5 introduces tiered fundamentals data providers (SEC EDGAR, Financial Datasets, Daloopa), which will worsen this tight coupling if adapters are imported directly.
3. Decoupling the data adapters via Python `typing.Protocol` (PEP 544) or Abstract Base Classes (ABCs) allows us to inject mock adapters during tests, swap vendors, and prevent implementation details from leaking into the core signal, risk, and runtime layers.

---

## Technical Architecture & Requirements

### R4.6.1 Strict Protocol Definitions

The data layer must expose structural typing interfaces (using `typing.Protocol`) or formal abstract classes for each data domain. These interfaces must live in `prescient.data.interfaces` (or within `prescient.data.models` / `prescient.data.__init__`).

#### 1. Peer List Protocol
Defines the interface for fetching Stock Peers/Competitor lists:
```python
from typing import Protocol, Sequence, Mapping
from datetime import datetime
from prescient.data.models import PeerListResult

class PeerListProvider(Protocol):
    def get_peers(
        self, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> PeerListResult:
        """Fetch stock peers for a single ticker."""
        ...

    def get_peers_bulk(
        self, 
        tickers: Sequence[str], 
        fetched_at: datetime | None = None
    ) -> PeerListResult:
        """Fetch stock peers for multiple tickers in bulk."""
        ...
```

#### 2. News and Sentiment Protocol
Defines the interface for fetching market news and sentiments:
```python
from typing import Protocol, Sequence
from datetime import datetime
from prescient.data.models import NewsSentimentResult

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
        """Fetch news and sentiment snapshots filtering by tickers and topics."""
        ...
```

#### 3. Fundamentals and KPIs Protocol
Defines the interface for fetching SEC facts, financials, metrics, and filing item items (supporting R4.5 tiers):
```python
from typing import Protocol, Sequence, Mapping, Any
from datetime import datetime
from prescient.data.models import (
    CompanyFactsResult,
    FilingHistoryResult,
    CompanyConceptResult,
    FinancialsResult,
    KpiMetricsResult,
    FilingItemsResult,
)

class FundamentalsProvider(Protocol):
    def get_company_facts(
        self, 
        cik: str | int, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> CompanyFactsResult:
        """Fetch raw XBRL company facts from the provider."""
        ...

    def get_filing_history(
        self, 
        cik: str | int, 
        ticker: str, 
        fetched_at: datetime | None = None
    ) -> FilingHistoryResult:
        """Fetch recent filing metadata history."""
        ...

    def get_company_concept(
        self,
        cik: str | int,
        taxonomy: str,
        concept: str,
        ticker: str,
        fetched_at: datetime | None = None,
    ) -> CompanyConceptResult:
        """Fetch facts for a specific XBRL taxonomy concept."""
        ...

    def get_financials(
        self,
        ticker: str,
        period: str = "annual",
        limit: int = 1,
        report_period_lte: str | None = None,
        fetched_at: datetime | None = None,
    ) -> FinancialsResult:
        """Fetch normalized statement metrics (Revenue, Assets, etc.)."""
        ...

    def get_kpi_metrics(
        self,
        ticker: str,
        metric_name: str | None = None,
        period: str = "quarterly",
        limit: int = 4,
        fetched_at: datetime | None = None,
    ) -> KpiMetricsResult:
        """Fetch specialized source-linked operating KPIs."""
        ...

    def get_filing_items(
        self,
        ticker: str,
        filing_type: str = "10-K",
        year: int | None = None,
        items: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> FilingItemsResult:
        """Fetch raw text segments for specific items (e.g., Item-7 MD&A)."""
        ...
```

---

### R4.6.2 Provider Registry & Factory Pattern

The package `prescient.data` must expose a registry and factory to construct these providers dynamically based on settings/configuration.

1. **Provider Registry**: A dictionary/mapping associating provider names (e.g., `"fmp"`, `"alpha_vantage"`, `"sec_edgar"`, `"financial_datasets"`, `"daloopa"`, `"mock"`) to their concrete implementation classes.
2. **Factory Functions**: Expose dynamic resolver functions:
   * `get_peer_provider(provider_name: str, **kwargs: Any) -> PeerListProvider`
   * `get_news_provider(provider_name: str, **kwargs: Any) -> NewsSentimentProvider`
   * `get_fundamentals_provider(provider_name: str, **kwargs: Any) -> FundamentalsProvider`

If an invalid/unregistered provider name is requested, the factory must raise a clear `ValueError` specifying the invalid name and the list of available providers.

---

### R4.6.3 Dependency Injection

To ensure loose coupling:
1. Core pipelines (`run_hot_cold_strategy_pipeline` in `prescient.runtime.pipeline`) must not instantiate data providers. They should accept pre-fetched domain models or accept configured provider instances typed with the above Protocols.
2. The runtime orchestrator or runner must use the factory to build the requested providers using system settings, then pass those providers down (Dependency Injection).

---

### R4.6.4 Standardized Configuration Schema

A clean YAML configuration structure under `config/config.yaml` (or equivalent `StrategySettings` / Pydantic models) should define the provider mapping:

```yaml
data_providers:
  peers:
    provider: "fmp"
    api_key: "${FMP_API_KEY}"
  news_sentiment:
    provider: "alpha_vantage"
    api_key: "${ALPHA_VANTAGE_API_KEY}"
  fundamentals:
    provider: "financial_datasets"
    api_key: "${FINANCIAL_DATASETS_API_KEY}"
    kpi_endpoint: "/customer-docs/kpis" # Custom parameters passed as kwargs
```

If a provider config specifies a missing environment variable or key, the system must bubble a structured `DataProviderError` of type `MISSING_API_KEY` at runtime initialization.

---

### R4.6.5 Uniform Structured Errors & Model Types

* Regardless of the underlying API error or HTTP failure, the pluggable adapters must convert all network issues, timeouts, rate limits, and parsing errors into the standard `DataProviderError` model defined in R4.2/R4.4.
* Swapping one implementation for another must never bubble raw HTTPExceptions (like `httpx.HTTPStatusError`) or parsing exceptions (like `json.JSONDecodeError`) to the caller.

---

## Acceptance Criteria

1. **Protocol Specifications Exist**: Standard Protocols are defined and documented for Peers, News & Sentiment, and Fundamentals.
2. **Zero Concrete Imports in Core**: The boundary tests (`tests/test_data_boundaries.py`) pass, ensuring that no core packages (`signal`, `risk`, `runtime`, `scheduler`, `events`, `analyst`) import concrete files like `prescient.data.fmp` or `prescient.data.alpha_vantage` directly.
3. **Configuration Swapping**: Changing the provider key in config (e.g. from `"fmp"` to `"mock"`) resolves the mock class without requiring a single code line change in the pipeline runners.
4. **Invalid Provider Error Handling**: Calling the factory with an unsupported provider name (e.g. `"unsupported_provider"`) throws a structured ValueError listing valid options.
5. **Uniform Errors**: All adapter implementations return the unified `DataProviderError` schema rather than vendor-specific or raw python exceptions.
6. **No Breaking Changes**: Existing tests for FMP and Alpha Vantage continue to pass without changes to their strategy evaluation outcomes.

---

## Non-Goals

* No caching layer implementation within this PRD.
* No live broker/execution client pluggability in this milestone (this is for read-only market data only).
* No validation of credentials directly against remote servers during factory construction (validation happens when performing requests, unless configured otherwise).
