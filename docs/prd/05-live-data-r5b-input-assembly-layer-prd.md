# PRD: R5B Live Data Input Assembly Layer

## Ownership

- **Layer:** `prescient.data`
- **Phase:** B of the Live Provider Data roadmap
- **Depends on:** Phase A provider configuration/builders and provider contract audit

## Objective

Build a deterministic input assembly layer that converts read-only provider outputs
into the existing scheduler/runtime pipeline inputs:

```text
providers -> assemble_pipeline_inputs(...) -> run_scheduled_strategy_pipeline(...)
```

R5B answers:

```text
Can the system assemble real provider data into typed strategy inputs without changing
the strategy engine, cron behavior, storage writes, broker behavior, or Claude rails?
```

## Background

The core strategy pipeline already accepts fully typed inputs:
`EarningsCalendarEvent`, `PeerResult`, `TargetMarketData`,
`TechnicalIndicatorSnapshot`, and `OptionContractSnapshot`. Seed data currently
constructs these inputs directly. Phase B replaces only that manual assembly gap.

The configured strategy universe remains the source of truth. Provider peer data is
diagnostic evidence, not permission to add new theme tickers.

## Functional Requirements

### R5B.1 FMP Market Data Adapter

Add a read-only FMP market-data adapter for historical EOD price and volume data.

```python
class HistoricalPriceCandle(BaseModel): ...
class HistoricalPriceResult(BaseModel): ...

class FmpMarketDataAdapter:
    def get_historical_prices(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
        fetched_at: datetime | None = None,
    ) -> HistoricalPriceResult: ...
```

The adapter must use injected HTTP transports in tests and must map missing keys,
HTTP errors, malformed responses, and empty responses to `DataProviderError`.

### R5B.2 Assembly Contract

Add `prescient.data.assembly` with:

- `PipelineInputProviders`
- `PipelineInputAssemblySettings`
- `PipelineInputAssemblyResult`
- `assemble_pipeline_inputs(...)`

The result must contain typed pipeline inputs, provider diagnostics, provider errors,
and skipped targets.

### R5B.3 Earnings Assembly

Use Finnhub earnings calendar data for all configured universe tickers.

- Upcoming events: `current_date` through
  `current_date + StrategySettings.earnings_window_days`.
- Completed peer events: `current_date - StrategySettings.peer_result_window_days`
  through `current_date`.

### R5B.4 Peer Assembly

Assemble `PeerResult` from completed Finnhub events plus FMP historical prices.

- `BMO`: event-day close versus previous trading close.
- `AMC` or `UNKNOWN`: next available trading close after earnings versus previous
  trading close.
- Missing price data becomes `price_reaction_pct=None`.
- `guidance_signal` and `theme_driver_signal` default to `unknown`.

### R5B.5 Target Market Data And Indicators

Use FMP historical EOD prices for each upcoming in-universe target.

- `avg_daily_volume`: average of the latest 30 available candle volumes.
- `pre_earnings_runup_pct`: latest close versus close 21 trading candles earlier.
- RSI 14, MACD 12/26/9, and latest VWAP are computed deterministically.
- Missing indicator values are listed in `missing_fields`.

### R5B.6 News Conflict Policy

Use AlphaVantage news sentiment only when available. Set
`TargetMarketData.has_conflicting_news=True` only when target sentiment is clearly
bearish: ticker relevance is at least `0.35` and sentiment score is at most `-0.35`,
or the sentiment label is `Bearish` with equivalent relevance.

### R5B.7 Options Boundary

Return empty options chains. Phase C owns options-chain provider selection and
`OptionContractSnapshot` production.

## Acceptance Criteria

1. FMP market data models, adapter, and builder exist and are unit-tested with fake
   transports.
2. `assemble_pipeline_inputs(...)` returns typed runtime-ready inputs using fake
   providers in tests.
3. Provider errors are collected and do not crash assembly unless construction itself
   is invalid.
4. Configured themes are never expanded from FMP peer lists.
5. Options chains remain empty and documented as Phase C.
6. Existing scheduler/runtime APIs are unchanged.
7. `ruff check .` and targeted Phase B tests pass.

## Non-Goals

- Replacing seed cron or enabling the live-data cron.
- Writing provider snapshots/errors to Supabase from the assembler.
- Adding an options-chain provider.
- Adding broker, Claude, or live-mode behavior.
- Caching, retries, rate-limit budgeting, or provider health dashboards.
