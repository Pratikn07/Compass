# PRD: R4.2 FMP Stock Peers / Competitor Lists

## Ownership

Owner: Ours

Source note: Requirement from Ours: use Financial Modeling Prep's stock peers endpoint as the primary read-only provider for peer / competitor list enrichment.

## Objective

Add a read-only FMP data adapter that can fetch normalized stock peer lists for configured tickers.

R4.2 answers:

```text
Which companies does an external data provider identify as comparable peers for this ticker?
```

This must be used as peer enrichment only. FMP peers must not automatically replace or expand `config/themes.yaml`, because the strategy thesis depends on user-defined themes and shared demand drivers, not just sector / market-cap similarity.

## Background

The current strategy system already has a configured `StrategyUniverse` and theme-based ticker groups. That user-defined universe remains the source of truth for strategy evaluation.

FMP's Stock Peer Comparison API describes peers as companies on the same exchange, in the same sector, and with similar market capitalization. That is useful for discovery and review, but it is not the same thing as the app's thesis requirement: peers must share the same demand-driver theme.

Sources:

- [FMP Stock Peer Comparison API](https://site.financialmodelingprep.com/developer/docs/stock-peers-api/?direct=true)
- [FMP Stock Peers Bulk API](https://site.financialmodelingprep.com/developer/docs/bulk-stock-peers)
- [FMP Quickstart](https://site.financialmodelingprep.com/developer/docs/quickstart)

## Functional Requirements

### R4.2.1 Read-Only Adapter Boundary

The FMP peer adapter must live under `prescient.data`.

It must not:

- Place trades.
- Import broker code.
- Import Claude / analyst code.
- Import risk code.
- Mutate strategy decisions.
- Write journal records directly.
- Call runtime directly.
- Modify `config/themes.yaml` automatically.

### R4.2.2 Provider-Neutral Peer Model

The adapter must normalize FMP responses into internal models.

Required normalized fields:

- `ticker`
- `peers`
- `provider = "fmp"`
- `source_endpoint`
- `provider_notes`, when useful
- `fetched_at`, only if supplied by the caller
- structured provider errors, if any

Tickers must normalize to uppercase.

Peer lists must:

- Remove blank symbols.
- Normalize symbols to uppercase.
- Deduplicate while preserving provider order.
- Exclude the target ticker itself if returned by the provider.

### R4.2.3 Single-Ticker Peer Lookup

The adapter must support fetching peers for one ticker.

Expected provider endpoint:

```text
https://financialmodelingprep.com/stable/stock-peers?symbol=AAPL&apikey=...
```

The response must normalize into one internal peer-list snapshot.

### R4.2.4 Bulk Peer Lookup

The adapter should support fetching bulk peer data when the provider plan supports it.

Expected provider endpoint:

```text
https://financialmodelingprep.com/stable/peers-bulk?apikey=...
```

Bulk output must normalize into a mapping of ticker to peer-list snapshot.

If bulk access is unavailable or plan-gated, the adapter must return a structured provider error and allow callers to fall back to single-ticker lookup.

### R4.2.5 Theme-Aware Filtering Helper

The data layer may provide a pure helper that filters provider peers against the current `StrategyUniverse`.

Required behavior:

- `filter_peers_to_theme(provider_peers, universe, theme_name)` returns only peers present in that configured theme.
- `filter_peers_to_universe(provider_peers, universe)` returns only peers present anywhere in the configured universe.
- Filtering must not mutate the universe.
- Filtering must not create new strategy themes.

### R4.2.6 Provider Error Handling

The adapter must return structured provider errors for:

- Missing API key.
- Unauthorized / forbidden plan access.
- Rate limited.
- Timeout.
- Malformed provider response.
- Empty provider response.
- Unsupported symbol.
- Provider temporarily unavailable.

Errors must be journal-safe and must not include API keys, request headers, raw secrets, or full raw payloads.

### R4.2.7 No Raw Provider Leakage

Raw FMP JSON may be used internally by the adapter parser, but it must not be passed into:

- `prescient.signal`
- `prescient.risk`
- `prescient.analyst`
- `prescient.runtime`
- `prescient.scheduler`

Core strategy code must receive only normalized models or already-filtered ticker lists.

## Acceptance Criteria

- FMP single-ticker stock peer responses normalize into deterministic internal peer-list snapshots.
- FMP bulk peer responses normalize into deterministic ticker-to-peer mappings.
- Duplicate, blank, lowercase, and self-referential symbols are cleaned.
- FMP peers do not automatically modify `config/themes.yaml`.
- Theme-aware filtering only returns peers already configured in the strategy universe.
- Provider failures return structured errors, not exceptions leaking raw payloads.
- Existing signal, scheduler, runtime, analyst, and risk tests continue to pass unchanged.
- Boundary tests prove deterministic layers do not import FMP adapter code.

## Non-Goals

- No broker integration.
- No order placement.
- No Claude analysis.
- No automatic theme generation.
- No automatic watchlist expansion.
- No peer scoring changes.
- No earnings result fetching; that belongs to R4.1.
- No news, sentiment, transcript, price, indicator, or SEC filing support.
- No caching/database layer unless required by a later data-store or journal milestone.

