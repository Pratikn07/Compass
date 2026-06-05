# Live Data Provider Contract Audit

**Status:** Phase A handoff for Phase B input assembly.
**Scope:** Existing read-only provider adapters and the typed pipeline inputs they can
populate.

## Purpose

This audit records what the current provider adapters return and how those outputs map
to the Phase B input assembly layer. It is the contract baseline for implementing
`assemble_pipeline_inputs(...)`.

Live credential smoke checks remain explicit-only through `scripts/verify_providers.py`.
When run with real keys, update this document with any provider shape drift observed in
the raw responses.

## Provider Matrix

| Provider | Adapter | Current output | Phase B use |
|---|---|---|---|
| Finnhub | `FinnhubEarningsAdapter` | `EarningsCalendarResult`, `CompanyEarningsResult`, EPS/revenue estimates | Upcoming target events and completed peer earnings events |
| FMP | `FmpStockPeersAdapter` | `PeerListResult` | Peer diagnostics only; configured themes remain source of truth |
| FMP | `FmpMarketDataAdapter` | `HistoricalPriceResult` | Target market data, peer price reaction, RSI/MACD/VWAP indicators |
| AlphaVantage | `AlphaVantageNewsSentimentAdapter` | `NewsSentimentResult` | Conservative conflicting-news flag and citations |
| SEC EDGAR | `SecEdgarFundamentalsAdapter` | facts, filings, concepts | Not required for Phase B MVP input assembly |

## Pipeline Input Coverage

| Pipeline input | Source | Coverage |
|---|---|---|
| `EarningsCalendarEvent` | Finnhub earnings calendar | Populated for configured tickers with future events in the strategy window |
| `PeerResult.earnings_event` | Finnhub earnings calendar | Populated from completed peer events with actuals |
| `PeerResult.price_reaction_pct` | FMP historical EOD prices | Derived from prior close to event/next close based on report time |
| `PeerResult.guidance_signal` | Transcript summary when available | Defaults to `unknown` in Phase B unless a transcript summary is injected later |
| `PeerResult.theme_driver_signal` | Transcript summary when available | Defaults to `unknown` in Phase B unless a transcript summary is injected later |
| `TargetMarketData.avg_daily_volume` | FMP historical EOD prices | Derived from last 30 available candles |
| `TargetMarketData.pre_earnings_runup_pct` | FMP historical EOD prices | Derived from latest close versus close 21 trading candles earlier |
| `TargetMarketData.has_conflicting_news` | AlphaVantage news sentiment | True only for clearly bearish target news |
| `TechnicalIndicatorSnapshot` | FMP historical EOD prices | Deterministic RSI 14, MACD 12/26/9, latest VWAP/price-vs-VWAP |
| `OptionContractSnapshot` | None in current providers | Empty until Phase C options-chain provider |

## Phase B Defaults

- Strategy universe comes from `config/themes.yaml`; provider peer lists do not expand
  themes.
- Missing provider fields become explicit `None`, `unknown`, or `missing_fields`
  values, not fabricated data.
- Provider errors are collected in assembly results and are journal-safe.
- No Supabase writes, cron replacement, broker calls, Claude calls, or live-mode changes.

## Known Gaps

- Options-chain sourcing is intentionally deferred to Phase C.
- SEC EDGAR fundamentals do not directly fill the current Phase B MVP input contract.
- Real provider shape drift can only be confirmed by manually running
  `uv run python scripts/verify_providers.py` with real keys.
