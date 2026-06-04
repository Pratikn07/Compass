# PRD: R2.3 Event-Driven Triggers With Local Classification

## Objective

Ensure `prescient` can react to important market and earnings events without turning Claude into a real-time event processor.

The system should ingest events from WebSocket, webhook, or bounded fast-poll sources, classify those events locally with deterministic code, ignore or journal low-value events, and escalate only important structured events to the existing hot/cold strategy pipeline and optional Claude analyst layer.

## Background

`prescient` is an earnings read-through strategy system. R2.1 established that Claude must not be in the execution hot path. R2.2 established that the normal workflow should be scheduled from earnings-calendar context, not continuous polling.

R2.3 adds a narrower capability:

```text
event source
  -> local event normalization
  -> deterministic event classification
  -> ignore / journal / trigger strategy refresh
  -> optional Claude only after deterministic gates pass
```

The purpose is not to build a high-frequency trading system. The purpose is to avoid missing important updates around earnings windows, such as a peer earnings result, guidance update, major news item, or abnormal target movement.

## Definitions

### Event-Driven Trigger

An event-driven trigger is a discrete external signal that may justify refreshing the strategy pipeline.

Examples:

- Earnings result became available.
- Guidance update was published.
- Major company news arrived.
- Price moved sharply after earnings.
- Volume or liquidity changed materially.
- Options liquidity changed near an earnings event.

### Local Classification

Local classification is deterministic code that decides whether an event is relevant and important enough to affect strategy processing.

Local classification must happen before Claude sees anything.

### Fast Poll

Fast poll means a short-lived, bounded polling loop used around a known event window when WebSocket or webhook delivery is unavailable.

Fast poll is not continuous polling. It must have an explicit scope, maximum duration, and maximum interval count.

### Important Event

An important event is an event that passes deterministic relevance and severity rules.

For MVP, an important event should be tied to:

- A ticker in the configured strategy universe.
- A target or peer inside an active earnings window.
- A field that can change candidate detection, peer scoring, target filters, rejection reasons, or candidate brief quality.

## Requirement

The system must classify events locally and only escalate important events.

Claude must not:

- Receive raw event streams.
- Classify every incoming event.
- Decide whether an event belongs to the configured universe.
- Decide whether a low-level event should trigger the strategy pipeline.
- Override deterministic event severity or rejection decisions.

Claude may be called only after the event has triggered or updated a structured candidate brief that passes the existing R2.1 gates.

## User Value

This requirement gives the user a system that is more responsive than a once-a-day scheduled job without becoming an always-on LLM scanner.

It provides:

- Faster reaction to earnings-related updates.
- Lower Claude cost and token usage.
- Less noise from irrelevant headlines or market ticks.
- Clear audit trail for why an event did or did not matter.
- Safer separation between event ingestion, deterministic strategy logic, and Claude judgment.

## Functional Requirements

### R2.3.1 Supported Event Sources

The system should support three event-source patterns:

- WebSocket event input for providers that stream market, news, or earnings updates.
- Webhook event input for providers that push structured updates.
- Bounded fast-poll input for known earnings windows when push delivery is unavailable.

The first implementation may use mocked or structured in-process events. Real provider integration is not required by this PRD.

### R2.3.2 Event Normalization

Incoming events must be normalized into a structured internal event shape before classification.

The normalized event should include:

- Event id or deterministic fingerprint.
- Source type.
- Event type.
- Ticker.
- Event time, if provided.
- Received time, if provided by caller.
- Raw source name.
- Structured payload summary.

The normalized event must not include credentials, account data, broker state, or unbounded raw documents.

### R2.3.3 Local Relevance Filter

The system must reject or ignore events that are not relevant to the configured strategy universe.

An event is not relevant when:

- The ticker is missing.
- The ticker is outside configured themes.
- The event type is unsupported.
- The event is unrelated to candidate detection, peer scoring, target filters, or strategy output.

Irrelevant events may be counted or journaled, but must not trigger Claude.

### R2.3.4 Local Importance Classification

Relevant events must be classified locally into deterministic importance levels.

Recommended levels:

- `ignored`
- `journal_only`
- `strategy_refresh`
- `candidate_review`

`strategy_refresh` means the system should refresh deterministic strategy evaluation.

`candidate_review` means the event is important enough that, after deterministic gates pass, a candidate may be eligible for Claude analyst review.

### R2.3.5 Trigger Strategy Refresh

An important event may trigger a bounded strategy refresh.

The refresh must:

- Use the existing deterministic strategy pipeline.
- Preserve R2.1 hot/cold behavior.
- Preserve R2.2 bounded execution behavior.
- Pass explicit structured inputs.
- Return or journal the event classification and resulting strategy decision.

