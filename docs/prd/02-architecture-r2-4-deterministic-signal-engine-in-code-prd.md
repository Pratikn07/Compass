# PRD: R2.4 Deterministic Signal Engine In Code

## Objective

Ensure `prescient` expresses the core earnings read-through strategy as deterministic Python code, not as LLM judgment.

The system must detect earnings candidates, score peer results, run target and technical filters, and build candidate briefs using typed inputs and repeatable rules.

The public deterministic hot-path entrypoint is:

```python
prescient.signal.core.evaluate_core_strategy(...)
```

## Background

`prescient` is an earnings read-through strategy system. The product looks for upcoming earnings targets in configured themes, checks whether same-theme peers have already reported strong or weak results, runs target tradability filters, and produces either a candidate brief or a structured rejection.

R2.1 establishes that Claude must not be in the execution hot path. R2.2 establishes that scheduled runs invoke the strategy pipeline as bounded jobs. R2.3 establishes that event-driven triggers may refresh the strategy pipeline after local event classification.

R2.4 defines the shared deterministic signal engine that scheduled runs and future event triggers must reuse.

```text
configured universe
  -> upcoming earnings candidates
  -> reported same-theme peers
  -> peer result scoring
  -> peer signal aggregation
  -> target / technical filters
  -> candidate brief or structured rejection
```

Future R2.3 event triggers may call the signal/runtime pipeline, but they must not duplicate peer scoring, target filtering, rejection mapping, or candidate brief logic.

## Definitions

### Deterministic Signal Engine

The deterministic signal engine is the code-owned hot path under `src/prescient/signal/`.

It owns:

- Strategy universe checks.
- Earnings candidate detection.
- Same-theme peer collection.
- Peer beat and miss detection.
- Peer signal aggregation.
- Target and technical filters.
- Candidate brief construction.
- Structured rejection reasons and audit payloads.

### Technical Filters

For R2.4, technical filters are implemented through the target filter layer. This includes average volume, extreme illiquidity, pre-earnings run-up, conflicting news, invalidating events, and options liquidity checks.

The canonical module is:

```text
src/prescient/signal/target_filters.py
```

R2.4 must not introduce a second duplicate `technical_filter.py` implementation.

### Candidate Brief

A candidate brief is the structured handoff from the deterministic signal engine to the cold-path Claude analyst.

It must be JSON-serializable and contain only structured strategy evidence.

## Requirement

The signal engine must implement peer-beat detection, technical filters, rejection logic, and candidate brief creation in deterministic code.

The same structured input must always produce the same serialized output.

The signal engine must not:

- Call Claude.
- Import the Claude analyst layer.
- Call runtime orchestration.
- Call scheduler orchestration.
- Call broker APIs.
- Place trades.
- Size positions.
- Fetch live market data directly.
- Infer missing financial data.
- Depend on system time unless `current_date` is explicitly passed.
- Run sleeps, polling loops, or event loops.

## User Value

This requirement gives the user a reliable strategy core that can be tested, scheduled, replayed, journaled, and later triggered by events without relying on LLM behavior.

It provides:

- Repeatable strategy output.
- Clear peer-beat logic.
- Clear target-filter rejection reasons.
- Claude-free operation.
- A stable hot-path API for scheduled and event-driven flows.
- A safer boundary before any future broker or risk layer.

## Functional Requirements

### R2.4.1 Public Hot-Path Entrypoint

The deterministic signal engine must expose one primary orchestration function:

```python
evaluate_core_strategy(
    *,
    universe,
    upcoming_events,
    peer_results,
    target_market_data,
    options_chains,
    current_date,
    settings,
    preferred_expression,
) -> list[StrategyDecision]
```

Inputs must be structured snapshots supplied by the caller.

The function must not fetch, poll, or infer missing external state.

### R2.4.2 Strategy Universe Boundary

The engine must only evaluate tickers from configured strategy themes.

Targets outside the configured universe must be rejected with `THEME_NOT_CONFIGURED`.

A ticker may belong to more than one theme, but each decision must preserve the theme that produced it.

### R2.4.3 Earnings Candidate Detection

The engine must identify upcoming target earnings from structured calendar input.

A target may proceed only if:

- It has an earnings date.
- The earnings date is inside the configured window.
- It belongs to at least one configured theme.
- Enough same-theme peers have already reported recently.

Default thresholds:

```yaml
earnings_window_days: 1
peer_result_window_days: 21
min_reported_peers: 3
```

### R2.4.4 Peer-Beat Detection

The engine must score peer results with deterministic rules:

```text
+1 EPS beat
+1 revenue beat
+1 positive guidance
+1 positive price reaction
+1 positive theme-driver signal

-1 EPS miss
-1 revenue miss
-1 negative guidance
-1 negative price reaction
-1 negative theme-driver signal
```

Missing structured inputs must be recorded as missing factors, not guessed.

### R2.4.5 Peer Signal Aggregation

The engine must aggregate peer scores into:

