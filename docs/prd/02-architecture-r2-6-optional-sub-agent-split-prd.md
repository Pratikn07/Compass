# PRD: R2.6 Optional Sub-Agent Split

## Objective

Define an optional sub-agent architecture for `prescient` that keeps analysis contexts small and responsibilities narrow.

The system may split cold-path analysis into specialized agents such as Sentiment Agent, Technical Agent, and Execution Agent. These agents must operate on structured inputs, produce structured outputs, and remain subordinate to deterministic code, risk rules, and broker adapters.

## Background

R2.5 defines Claude as analyst only. That means Claude may review a completed candidate brief but may not own scoring, filters, risk, or execution.

As `prescient` grows, a single analyst prompt may become too broad. It could mix news sentiment, technical indicators, options expression, risk constraints, and execution checks in one large context. R2.6 allows optional sub-agents to keep each review focused.

The purpose is context control, not autonomy.

```text
CandidateBrief
  -> optional focused sub-agents
    -> combined analyst packet
      -> final analyst recommendation
```

## Definitions

### Sub-Agent

A sub-agent is a narrow cold-path reviewer that receives structured input and returns structured output for one area of judgment.

Sub-agents do not own the deterministic strategy engine.

### Sentiment Agent

Reviews structured news, commentary summaries, and contradiction flags.

It answers:

> Does sentiment support, weaken, or contradict the candidate thesis?

### Technical Agent

Reviews structured technical and market indicators such as trend, volume, run-up, price reaction, and liquidity fields.

It answers:

> Does the target's technical setup support or weaken the candidate?

### Execution Agent

Reviews structured expression and execution readiness.

In MVP, this agent must not place trades. It can only identify whether the proposed expression is feasible, unsupported, missing data, or blocked by future risk/execution gates.

It answers:

> Is the proposed expression reviewable and operationally safe to pass forward?

## Requirement

Sub-agent split must be optional.

The app must work without sub-agents. If enabled, sub-agents must:

- Receive only structured data.
- Keep focused scope.
- Return strict JSON.
- Avoid broker credentials and account data.
- Avoid raw unbounded documents.
- Never override deterministic gates.
- Never place trades.
- Feed a combined analyst packet or final analyst review.

## User Value

This requirement gives the user:

- Smaller Claude contexts.
- Easier prompt testing.
- Clearer audit trails by analysis category.
- Better isolation of sentiment, technical, and execution concerns.
- A future path to enable or disable specific reviewers without changing the core strategy.

## Functional Requirements

### R2.6.1 Optional Orchestration

Sub-agents must be disabled by default for MVP unless explicitly enabled by caller or configuration.

When disabled, the R2.5 Claude analyst flow remains valid:

```text
CandidateBrief -> Claude analyst result
```

When enabled, the flow may become:

```text
CandidateBrief
  -> Sentiment Agent
  -> Technical Agent
  -> Execution Agent
  -> combined analyst packet
  -> final analyst result
```

### R2.6.2 Candidate-Ready Only

Sub-agents may run only when Claude analysis would already be allowed under R2.5:

- Strategy status is `candidate_ready_for_analyst`.
- Candidate brief exists.
- `claude_analysis_allowed` is `true`.

Rejected, no-trade, ignored, journal-only, and duplicate outcomes must skip sub-agents.

### R2.6.3 Structured Inputs Only

Each sub-agent must receive a bounded structured input.

Allowed inputs may include:

- Candidate brief fields.
- Peer scores.
- Supporting evidence.
- Contradictions.
- Structured sentiment summaries.
- Structured technical indicators.
- Structured expression/liquidity fields.

Disallowed inputs:

- Broker credentials.
- Account balances.
- Position state.
- Raw order instructions.
- Raw event streams.
- Full unbounded transcripts.
- Full unbounded news articles.

### R2.6.4 Structured Outputs Only

Each sub-agent must return strict JSON.

Recommended shared output fields:

- `agent_name`
- `status`
- `summary`
- `supports_thesis`
- `risks`
- `missing_context`
- `confidence`

Extra fields must be rejected.

