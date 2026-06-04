# PRD: R2.1 Claude Must Not Be In The Execution Hot Path

## Objective

Ensure `prescient` uses Claude only as a cold-path analyst and never as a dependency for time-sensitive strategy execution.

The system must be able to detect earnings candidates, score peer signals, run target filters, build candidate briefs, reject bad setups, journal decisions, and trigger future execution workflows without waiting for Claude.

Claude may add reasoning quality, thesis review, contradiction checks, and conviction commentary, but Claude must never be required for the deterministic engine to complete its work.

## Background

The app is an earnings read-through strategy system. Its core strategy engine already follows a deterministic flow:

```text
configured universe
  -> upcoming earnings candidates
  -> reported peer collection
  -> peer scoring
  -> peer signal aggregation
  -> target filters
  -> candidate brief or rejection
```

Claude's role, defined in the core strategy PRD, is to read a structured candidate brief and return analyst-style judgment. That role must remain outside the latency-sensitive path because LLM calls can be slow, unavailable, rate-limited, or inconsistent in timing.

## Definitions

### Hot Path

The hot path is the deterministic, time-sensitive path that decides whether a market setup exists and whether it is eligible for downstream action.

Hot-path work includes:

- Loading configured strategy universe.
- Reading earnings/calendar inputs.
- Finding upcoming targets.
- Collecting already reported peers from structured input.
- Scoring peer results.
- Aggregating peer signal.
- Running target tradability filters.
- Producing `CANDIDATE_READY_FOR_ANALYST`, `REJECTED_WITH_REASON`, or `NO_TRADE`.
- Writing or returning journal-safe decision records.
- Triggering future alert or execution workflows.

### Cold Path

The cold path is slower, advisory, and non-blocking.

Cold-path work includes:

- Claude analysis of a completed `CandidateBrief`.
- Thesis summarization.
- Missing-context identification.
- Contradiction review.
- Conviction score.
- Suggested expression review limited to allowed expressions.
- Human-readable analyst notes.

## Requirement

Claude must not be in the execution hot path.

The hot path must not:

- Call Claude.
- Wait for Claude.
- Retry Claude.
- Require a Claude API key.
- Depend on Claude response content to create a deterministic decision.
- Allow Claude to modify peer scores, thresholds, target filters, or rejection reasons.
- Allow Claude to place trades, size positions, or issue broker commands.

The cold path may call Claude only after the deterministic engine has produced a candidate brief with `claude_analysis_allowed = true`.

## User Value

This requirement protects the product from slow or unreliable LLM calls during market-sensitive workflows.

It gives the user:

- Fast deterministic candidate detection.
- Reliable rejection reasons even when Claude is unavailable.
- A clear audit trail for every decision.
- Safer separation between analysis and future execution.
- Repeatable tests for the strategy engine.
- The option to disable Claude without disabling the strategy engine.

## Functional Requirements

### R2.1.1 Hot Path Independence

The core signal pipeline must complete without Claude.

Given the same structured input, the hot path must produce the same strategy decision whether Claude is configured or not.

### R2.1.2 Explicit Claude Gate

Claude may run only when all of these are true:

- Strategy decision status is `candidate_ready_for_analyst`.
- A valid `CandidateBrief` exists.
- `claude_analysis_allowed` is `true`.
- The candidate came from a configured theme.
- Deterministic filters passed.

Any rejected or no-trade decision must skip Claude.

### R2.1.3 Candidate Brief Boundary

Claude must receive only the structured candidate brief, not raw broker data, credentials, account balances, order state, or unbounded transcripts.

The candidate brief is the data contract between hot path and cold path.

### R2.1.4 Non-Blocking Analyst Failure

If Claude fails, times out, returns invalid JSON, or is unavailable:

- The deterministic strategy decision must remain unchanged.
- No rejection reason from the signal engine should be replaced by Claude output.
- The Claude result should be marked as failed or skipped.
- The system should still be able to journal the deterministic decision.

