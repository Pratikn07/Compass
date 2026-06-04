# PRD: R4.1 Finnhub Earnings Calendar + Estimates / Actuals

## Ownership

Owner: Ours

Source note: Requirement from Ours, GPT-assisted: use Finnhub as the primary read-only provider for earnings calendar dates, EPS estimates, revenue estimates, and reported EPS / revenue actuals.

## Objective

Add a read-only Finnhub data adapter that can fetch normalized earnings calendar data and earnings estimate / actual data for configured tickers.

R4.1 answers:

```text
Which configured companies report earnings soon, which peers have already reported, and what structured EPS / revenue estimate and actual values are available?
```

This data is a core input to the deterministic earnings read-through strategy. It must feed existing signal-layer concepts such as `EarningsCalendarEvent` and `EarningsEvent`, but the provider adapter itself must remain isolated under `prescient.data`.

## Background

The current strategy engine already expects two earnings inputs:

- upcoming target earnings calendar events
- completed peer earnings events with EPS and revenue estimate / actual values

Candidate detection uses upcoming events to find targets reporting inside the configured earnings window. Peer scoring uses completed events to determine EPS beats / misses and revenue beats / misses. R4.1 provides the first real provider integration for those inputs.

Finnhub exposes several relevant endpoints:

- [Earnings Calendar](https://finnhub.io/docs/api/earnings-calendar): calendar-window earnings data, including symbol, report date, report time, quarter, year, and EPS / revenue estimate and actual values when available.
- [Company Earnings](https://finnhub.io/docs/api/company-earnings): historical company earnings values including actual, estimate, surprise, and surprise percent.
- [Company EPS Estimates](https://finnhub.io/docs/api/company-eps-estimates): analyst EPS estimate snapshots by annual or quarterly frequency.
- [Company Revenue Estimates](https://finnhub.io/docs/api/company-revenue-estimates): analyst revenue estimate snapshots by annual or quarterly frequency.

Finnhub is the primary provider for this milestone. Future provider swaps should follow R4.6 pluggable adapter requirements.

## Functional Requirements

### R4.1.1 Read-Only Adapter Boundary

The Finnhub earnings adapter must live under `prescient.data`.

It must not:

- Place trades.
- Import broker code.
- Import Claude / analyst code.
- Import risk code.
- Mutate strategy decisions.
- Write journal records directly.
- Call runtime directly.
- Modify `config/themes.yaml`.
- Expand the configured universe automatically.

### R4.1.2 Provider-Neutral Earnings Models

The adapter must normalize Finnhub responses into internal models before any data reaches deterministic strategy code.

Required normalized fields for earnings calendar snapshots:

- `ticker`
- `earnings_date`
- `report_time`
- `fiscal_year`, when supplied
- `fiscal_quarter`, when supplied
- `eps_estimate`, when supplied
- `eps_actual`, when supplied
- `revenue_estimate`, when supplied
- `revenue_actual`, when supplied
- `provider = "finnhub"`
- `source_endpoint`
- `provider_notes`, when useful
- `fetched_at`, only if supplied by the caller
- structured provider errors, if any

The normalized data layer must provide conversion into existing signal models:

- upcoming entries become `EarningsCalendarEvent`
- completed entries become `EarningsEvent`

Tickers must normalize to uppercase. Empty or malformed tickers must not enter signal-layer data.

### R4.1.3 Earnings Calendar Window Lookup

The adapter must support fetching a bounded earnings calendar window.

Expected provider endpoint:

```text
GET /calendar/earnings
```

Required request parameters:

- `from`
- `to`
- `token`

Optional request parameter:

- `symbol`

The adapter must support:

- a single configured ticker
- a deduplicated sequence of configured tickers
- a bounded date window for the configured universe

If the provider supports only one symbol per request for the desired response shape, the adapter may call the endpoint once per ticker and combine normalized results. Calls must remain bounded by caller-supplied tickers and date ranges.

The adapter must not issue unbounded broad-market calendar scans unless the caller explicitly supplies a bounded date range and no symbol filter.

### R4.1.4 Report Time Normalization

Finnhub report-time values must normalize into the existing signal-layer `ReportTime` values:

- before-market-open values such as `bmo` normalize to `BMO`
- after-market-close values such as `amc` normalize to `AMC`
- missing, unknown, or unsupported values normalize to `UNKNOWN`

The adapter must not reject an otherwise usable earnings event only because report time is unknown.

### R4.1.5 Estimates and Actuals Normalization

The adapter must normalize EPS and revenue values into numeric `float` values where possible.

Required behavior:

- Blank, missing, or non-numeric EPS / revenue values normalize to `None`.
- EPS estimates and actuals must not be inferred from revenue fields, surprise fields, or text.
- Revenue estimates and actuals must not be inferred from EPS fields, surprise fields, or text.
- Actual values must remain `None` for upcoming events when the provider has not reported actuals.
- Estimate values may remain `None` when the provider does not supply them.

Missing structured inputs are valid data states. They must flow downstream as missing values so existing scoring can record missing factors instead of hallucinating beats or misses.

### R4.1.6 Company Earnings History Lookup

The adapter must support fetching company earnings history for a single ticker.

Expected provider endpoint:

```text
GET /stock/earnings
```

Required request parameters:

- `symbol`
- `token`

Optional request parameter:

- `limit`

Company earnings history may be used to enrich completed peer events with EPS actual / estimate values and surprise metadata.

The adapter must not treat a fiscal period value from the company earnings endpoint as an actual report date when a real report date is unavailable. Completed `EarningsEvent` objects require a true earnings date from calendar data or another explicit report-date source. If only fiscal-period history is available, the adapter must return normalized provider data but not fabricate a completed signal event date.

### R4.1.7 EPS and Revenue Estimate Lookup

The adapter should support fetching EPS and revenue estimate snapshots for a single ticker.

Expected provider endpoints:

```text
GET /stock/eps-estimate
GET /stock/revenue-estimate
```

Required request parameters:

- `symbol`
- `token`

Optional request parameter:

- `freq`, with supported values `annual` and `quarterly`

Estimate snapshots may be used to backfill missing EPS or revenue estimate values for upcoming calendar events when period alignment is clear.

The adapter must not attach an estimate to an earnings event unless the fiscal period or date alignment is deterministic.

### R4.1.8 Pure Merge and Conversion Helpers

The data layer may provide pure helpers to merge calendar data, company earnings history, EPS estimates, and revenue estimates.

Required behavior:

- Helpers must not mutate input snapshots.
- Helpers must not mutate the configured `StrategyUniverse`.
- Helpers must not create new strategy themes.
- Helpers must preserve provider order unless sorting is explicitly required by date.
- Helpers must prefer true calendar report dates over fiscal period labels.
- Helpers must preserve `None` for values that cannot be aligned confidently.

### R4.1.9 Provider Error Handling

The adapter must return structured provider errors for:

- Missing API key / token.
- Unauthorized or forbidden access.
- Payment-required or plan-gated access.
- Rate limiting.
- Timeout.
- Malformed provider response.
- Empty provider response.
- Unsupported symbol.
- Provider temporarily unavailable.

Errors must be journal-safe and must not include API keys, request headers, raw secrets, full raw payloads, account identifiers, prompts, or broker details.

Raw `httpx` errors, JSON parsing errors, and provider-specific response shapes must not leak to callers.

### R4.1.10 No Raw Provider Leakage

Raw Finnhub JSON may be used internally by the adapter parser, but it must not be passed into:

- `prescient.signal`
- `prescient.risk`
- `prescient.analyst`
- `prescient.runtime`
- `prescient.scheduler`
- `prescient.events`

Core strategy code must receive only normalized models or existing signal-layer earnings models.

### R4.1.11 Pluggable Provider Registration

The implementation should prepare for R4.6 by exposing a provider protocol and factory entry for earnings data.

Expected interface shape:

```python
class EarningsProvider(Protocol):
    def get_earnings_calendar(...) -> EarningsCalendarResult:
        ...

    def get_company_earnings(...) -> CompanyEarningsResult:
        ...

    def get_eps_estimates(...) -> EarningsEstimateResult:
        ...

    def get_revenue_estimates(...) -> RevenueEstimateResult:
        ...
```

Expected factory behavior:

```python
get_earnings_provider("finnhub", token="...")
```

Unsupported provider names must raise a clear `ValueError` listing valid earnings providers.

### R4.1.12 Scheduler and Runtime Usage

Scheduler and runtime layers must consume pre-fetched normalized earnings data or provider instances typed by protocol. They must not import `prescient.data.finnhub` directly.

The scheduler should use R4.1 data for bounded earnings-calendar wakes:

- upcoming target lookahead window
- recent peer-result lookback window
- configured universe tickers only, unless explicitly asked for a broader bounded scan

R4.1 must not introduce continuous polling.

## Acceptance Criteria

- Finnhub earnings calendar responses normalize into deterministic internal snapshots.
- Upcoming calendar rows convert into `EarningsCalendarEvent` without raw provider payloads.
- Completed calendar rows with actual values convert into `EarningsEvent` without raw provider payloads.
- Ticker symbols normalize to uppercase and deduplicate when callers request multiple symbols.
- Report-time values normalize to `BMO`, `AMC`, or `UNKNOWN`.
- EPS and revenue estimate / actual values normalize to floats or `None`.
- Missing estimates or actuals are preserved as missing values rather than inferred.
- Company earnings history can enrich completed peer data but must not fabricate report dates from fiscal periods.
- EPS and revenue estimate endpoints can backfill estimates only when period alignment is deterministic.
- Missing token, unauthorized access, payment-required access, rate limits, timeouts, malformed responses, empty responses, unsupported symbols, and provider unavailability return structured `DataProviderError` values.
- Provider errors are journal-safe and do not expose Finnhub tokens or raw payloads.
- The data package exposes an earnings provider protocol and a Finnhub factory registration compatible with R4.6.
- Deterministic layers do not import concrete Finnhub adapter code.
- Existing signal, scheduler, runtime, analyst, risk, and broker tests continue to pass unchanged.

## Non-Goals

- No broker integration.
- No order placement.
- No Claude analysis.
- No automatic strategy decisions.
- No automatic watchlist or theme expansion.
- No peer-list enrichment; that belongs to R4.2.
- No news or sentiment enrichment; that belongs to R4.4.
- No SEC filing, financial statement, or KPI enrichment; that belongs to R4.5.
- No earnings-call transcript summarization; that belongs to R4.7.
- No price reaction or indicator calculation.
- No options-chain lookup.
- No cache or database layer unless required by a later storage milestone.
- No streaming earnings feed.
- No continuous polling loop.
