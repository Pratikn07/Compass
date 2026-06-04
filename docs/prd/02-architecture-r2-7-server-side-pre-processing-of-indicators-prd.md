# PRD: R2.7 Server-Side Pre-Processing Of Indicators

## Ownership

Owner: Gem

## Objective

Ensure technical indicators used by `prescient` are computed before Claude sees any candidate.

RSI, MACD, VWAP, and related technical signals must be produced by the market-data provider layer or deterministic server-side preprocessing, not by Claude.

Claude may read compact structured indicator summaries, but it must not receive raw candle streams or calculate technical indicators inside a prompt.

## Background

`prescient` separates deterministic strategy logic from cold-path Claude analysis.

R2.4 defines the deterministic signal engine as code-owned. R2.5 defines Claude as analyst only. R2.6 allows optional focused sub-agents, including a Technical Agent, but still requires structured inputs and forbids Claude from computing hidden indicators from raw price streams.

R2.7 makes that boundary explicit for technical indicators.

```text
market data provider / server preprocessing
  -> compact indicator snapshot
  -> deterministic target filters / candidate brief
  -> optional Claude analyst or Technical Agent
```

The goal is to reduce prompt tokens, reduce latency, improve repeatability, and keep technical calculations auditable.

## Definitions

### Indicator Snapshot

An indicator snapshot is a compact structured record for a ticker and as-of timestamp or trading date.

It may include:

- RSI value and interpretation.
- MACD line, signal line, histogram, and crossover state.
- VWAP value and price-vs-VWAP state.
- Recent trend or momentum labels derived by deterministic rules.
- Missing-data flags.
- Data freshness metadata.

It must not include long raw OHLCV candle arrays unless explicitly needed outside Claude.

### Provider Layer

The provider layer is the part of the system that obtains market data and returns structured snapshots to the strategy pipeline.

For R2.7, "provider layer" may mean:

- An external data provider that directly returns computed indicators.
- A local server-side adapter that computes indicators deterministically from provider OHLCV data before the strategy engine or Claude receives it.

In both cases, Claude must not compute the indicator.

### Technical Indicator Consumer

A technical indicator consumer is deterministic code, a candidate brief builder, the cold-path Claude analyst, or a future R2.6 Technical Agent that reads already-computed indicator fields.

Consumers may interpret provided fields, but they must not derive RSI, MACD, or VWAP from raw candle history inside Claude.

## Requirement

Technical indicators must be computed outside Claude and passed through the system as bounded structured fields.

Claude and any optional sub-agent may receive only compact indicator snapshots or summaries. They must not receive raw price history for the purpose of calculating RSI, MACD, VWAP, trend, volume-weighted levels, or crossover states.

## User Value

This requirement gives the user:

- Lower Claude token usage.
- Lower Claude latency.
- More repeatable technical signals.
- Easier test coverage for technical calculations.
- Cleaner audit trails for why a technical setup passed or failed.
- Better separation between data processing and analyst judgment.

## Functional Requirements

### R2.7.1 Indicator Computation Boundary

RSI, MACD, VWAP, and derived technical labels must be computed before Claude analysis.

Allowed computation locations:

- External market-data provider API.
- Internal provider adapter.
- Deterministic server-side preprocessing module.

Disallowed computation locations:

- Claude analyst prompt.
- Claude sub-agent prompt.
- Free-form transcript or news parsing.
- Broker execution layer.

### R2.7.2 Structured Indicator Snapshot

The system must represent indicators as typed structured data.

Minimum MVP fields should include:

- `ticker`
- `as_of`
- `rsi_14`
- `macd_line`
- `macd_signal`
- `macd_histogram`
- `macd_state`
- `vwap`
- `price_vs_vwap`
- `missing_fields`
- `source`

`macd_state` should be a bounded enum such as `bullish`, `bearish`, `neutral`, or `unknown`.

`price_vs_vwap` should be a bounded enum such as `above`, `below`, `near`, or `unknown`.

Missing values must be explicit. The strategy must not ask Claude to infer them.

### R2.7.3 Candidate Brief Integration

Candidate briefs may include a compact technical section when indicator data is available.

The technical section should include only:

- Current indicator values.
- Bounded interpretation labels.
- Data freshness.
- Missing-data flags.
- Short deterministic summary text if needed.

Candidate briefs must not include long raw OHLCV arrays.

### R2.7.4 Deterministic Filter Integration

Technical indicators may be used by deterministic target filters only after they are available as structured snapshots.

Initial R2.7 behavior should be conservative:

- Missing indicator data should be recorded as missing context or warning unless a later PRD makes it a hard rejection.
- Existing target filters for volume, run-up, conflicting news, invalidating events, and options liquidity must remain unchanged unless an implementation plan explicitly extends them.
- Indicator fields must not override peer scoring or earnings candidate detection.

