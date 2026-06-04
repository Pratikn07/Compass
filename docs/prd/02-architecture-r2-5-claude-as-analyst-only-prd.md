# PRD: R2.5 Claude As Analyst Only

## Ownership

Owner: Ours

Drafting support: GPT

## Objective

Ensure Claude acts only as an analyst layer after deterministic strategy gates pass.

Claude must read a structured `CandidateBrief` and return a machine-readable analyst opinion:

- Go, no-go, or needs-more-context recommendation.
- Thesis summary.
- Conviction score.
- Missing context.
- Contradictions.
- Suggested expression.

Claude must not detect candidates, score peers, run filters, size trades, place orders, override risk, or change deterministic strategy decisions.

## Background

`prescient` separates the strategy pipeline into a hot deterministic path and a cold analyst path.

R2.1 establishes that Claude must not be in the execution hot path. R2.2 establishes scheduled bounded runs. R2.3 establishes that event-driven triggers may refresh the strategy pipeline after local event classification. R2.4 establishes `prescient.signal.core.evaluate_core_strategy(...)` as the deterministic signal engine that owns candidate detection, peer scoring, target filters, rejections, and candidate brief construction.

R2.5 defines what Claude is allowed to do after R2.4 produces a candidate-ready brief.

```text
structured inputs
  -> deterministic signal engine
  -> StrategyDecision(candidate_ready_for_analyst)
  -> CandidateBrief
  -> Claude analyst
  -> structured analyst result
  -> journal / review / future risk layer
```

Rejected and no-trade decisions must skip Claude.

## Definitions

### Candidate Brief

A `CandidateBrief` is the structured handoff from deterministic code to Claude. It is created by `prescient.signal` only after earnings candidate detection, peer scoring, target filters, and strategy output construction pass.

The brief contains structured strategy evidence such as:

- Target ticker.
- Theme.
- Earnings date and report time.
- Strategy direction.
- Peer signal score.
- Positive peer ratio.
- Reported peers.
- Peer score details.
- Main deterministic thesis.
- Supporting evidence.
- Contradictions.
- Recommended expression.
- Strategy status.

Claude may read the brief. Claude must not receive raw broker data, account data, secrets, live API credentials, unbounded transcripts, raw event streams, or full unfiltered news feeds.

### Claude Analyst

The Claude analyst is the cold-path reasoning layer under `prescient.analyst`.

It may inspect the candidate brief for:

- Narrative quality.
- Obvious contradictions.
- Missing context.
- Whether the deterministic evidence supports proceeding.
- Whether the deterministic expression still makes sense.

It does not own strategy logic.

### Analyst Recommendation

The analyst recommendation must be one of:

- `go`: Claude agrees the candidate is analyst-ready based on the provided brief.
- `no_go`: Claude sees a material contradiction or insufficient support in the provided brief.
- `needs_more_context`: Claude cannot make a clean go/no-go judgment from the structured brief and names the missing context.

### Conviction Score

`conviction_score` is Claude's bounded analyst confidence in its recommendation, represented as an integer from `0` to `100`.

It is not a probability, risk budget, position size, order size, or authorization to trade.

### Suggested Expression

`suggested_expression` is Claude's non-binding expression suggestion.

Allowed values for MVP:

- `CALL_OPTION`
- `STOCK`
- `NONE`

Claude must not suggest unsupported expressions such as puts, spreads, baskets, shorts, leverage, notional values, quantities, or broker actions.

## Requirement

Claude must operate as analyst only.

It must accept only structured candidate briefs and return only a typed analyst result. Its output may inform human review or future downstream policy, but it must not mutate deterministic decisions or directly trigger broker execution.

## User Value

This gives the user the benefit of LLM judgment without letting LLM behavior control the strategy engine.

It provides:

- A repeatable code-owned strategy core.
- A bounded place for Claude to explain thesis quality.
- Clear audit records of what Claude saw and returned.
- Safer separation between signal generation and execution.
- Lower risk from malformed, delayed, unavailable, or overconfident model output.

## Functional Requirements

### R2.5.1 Structured Brief Input Only

Claude must receive only `CandidateBrief` JSON.

Claude must not receive:

- Raw broker payloads.
- Account balances.
- Portfolio holdings.
- Credentials or API keys.
- Order state.
- Raw event streams.
- Full unbounded transcripts.
- Free-form web/news dumps.
- Non-theme tickers not present in the candidate brief.

### R2.5.2 Candidate-Ready Gate