### R2.6.5 Sentiment Agent Scope

The Sentiment Agent may:

- Review structured news or commentary summaries.
- Identify sentiment support.
- Identify contradictions.
- Identify missing sentiment context.

The Sentiment Agent must not:

- Score peers.
- Override target filters.
- Recommend position size.
- Place trades.

### R2.6.6 Technical Agent Scope

The Technical Agent may:

- Review structured price movement, volume, trend, run-up, and liquidity context.
- Identify technical support or weakness.
- Flag missing indicator context.

The Technical Agent must not:

- Fetch live data directly.
- Compute hidden indicators from raw price streams inside Claude.
- Override deterministic target filters.
- Place trades.

### R2.6.7 Execution Agent Scope

The Execution Agent may:

- Review deterministic recommended expression.
- Flag unsupported expression.
- Identify missing execution context.
- Confirm that future risk and broker gates still need to approve action.

The Execution Agent must not:

- Place or cancel orders.
- Choose position size.
- Override risk caps.
- Access broker credentials.
- Convert analyst judgment into an executable order.

### R2.6.8 Aggregation

Sub-agent outputs may be aggregated into a combined analyst packet.

The aggregator must:

- Preserve each sub-agent's output.
- Preserve failures and skipped states.
- Avoid hiding contradictions.
- Avoid converting sub-agent output into trade action.

The final analyst recommendation remains advisory.

### R2.6.9 Failure Handling

If one sub-agent fails:

- The failure must be recorded.
- Other sub-agent results may still be preserved.
- Final analyst result may be skipped, failed, or marked `needs_more_context`.
- Deterministic strategy decision must remain unchanged.

## Non-Functional Requirements

### Modularity

Each sub-agent must have a narrow prompt and schema.

No sub-agent should need the full system context.

### Safety

Sub-agent output must not bypass R2.1, R2.4, R2.5, risk rules, or broker adapters.

### Cost Control

Sub-agents should be optional because each one can add latency and token cost.

### Testability

Sub-agents must be fakeable in tests.

Tests must prove:

- Disabled mode does not call sub-agents.
- Non-candidate decisions skip sub-agents.
- Unsafe extra fields fail validation.
- Partial failure is represented safely.

## Decision Flow

```text
strategy decision
  -> not candidate_ready_for_analyst
    -> skip sub-agents

strategy decision
  -> candidate_ready_for_analyst
    -> optional Sentiment Agent
    -> optional Technical Agent
    -> optional Execution Agent
    -> aggregate structured outputs
    -> optional final Claude analyst review
```

## Out Of Scope

This PRD does not require:

- Real multi-agent runtime.
- Parallel execution.
- Real Anthropic API calls.
- Broker integration.
- Order placement.
- Position sizing.
- Risk gatekeeper implementation.
- Live technical indicator provider integration.
- Raw news scraping.
- UI changes.

## Acceptance Criteria

R2.6 is complete when:

- Sub-agent orchestration is optional.
- Sub-agents run only for candidate-ready decisions.
- Disabled mode preserves the existing R2.5 analyst flow.
- Sentiment, Technical, and Execution agent scopes are represented separately.
- Each sub-agent has strict structured input/output contracts.
- Failed or skipped sub-agent outputs are represented safely.
- Sub-agent output cannot include position size, order quantity, broker action, or risk override.
- Tests use fake clients and require no live Claude API key.
- Deterministic strategy output is unchanged by sub-agent results.

## Success Criteria

This requirement is successful when the product can answer:

> Why split Claude into sub-agents?

The answer must be:

> To keep each cold-path review narrow, structured, auditable, and optional. Sub-agents can improve analysis quality, but they do not own strategy logic, risk, or execution.

## Current Implementation Notes

The current code has a single Claude analyst layer:

- `prescient.analyst` reads `CandidateBrief`.
- `prescient.runtime` calls the analyst only after deterministic gates pass.
- No sub-agent package exists.

R2.6 should be implemented only after the R2.5 analyst-only schema is explicit, especially the `conviction_score` field and strict analyst result contract.