### R2.7.5 Claude Prompt Boundary

Claude may receive:

- Indicator values.
- Interpretation labels.
- Missing-data flags.
- Data freshness metadata.
- A deterministic summary of technical context.

Claude must not receive:

- Raw candle arrays.
- Enough OHLCV history to calculate indicators in prompt.
- Instructions to compute RSI, MACD, VWAP, moving averages, or crossover state.
- Provider credentials or API payloads.

### R2.7.6 Optional Technical Agent Compatibility

If R2.6 Technical Agent is enabled, it must consume the same structured indicator snapshot.

The Technical Agent may answer:

> Does the precomputed technical setup support, weaken, or contradict the candidate?

It must not compute indicators or fetch market data.

### R2.7.7 Provider Failure Handling

If the provider cannot return or compute indicators:

- The snapshot must mark missing fields explicitly.
- The deterministic strategy decision must remain valid.
- Claude analysis may proceed with missing technical context only if the candidate is otherwise eligible.
- Claude must be told that indicator data is missing, not asked to reconstruct it.

### R2.7.8 Auditability

Every indicator snapshot used by a decision should preserve:

- Source name.
- As-of date or timestamp.
- Indicator values.
- Missing fields.
- Freshness status.

The system should be able to answer:

> Which precomputed technical indicators were available when this candidate was reviewed?

### R2.7.9 Cost And Latency Control

The system should prefer compact indicator records over raw time series in any prompt-bound payload.

R2.7 implementation should track or make measurable:

- Prompt payload size before and after indicator preprocessing.
- Whether Claude received raw candle data.
- Whether indicator preprocessing was skipped, completed, or failed.

## Non-Functional Requirements

### Determinism

When indicators are computed internally, calculations must be deterministic and covered by tests.

### Safety

Indicator values are advisory technical context. They must not place trades, size positions, or bypass deterministic rejection reasons.

### Modularity

Provider preprocessing should live outside `prescient.analyst`.

Claude-specific code must not own indicator math.

### Testability

Indicator snapshots must be fakeable in tests.

Tests must not require live provider credentials.

### Token Efficiency

Prompt payloads should include bounded indicator fields instead of raw market-data history.

## Out Of Scope

R2.7 does not include:

- Real external provider selection.
- Real provider API credentials.
- Broker integration.
- Order placement.
- Position sizing.
- New strategy types.
- Claude-based technical indicator calculation.
- Long-form technical chart generation.
- UI charts or dashboards.

## Decision Flow

```text
provider data available
  -> compute or fetch indicator snapshot
  -> attach compact snapshot to structured market context
  -> deterministic strategy pipeline
  -> candidate brief with compact technical section
  -> optional Claude analyst / Technical Agent reads snapshot only

provider data missing
  -> indicator snapshot records missing fields
  -> deterministic strategy pipeline continues with missing context
  -> Claude receives missing-data flags only if candidate-ready
```

## Acceptance Criteria

- RSI, MACD, and VWAP are represented as structured precomputed fields before Claude analysis.
- Claude prompts do not include raw OHLCV/candle arrays for indicator calculation.
- Claude prompts do not instruct Claude to calculate RSI, MACD, VWAP, moving averages, or crossover states.
- Missing indicator values are explicit and testable.
- Indicator snapshots include source and freshness metadata.
- Deterministic strategy output remains valid when indicator data is missing.
- Optional R2.6 Technical Agent, if enabled, consumes structured indicator snapshots only.
- Tests use fake provider snapshots and do not require live market-data credentials.
- `prescient.analyst` does not implement indicator math.

## Current Implementation Notes

The current codebase does not yet have a dedicated indicator snapshot model or provider preprocessing layer.

Existing relevant boundaries:

- `prescient.signal` owns deterministic strategy decisions and candidate brief construction.
- `prescient.analyst` validates Claude's structured analyst output.
- R2.6 already states that a future Technical Agent must not fetch live data or compute hidden indicators from raw price streams.

Known R2.7 implementation gaps:

- Add structured indicator snapshot models.
- Add provider/preprocessing interfaces for indicator snapshots.
- Extend candidate brief construction with compact technical context.
- Add tests proving raw candle data is not sent to Claude.

## Product FAQ

> Can Claude compute RSI from historical candles?

No. RSI must be computed by the provider layer or deterministic server-side preprocessing before Claude runs.

> Can Claude interpret an RSI value?

Yes. Claude may interpret a structured RSI value and label if the candidate is already eligible for Claude analysis.

> What happens when indicator data is missing?

The missing fields are recorded explicitly. Claude may receive the missing-data flags, but it must not reconstruct the indicators.

> Does R2.7 make technical indicators hard trade gates?

No. R2.7 defines preprocessing and data boundaries. Any hard technical rejection rules should be added by a later implementation plan or PRD.