- Average peer score.
- Positive peer count.
- Negative peer count.
- Positive peer ratio.
- Missing-data count.
- Pass/fail threshold result.

Default pass thresholds:

```yaml
min_positive_peer_ratio: 0.67
min_average_peer_score: 2.0
```

If thresholds fail, reject with `PEER_SIGNAL_TOO_WEAK`.

If all peer data is missing, reject with `MISSING_DATA`.

### R2.4.6 Target / Technical Filters

Before producing a candidate brief, the engine must run deterministic target filters.

Required checks:

- Average daily volume meets threshold.
- Target is not extremely illiquid.
- Pre-earnings run-up does not exceed threshold.
- Conflicting news flag is false.
- Invalidating event flag is false.
- Options liquidity passes when preferred expression is `CALL_OPTION`.

If options fail and stock fallback is enabled, the engine may recommend `STOCK`.

If options fail and fallback is disabled, reject with `OPTIONS_TOO_ILLIQUID`.

### R2.4.7 Candidate Brief Construction

When all deterministic filters pass, the engine must produce a JSON-serializable `CandidateBrief` containing:

- Target ticker.
- Theme.
- Earnings date and report time.
- Direction.
- Peer signal score.
- Positive peer ratio.
- Reported peers.
- Peer scores.
- Main thesis.
- Supporting evidence.
- Contradictions.
- Recommended expression.
- Strategy status.

Candidate brief text must be generated from structured inputs only.

### R2.4.8 Rejection Output

Every rejected decision must include:

- Status.
- Rejection reasons.
- Rejection details.
- Rejection stage.
- Audit-safe structured data.

Rejected decisions must set `claude_analysis_allowed = false`.

Candidate-ready decisions must set `claude_analysis_allowed = true`.

### R2.4.9 Reuse By Scheduled And Event-Driven Flows

Scheduled runs from R2.2 and future event-driven triggers from R2.3 must call the existing signal/runtime pipeline.

They must not reimplement:

- Peer scoring.
- Peer aggregation.
- Target filters.
- Candidate brief construction.
- Rejection reason mapping.

## Non-Functional Requirements

### Determinism

Same input must produce the same serialized strategy decisions.

### Testability

The signal engine must be testable with mocked data only.

Tests must not require:

- Broker credentials.
- Claude API keys.
- Network access.
- Real WebSocket or webhook sources.
- A scheduler or cron daemon.

### Safety

The signal engine must never execute trades or produce position sizes.

### Auditability

Every decision must include enough structured information for later journaling.

### Simplicity

R2.4 should harden the existing signal engine rather than introduce a parallel strategy path.

## Decision Flow

```text
structured inputs
  -> evaluate_core_strategy
    -> detect earnings candidates
      -> score reported peers
        -> aggregate peer signal
          -> run target / technical filters
            -> candidate_ready_for_analyst + CandidateBrief
            -> rejected_with_reason + audit details
```

## Out Of Scope

R2.4 does not include:

- WebSocket implementation.
- Webhook implementation.
- Fast-poll implementation.
- Claude analysis changes.
- Broker integration.
- Risk sizing.
- Order placement.
- Live data adapters.
- Alert delivery.
- New scheduler behavior.
- UI or dashboard work.

Those belong to R2.1, R2.2, R2.3, or later broker/risk/data requirements.

## Acceptance Criteria

R2.4 is complete when:

- `evaluate_core_strategy` is documented as the deterministic hot-path entrypoint.
- Configured-universe target detection works.
- Same-theme peer collection works.
- Peer beat/miss scoring is deterministic.
- Peer aggregation produces pass/fail signal metrics.
- Target filters reject weak or unsafe setups.
- Candidate briefs are produced only after deterministic filters pass.
- Rejected decisions include clear structured reasons and details.
- Rejected decisions block Claude analysis.
- Candidate-ready decisions allow Claude analysis.
- `prescient.signal` does not import Claude, runtime, scheduler, broker, or network-client layers.
- `prescient.signal` does not use hidden clock reads, sleeps, or polling loops.
- Same input produces identical serialized output.

## Success Criteria

This requirement is successful when the product can answer:

> Where does the trading setup get decided?

The answer must be:

> In deterministic code under `prescient.signal`, through `evaluate_core_strategy`. Scheduled and event-driven flows may trigger that engine, and Claude may analyze completed candidate briefs afterward, but neither the scheduler, event layer, nor Claude owns peer scoring, filters, or candidate creation.

## Current Implementation Notes

The current code already contains the main R2.4 pieces:

- `prescient.signal.core.evaluate_core_strategy`
- `prescient.signal.candidate`
- `prescient.signal.peer_scoring`
- `prescient.signal.target_filters`
- `prescient.signal.strategy_output`
- `prescient.signal.rejections`
- `CandidateBrief`
- `StrategyDecision`
- Core acceptance tests

The implementation milestone for R2.4 should preserve this public contract and add regression tests that prevent future scheduler, event-trigger, or Claude work from moving strategy decisions out of the deterministic signal engine.