The event system must not place trades or size positions.

### R2.3.6 Claude Escalation Gate

Only important events may lead to Claude, and only indirectly.

The allowed path is:

```text
event
  -> local classification
  -> strategy refresh
  -> candidate_ready_for_analyst
  -> Claude analyst
```

Rejected, ignored, journal-only, and no-trade outcomes must skip Claude.

Claude must receive only structured candidate or event-review briefs, never raw event streams.

### R2.3.7 Bounded Fast Polling

Fast polling is allowed only as a fallback around known event windows.

Fast polling must have:

- A configured ticker or event window.
- A maximum duration.
- A maximum number of attempts.
- A fixed or configured interval.
- A clear stop condition.

Fast polling must not become an indefinite loop.

### R2.3.8 Deduplication And Idempotency

Duplicate events must not repeatedly trigger the same strategy refresh.

The system should use a deterministic event fingerprint based on stable event fields.

If the same event is received twice:

- Classification should be identical.
- Journal records should identify it as the same event.
- Claude should not be called twice for the same event and unchanged candidate state.

### R2.3.9 Event Audit Trail

Every event that reaches classification must produce audit-safe output.

The event audit should include:

- Event fingerprint.
- Source type.
- Event type.
- Ticker.
- Theme, if known.
- Relevance result.
- Importance level.
- Classification reason.
- Whether strategy refresh was triggered.
- Whether Claude analysis was allowed.
- Resulting strategy status, if a refresh ran.

## Non-Functional Requirements

### Latency

Local classification should be lightweight and deterministic.

Claude latency must not affect event ingestion or local classification.

### Reliability

If an event source fails, the scheduled pipeline from R2.2 should still work.

If Claude fails, event classification and deterministic strategy decisions must remain intact.

### Determinism

Given the same normalized event, universe, settings, and strategy inputs, classification must produce the same serialized output.

### Cost Control

Most events should not reach Claude.

Claude calls should be reserved for events that produce or materially update a candidate-ready setup.

### Security

Events must not carry secrets into Claude prompts.

The system must not forward:

- API keys.
- Broker credentials.
- Account balances.
- Position state.
- Raw order instructions.
- Full unbounded transcripts or documents.

### Testability

The event trigger layer must be testable with mocked events.

Tests must not require:

- Real WebSocket connections.
- Real webhook servers.
- Real market data providers.
- Real Claude calls.
- Broker credentials.

## Decision Flow

```text
websocket / webhook / bounded fast poll
  -> normalize event
    -> check configured universe
      -> classify importance locally
        -> ignored or journal_only
          -> journal classification

websocket / webhook / bounded fast poll
  -> normalize event
    -> check configured universe
      -> classify importance locally
        -> strategy_refresh or candidate_review
          -> run bounded hot/cold runtime pipeline
            -> Claude only if candidate_ready_for_analyst
```

## Out Of Scope

This PRD does not require:

- Real WebSocket provider integration.
- Real webhook HTTP server.
- Real fast-poll provider client.
- Broker execution.
- Order placement.
- Position sizing.
- Risk gatekeeper implementation.
- Streaming every quote tick.
- Claude classification of raw event feeds.
- UI or dashboard changes.

Those belong to later data, broker, risk, or UI requirements.

## Acceptance Criteria

R2.3 is complete when:

- The app has a normalized event model for event-driven inputs.
- The app has deterministic local event classification.
- Events outside configured themes do not trigger strategy refresh or Claude.
- Low-importance events are ignored or journaled without Claude.
- Important events can trigger exactly one bounded strategy refresh.
- Candidate-ready strategy results may reach Claude through the existing R2.1 gate.
- Rejected and no-trade results never reach Claude.
- Duplicate events are identifiable by stable fingerprint.
- Bounded fast-poll behavior has an explicit maximum duration or attempt count.
- Tests prove raw event streams are not sent directly to Claude.
- Tests prove repeated classification of the same event is deterministic.

## Success Criteria

This requirement is successful when the product can answer:

> What happens when a market or earnings event arrives?

The answer must be:

> The event is normalized and classified locally. If it is irrelevant or low-value, it is ignored or journaled. If it is important, it can trigger one bounded strategy refresh. Claude only sees a structured candidate-ready brief after deterministic gates pass.

## Current Implementation Notes

The current code already supports the downstream pieces R2.3 should reuse:

- `prescient.signal` contains deterministic strategy evaluation.
- `prescient.runtime.run_hot_cold_strategy_pipeline(...)` preserves the R2.1 hot/cold boundary.
- `prescient.scheduler` provides bounded scheduled execution from R2.2.
- No event trigger package currently exists.

The next implementation milestone should add a small event-trigger layer that classifies mocked structured events locally and calls the existing runtime only for important events.