Claude may run only when all of these are true:

- `StrategyDecision.status == CANDIDATE_READY_FOR_ANALYST`
- `StrategyDecision.candidate` is present.
- `StrategyDecision.claude_analysis_allowed == true`

Rejected decisions, no-trade decisions, malformed decisions, and decisions without a candidate brief must return a skipped Claude result without calling the Claude client.

### R2.5.3 Analyst Output Schema

Claude output must be strict JSON with no extra fields.

Target R2.5 output schema:

```json
{
  "recommendation": "go | no_go | needs_more_context",
  "thesis": "short analyst thesis based only on the candidate brief",
  "reasoning": "short explanation of the recommendation",
  "conviction_score": 0,
  "missing_context": ["structured context still needed"],
  "contradictions": ["material contradiction found in the brief"],
  "suggested_expression": "CALL_OPTION | STOCK | NONE"
}
```

`conviction_score` must validate as an integer in the inclusive range `0..100`.

The schema must reject extra fields, including:

- `position_size`
- `order_quantity`
- `broker_action`
- `limit_price`
- `stop_loss`
- `take_profit`
- `account_allocation`
- `risk_override`
- `execute_trade`

### R2.5.4 Go / No-Go Semantics

Claude may return `go` only when the structured brief supports the deterministic thesis and Claude does not identify material contradictions.

Claude should return `no_go` when the brief contains a material contradiction, stale evidence, unsupported thesis, or mismatch between evidence and expression.

Claude should return `needs_more_context` when the brief is plausible but missing structured context required for a clean judgment.

When `recommendation` is `no_go` or `needs_more_context`, `suggested_expression` should be `NONE` unless there is a clear reason to suggest a non-execution review path. MVP should prefer `NONE` for these outcomes.

### R2.5.5 Thesis Summary

Claude must provide a concise `thesis` derived only from the candidate brief.

The thesis must:

- Name the target.
- Name the theme.
- Reflect the deterministic direction.
- Reference the peer read-through evidence at a high level.
- Avoid inventing missing financial facts.

The thesis must not include order instructions, position sizing, or unsupported tickers.

### R2.5.6 Conviction Score

Claude must return `conviction_score` as a bounded analyst confidence score.

Guidance:

- `0..39`: weak or no conviction.
- `40..69`: moderate conviction or meaningful uncertainty.
- `70..100`: high conviction based on a clean brief and low contradiction load.

The score must be explained by `reasoning`, `missing_context`, and `contradictions`.

The score must not be used as a position size or direct risk budget.

### R2.5.7 Suggested Expression

Claude may suggest only:

- `CALL_OPTION` when the brief supports the existing option expression.
- `STOCK` when the brief supports bullish exposure but option expression looks unsuitable from the structured brief.
- `NONE` when Claude recommends no-go or needs more context.

Claude cannot authorize a trade. A future risk or execution layer may choose to ignore Claude's suggested expression.

### R2.5.8 Prompt Contract

The prompt must explicitly tell Claude:

- Read only the candidate brief JSON.
- Return strict JSON only.
- Do not invent missing financial data.
- Do not override deterministic filters or risk limits.
- Do not choose position size.
- Do not place trades or issue broker instructions.
- Do not trade on a single headline.
- Do not recommend tickers outside the configured theme.
- Do not suggest unsupported output fields.
- Only suggest `CALL_OPTION`, `STOCK`, or `NONE`.

Prompt changes should be versioned or otherwise auditable.

### R2.5.9 Failure Handling

If Claude is disabled, missing, unavailable, rate-limited, times out, returns malformed JSON, or fails schema validation:

- The deterministic `StrategyDecision` must remain unchanged.
- The Claude result must be marked `skipped` or `failed`.
- Rejection reasons from the signal engine must not be replaced.
- No broker, risk, or execution action may be triggered from the failed response.
- The error should be journal-safe and should not expose secrets.

### R2.5.10 Auditability

The system must be able to journal:

- Whether Claude was enabled.
- Whether Claude was skipped, analyzed, or failed.
- The deterministic strategy status.
- The candidate target and theme.
- The validated Claude result, if present.
- The validation error message, if any.

The system should retain enough information to answer:

> What did deterministic code decide before Claude ran, and what did Claude add afterward?

### R2.5.11 Testability

Claude integration must be fakeable in tests.

Tests must be able to prove:

