# PRD: R4.5 SEC Filings for Fundamentals & KPIs

## Ownership

Owner: Ours

Source note: Requirement from GPT: add read-only SEC filing, fundamentals, and KPI enrichment using a tiered provider strategy across SEC EDGAR data APIs, Financial Datasets, and Daloopa.

## Objective

Add a read-only fundamentals/KPI data layer under `prescient.data` that can fetch, normalize, and preserve provenance for SEC filing metadata, XBRL fundamentals, normalized financial statements, and operating KPIs.

R4.5 answers:

```text
What reported fundamentals and source-linked KPIs support or weaken the earnings read-through thesis for this ticker?
```

This is enrichment only. R4.5 must not make strategy decisions, place trades, call Claude for extraction, or mutate the configured strategy universe.

## Background

The existing strategy engine already reasons about revenue, EPS, guidance, peer evidence, and source-safe analyst context. R4.5 adds a provider-neutral data boundary for reported company fundamentals and operating KPIs.

Sources:

- [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces): `companyfacts`, `companyconcept`, `frames`, and bulk archives.
- [SEC EDGAR fair access guidance](https://www.sec.gov/os/accessing-edgar-data): declare `User-Agent`, keep automated access efficient, and respect the current 10 requests/second guideline.
- [Financial Datasets financial statements](https://docs.financialdatasets.ai/api/financials/all-financial-statements): normalized income statement, balance sheet, and cash flow data via `/financials`.
- [Financial Datasets KPI metrics](https://docs.financialdatasets.ai/api/kpi/metrics): source-linked operational KPIs via `/kpi/metrics`.
- [Financial Datasets filing items](https://docs.financialdatasets.ai/api/filings/items): section-level 10-K, 10-Q, and 8-K filing text.
- [Daloopa API](https://www.daloopa.com/products/api): premium standardized fundamentals/KPI provider with source-linked datapoints.

## Functional Requirements

### R4.5.1 Read-Only Adapter Boundary

Adapters must live under `prescient.data`.

They must not:

- Place trades.
- Import broker code.
- Import Claude / analyst code.
- Import risk code.
- Mutate strategy decisions.
- Write journal records directly.
- Call runtime directly.
- Modify `config/themes.yaml`.
- Use SEC filer submission APIs.

### R4.5.2 Tiered Provider Strategy

Use a provider-neutral interface with these provider roles:

- SEC EDGAR: authoritative public baseline for filing metadata and XBRL company facts.
- Financial Datasets: normalized fundamentals, statements, KPI metrics, and filing item text when API credentials are configured.
- Daloopa: premium source-linked KPI/fundamental enrichment when customer API access and current docs are available.

Paid-provider absence must return structured errors and must not block SEC-only enrichment.

### R4.5.3 Normalized Models

Normalize provider responses into internal models with these concepts:

- `FilingSnapshot`: ticker, CIK, form type, accession number, filing date, report period, fiscal year/quarter, source URL, provider.
- `FundamentalMetric`: ticker, CIK, metric name, value, unit/currency, period, fiscal period, statement type, taxonomy/concept when available, accession number, source URL, provider.
- `KpiMetric`: ticker, metric name, value, unit, period, period type, segment when supplied, YoY value/change when supplied, source text, source URL, provider.
- `FundamentalsResult` / `KpiResult`: normalized snapshots plus structured provider errors.

Tickers must normalize to uppercase. SEC CIKs must normalize to 10-digit zero-padded strings.

### R4.5.4 Lookup Behavior

Support these read paths:

- SEC filing history and filing metadata by ticker or CIK.
- SEC company facts by CIK using `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
- SEC single concept lookup using `companyconcept` when callers request a specific taxonomy tag.
- Financial Datasets normalized statements using `/financials` with ticker or CIK, period, limit, and report-period filters.
- Financial Datasets KPI metrics using `/kpi/metrics` with ticker, metric name, period, date filters, and limit.
- Financial Datasets filing items for source text when explicitly requested.
- Daloopa fundamentals/KPIs only through documented customer API access; do not invent undocumented endpoint names.

Optional filters must be omitted when not supplied.

### R4.5.5 Provenance and Reconciliation

Every normalized metric must preserve provider, source endpoint, and source URL or accession provenance when available.

If multiple providers return the same metric, the data layer must keep separate provider-attributed records. It must not silently overwrite one provider with another.

The adapter may normalize field names and units supplied by providers, but it must not hallucinate missing KPI values or derive new metrics unless a future deterministic calculation milestone defines them.

### R4.5.6 Provider Error Handling

Return structured provider errors for:

- Missing paid-provider API key.
- Missing SEC user-agent configuration.
- Unauthorized, forbidden, or payment-required access.
- Rate limiting.
- Timeout.
- Malformed response.
- Empty response.
- Unsupported ticker/CIK.
- Provider unavailable.
- Filing parse in progress / retry-after responses.

Errors must be journal-safe and must not include API keys, request headers, raw secrets, or full raw payloads.

### R4.5.7 No Raw Provider Leakage

Raw SEC, Financial Datasets, or Daloopa payloads may be used inside parsers only. They must not be passed into:

- `prescient.signal`
- `prescient.risk`
- `prescient.analyst`
- `prescient.runtime`
- `prescient.scheduler`

Core strategy code may consume only normalized models or already-filtered ticker/metric summaries.

## Acceptance Criteria and Test Scenarios

- SEC company facts normalize deterministic fundamentals with ticker/CIK, concept, value, unit, accession, period, and provider metadata.
- Financial Datasets statements normalize income statement, balance sheet, and cash flow fields without leaking raw JSON.
- Financial Datasets KPI responses normalize metric name, value, unit, segment, period, YoY fields, source text, and source URL.
- Daloopa responses normalize through the same provider-neutral KPI/fundamental models when fixture docs are available.
- Missing credentials, SEC missing user-agent, 401/403/402/429/503, timeout, malformed JSON, empty response, and unsupported symbols return structured errors.
- Multiple providers returning the same metric remain distinct provider-attributed records.
- Existing signal, scheduler, runtime, analyst, and risk tests continue to pass unchanged.
- Boundary tests prove deterministic layers do not import SEC, Financial Datasets, or Daloopa adapter code.

## Non-Goals

- No broker integration.
- No order placement.
- No Claude-based filing extraction.
- No full HTML/XBRL filing parser beyond provider/API payload normalization.
- No automatic KPI discovery from unstructured text.
- No automatic strategy decisions or scoring changes.
- No webhook ingestion, cache/database layer, or bulk archive ingestion unless required by a later storage milestone.
- No SEC filing submission API support.

## Assumptions and Defaults

- Provider posture is tiered: SEC baseline, Financial Datasets normalized provider, Daloopa premium enrichment.
- SEC requests require a configured descriptive `User-Agent`.
- Paid providers are optional and plan-gated.
- Daloopa endpoints must be supplied from customer documentation; implementation must not invent undocumented Daloopa routes.
