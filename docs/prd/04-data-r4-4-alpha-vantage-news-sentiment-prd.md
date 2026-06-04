# PRD: R4.4 Alpha Vantage News & Sentiment

## Ownership

Owner: Ours

Source note: Requirement from Ours: use Alpha Vantage's Market News & Sentiment API as a primary read-only provider for external news and sentiment enrichment.

## Objective

Add a read-only Alpha Vantage data adapter that can fetch normalized market news and sentiment for configured tickers and topics.

R4.4 answers:

```text
What current or historical provider news mentions these symbols or topics, and what sentiment did the provider assign?
```

This is read-only enrichment for review and downstream research context. It must not become a trading trigger by itself.

## Background

Alpha Vantage exposes market news and sentiment through the `NEWS_SENTIMENT` function on its `/query` endpoint. The API can filter by stock, crypto, and forex tickers, topics, time ranges, sort order, and result limit.

Provider source:

- [Alpha Vantage API Documentation](https://www.alphavantage.co/documentation/)

## Functional Requirements

### R4.4.1 Read-Only Adapter Boundary

The Alpha Vantage adapter must live under `prescient.data`.

It must not place trades, import broker code, import Claude or analyst code, import risk code, write journal records directly, call runtime directly, or mutate strategy decisions.

### R4.4.2 Provider-Neutral News Model

The adapter must normalize provider responses into internal models.

Required normalized fields:

- query tickers
- topics
- provider = `alpha_vantage`
- source endpoint
- provider notes, when useful
- fetched_at, only if supplied by the caller
- articles with title, URL, published time, source, authors, summary, topics, ticker sentiment, and overall sentiment when supplied
- structured provider errors, if any

Ticker symbols must normalize to uppercase. Topic filters must normalize to lowercase.

### R4.4.3 News & Sentiment Lookup

The adapter must support fetching Alpha Vantage news and sentiment with these provider parameters:

- `function=NEWS_SENTIMENT`
- `tickers`
- `topics`
- `time_from`
- `time_to`
- `sort`
- `limit`
- `apikey`

It must omit optional filters when callers do not supply them.

### R4.4.4 Provider Error Handling

The adapter must return structured provider errors for:

- missing API key
- unauthorized or premium-plan access
- rate limiting
- timeouts
- malformed provider responses
- empty provider responses
- unsupported symbols
- provider unavailability

Errors must be journal-safe and must not include API keys, request headers, raw secrets, or raw provider payloads.

### R4.4.5 No Raw Provider Leakage

Raw Alpha Vantage JSON may be used internally by the adapter parser, but it must not be passed into:

- `prescient.signal`
- `prescient.risk`
- `prescient.analyst`
- `prescient.runtime`
- `prescient.scheduler`

Core strategy code must receive only normalized models or already-filtered context.

## Acceptance Criteria

- Alpha Vantage news responses normalize into deterministic internal snapshots.
- Ticker and topic query filters normalize deterministically.
- Provider article topics, ticker sentiment, and overall sentiment normalize without leaking raw JSON.
- Missing API keys, HTTP failures, provider `Note`, `Information`, and `Error Message` payloads return structured errors.
- Provider errors are journal-safe.
- Alpha Vantage news remains read-only enrichment and must not place trades.
- No automatic strategy decisions are made from news or sentiment alone.
- Existing signal, scheduler, runtime, analyst, and risk tests continue to pass unchanged.
- Boundary tests prove deterministic layers do not import provider adapter code.

## Non-Goals

- No broker integration.
- No order placement.
- No Claude analysis.
- No automatic strategy decisions.
- No automatic watchlist expansion.
- No cache or database layer unless required by a later storage milestone.
- No earnings transcripts, price, indicator, options, SEC filing, or FMP peer support.