- Non-candidate decisions do not call the Claude client.
- Candidate-ready decisions call a fake Claude client only when enabled.
- Valid JSON produces an analyzed result.
- Invalid JSON produces a failed result.
- Unsafe extra fields are rejected.
- Invalid suggested expressions are rejected.
- Invalid conviction scores are rejected.
- Identical input and fake response produce identical serialized output.

## Non-Functional Requirements

### Safety

Claude output must be advisory only. It must not create, update, or submit orders.

### Reliability

The deterministic path must succeed even when Claude fails.

### Reproducibility

Given the same candidate brief and fake Claude response, the validated analyst result must serialize identically.

### Cost Control

Claude should be called only for candidate-ready setups. Rejected, no-trade, ignored, and low-value events must not consume Claude tokens.

### Security

Claude prompts must not include secrets, credentials, account details, or broker authorization data.

### Maintainability

Claude-specific code must stay outside `prescient.signal`.

The deterministic signal package must not import `prescient.analyst`.

## Out Of Scope

R2.5 does not include:

- Candidate detection.
- Peer scoring.
- Target filters.
- Risk sizing.
- Broker execution.
- Order placement.
- Account allocation.
- Position management.
- Live market-data adapters.
- Claude classification of raw event feeds.
- Claude parsing of raw transcripts.
- User interface work.

## Decision Flow

```text
evaluate_core_strategy(...)
  -> rejected/no_trade
      -> claude_analysis_allowed = false
      -> skip Claude

evaluate_core_strategy(...)
  -> candidate_ready_for_analyst
      -> CandidateBrief
      -> claude_analysis_allowed = true
      -> optional Claude analyst
      -> validate strict analyst JSON
      -> journal analyzed/skipped/failed result
```

## Acceptance Criteria

- `prescient.signal` remains Claude-free and does not import `prescient.analyst`.
- Claude receives only `CandidateBrief` JSON.
- Claude is skipped for rejected and no-trade decisions.
- Claude is optional and can be disabled without disabling the deterministic strategy engine.
- Claude output includes `recommendation`, `thesis`, `reasoning`, `conviction_score`, `missing_context`, `contradictions`, and `suggested_expression`.
- `recommendation` validates to `go`, `no_go`, or `needs_more_context`.
- `conviction_score` validates as an integer from `0` to `100`.
- `suggested_expression` validates to `CALL_OPTION`, `STOCK`, or `NONE`.
- Unsafe extra fields are rejected.
- Malformed JSON is rejected.
- Claude failures do not change deterministic strategy decisions.
- Tests use fake Claude clients and do not require a real Claude API key.
- Journal events preserve the hot-path decision separately from the cold-path Claude result.

## Current Implementation Notes

The current implementation already has the core boundary:

- `prescient.signal.core.evaluate_core_strategy(...)` owns deterministic strategy decisions.
- `StrategyDecision.claude_analysis_allowed` gates Claude eligibility.
- `prescient.analyst` contains prompt and response validation.
- `prescient.runtime.run_hot_cold_strategy_pipeline(...)` runs deterministic decisions first and optional Claude analysis second.
- `ClaudeAnalysisStatus` supports `analyzed`, `skipped`, and `failed`.
- Current validation rejects malformed JSON, unsafe extra fields, and unsupported suggested expressions.

Known R2.5 implementation gaps:

- Add a required `thesis` field to `ClaudeStrategyAnalysis`.
- Add a required bounded `conviction_score` field to `ClaudeStrategyAnalysis`.
- Update the Claude prompt to request these fields.
- Extend analyst and runtime tests for valid and invalid conviction scores.

## Open Questions

- Should `conviction_score` be displayed as a raw integer or mapped to low/medium/high in user-facing surfaces?
- Should future execution policy require both deterministic readiness and Claude `go`, or should Claude remain purely advisory for manual review?
- Should Claude output include a prompt version or analyst schema version in a wrapper object, or should versioning remain outside the model response?

## Product FAQ

> Can Claude decide which earnings candidates to analyze?

No. Candidate detection belongs to deterministic code.

> Can Claude reject a deterministic candidate?

Claude can return `no_go`, but this is an analyst result. It does not mutate the original deterministic `StrategyDecision`.

> Can Claude choose position size?

No. Position sizing and risk are out of scope for Claude.

> What happens if Claude is unavailable?

The deterministic decision remains valid and journaled. Claude analysis is marked skipped or failed.

> What should Claude see?

Only the structured `CandidateBrief` created by the deterministic signal engine.