### R2.1.5 No Claude Authority Over Execution

Claude output may include:

- `recommendation`
- `thesis`
- `risks`
- `missing_context`
- `conviction_score`
- `suggested_expression`

Claude output must not include or control:

- Position size.
- Order quantity.
- Limit price.
- Broker action.
- Account allocation.
- Risk limit override.
- Universe override.
- Direct trade instruction.

Unsafe Claude output must be rejected by schema validation.

### R2.1.6 Deterministic Audit Trail

Every hot-path decision must be journal-safe before Claude runs.

The audit payload should include:

- Target.
- Theme.
- Strategy status.
- Rejection reasons and details, if rejected.
- Peer scores.
- Peer signal thresholds.
- Missing data counts.
- Target market data completeness.
- Recommended expression from deterministic filters.
- Whether Claude analysis was allowed.

### R2.1.7 Optional Claude

The system must support operation with Claude disabled.

When Claude is disabled:

- Candidate detection still runs.
- Peer scoring still runs.
- Target filters still run.
- Candidate briefs are still produced.
- Journal records are still written.
- Claude analysis status should be `skipped` or absent, depending on caller design.

## Non-Functional Requirements

### Latency

The hot path must not include LLM latency.

Any future SLA or runtime budget for candidate detection must measure the deterministic path separately from Claude analysis.

### Reliability

Claude outages, API errors, malformed output, rate limits, or missing credentials must not prevent deterministic decisions from being produced.

### Determinism

The hot path must remain deterministic and unit-testable.

Same input must produce the same serialized strategy decision.

### Security

Claude must not receive:

- Broker credentials.
- API keys.
- Account balances.
- Account identifiers.
- Raw order instructions.
- Personally sensitive user data.

### Testability

Claude integration must be fakeable in tests.

Tests must be able to prove whether Claude was called or skipped.

## Decision Flow

```text
scheduled or event trigger
  -> deterministic signal engine
    -> rejected/no_trade
      -> journal decision
      -> skip Claude

scheduled or event trigger
  -> deterministic signal engine
    -> candidate_ready_for_analyst
      -> journal deterministic decision
      -> optional cold-path Claude analysis
      -> journal analyst result
```

## Out Of Scope

This PRD does not require:

- Live broker integration.
- Order placement.
- Position sizing.
- Continuous polling.
- WebSocket event ingestion.
- Sub-agent orchestration.
- Real Claude API credentials.
- UI or dashboard changes.
- Backtesting.

Those are separate architecture or execution requirements.

## Acceptance Criteria

R2.1 is complete when:

- The deterministic signal engine can run without importing or calling the Claude analyst layer.
- Rejected and no-trade decisions always skip Claude.
- Candidate-ready decisions are the only decisions eligible for Claude analysis.
- Claude receives only `CandidateBrief` JSON.
- Claude failures do not change deterministic strategy decisions.
- Tests verify that non-candidate decisions do not call the Claude client.
- Tests verify that candidate-ready decisions may call a fake Claude client.
- Unsafe Claude fields such as `position_size`, `order_quantity`, or `broker_action` fail validation.
- The app can run with no Claude API key in deterministic mode.

## Success Criteria

This requirement is successful when the product can answer:

> What would the strategy engine do if Claude were completely unavailable?

The answer must be:

> It still finds candidates, rejects bad setups with reasons, builds candidate briefs for valid setups, and records deterministic decisions. Claude only adds optional analyst commentary afterward.

## Current Implementation Notes

The current code already supports the main boundary:

- `prescient.signal` contains deterministic strategy logic.
- `prescient.analyst` contains Claude prompt and response handling.
- `StrategyDecision.claude_analysis_allowed` marks whether Claude may run.
- Non-candidate decisions are skipped by the analyst layer.
- Claude output validation forbids unsafe extra fields.

Future runtime work should preserve this separation by making any scheduler, journal, alert, or execution adapter call the signal engine first and the analyst layer second.
