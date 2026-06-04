# PRD: R8.2 Push Notification on Every Executed Trade

## Ownership

Owner: Ours

Source note: Requirement from our operating checklist. Robinhood already provides native mobile notifications for activity in the Robinhood app, but `prescient` still needs a provider-neutral notification requirement so Alpaca, paper mode, propose-only transitions, future brokers, and journaled execution events are handled consistently.

## Objective

Notify the user every time `prescient` executes or records a broker-confirmed trade event.

R8.2 must make trade execution visible immediately without giving Claude, strategy logic, or notification delivery code any authority to place, modify, cancel, size, or approve trades.

## Background

Earlier milestones created the execution and audit foundations:

- R2 hot/cold architecture keeps Claude outside the execution hot path.
- R3 risk gate and sizing rules decide whether a trade may proceed.
- R5 broker adapters place or simulate orders through swappable broker interfaces.
- R6 journal records capture strategy, analyst, risk, sizing, and broker outcomes.
- R6.3 adds source citations and audit trails to decisions.

R8.2 is the alerting layer for broker-confirmed trade events. It should sit after execution confirmation and journal creation, not before risk checks or order placement.

## Definitions

### Push Notification

A short user-facing message delivered through a configured notification channel after a broker-confirmed execution event.

Initial channels may be implemented as local/mobile push, Telegram, Discord, email, or another adapter, but the PRD is channel-neutral. The product requirement is that an execution event creates a notification request; specific delivery adapters are implementation details.

### Executed Trade Event

For R8.2, an executed trade event is a broker-source-of-truth event that changes real or simulated order state after deterministic approval.

Included events:

- Order submitted or accepted by the broker.
- Order filled.
- Partial fill.
- Broker rejection after submit attempt.
- Order cancellation confirmed by broker.
- Paper/propose-only virtual execution result, when the system intentionally simulates the broker outcome.

Excluded events:

- Candidate found.
- Candidate rejected.
- Claude analyst output.
- Risk approval without order submission.
- Position sizing output without order submission.
- Strategy proposal in propose-only mode unless a virtual execution result is explicitly produced.
- Raw broker polling updates that do not change order state.

### Native Broker Notification

A broker-provided notification outside `prescient`, such as Robinhood mobile push notifications.

Native broker notifications may satisfy the user-visible delivery requirement for that broker, but `prescient` must still create an internal notification/audit record so the journal can show that the user was expected to be notified.

## User Value

R8.2 gives the user:

- Immediate awareness when an order is submitted, filled, rejected, or cancelled.
- A safety backstop so automated or semi-automated execution is never silent.
- A consistent notification experience across Alpaca, Robinhood, paper mode, and future brokers.
- A journal-safe audit trail proving that a notification was created or intentionally suppressed.
- Reduced duplicate noise when a broker like Robinhood already sends native mobile notifications.

## Functional Requirements

### R8.2.1 Notification Trigger

The system must create a notification request for every broker-confirmed execution event.

Required behavior:

- Trigger only after the broker adapter or execution wrapper returns a structured execution result.
- Trigger only after the execution event has enough structured metadata to identify what happened.
- Trigger for submitted, filled, partially filled, rejected, and cancelled order events.
- Trigger for paper/propose-only virtual execution results when those results are recorded as execution outcomes.
- Never trigger from candidate detection, Claude analysis, or risk approval alone.

### R8.2.2 Hot Path Boundary

Notification delivery must not block, delay, approve, or alter trade execution.

Required behavior:

- The risk and broker path remains authoritative.
- Notification code receives execution results after the broker decision exists.
- Notification failures must not mutate broker results, strategy decisions, risk decisions, sizing decisions, or journal records.
- Notification failures must be recorded as notification failures, not trade failures.
- Claude must not generate, approve, suppress, or rewrite execution notifications.

### R8.2.3 Notification Payload

Every trade notification must include compact, actionable information.

Required fields:

- Event type: submitted, filled, partial fill, rejected, cancelled, or virtual execution.
- Ticker.
- Trade expression: stock, call option, put option, or other supported expression.
- Side: buy or sell when available.
- Quantity or filled quantity when available.
- Limit price, average fill price, or execution price when available.
- Broker name.
- Execution mode: paper, propose-only, or live.
- Strategy status.
- Recommended expression from the candidate brief, when available.
- Run ID and decision ID.
- Order ID when safe to expose.
- Timestamp supplied by broker/runtime when available.

The message should be short enough to read on a lock screen. Detailed reasoning belongs in the journal, not in the push body.

### R8.2.4 Safety and Privacy

Notification payloads must be journal-safe and user-safe.

Notifications must not include:

- API keys.
- Authorization headers.
- Broker credentials.
- Account IDs or account numbers.
- Full account balance.
- Buying power.
- Raw provider payloads.
- Raw Claude prompts.
- Full thesis text if it makes the notification too long.
- Any instruction that implies the user must manually execute an additional trade.

Allowed compact fields:

- Ticker.
- Direction/side.
- Quantity.
- Price.
- Broker name.
- Execution mode.
- Order status.
- Order ID or short order reference, if already journal-safe.
- Link or reference to local journal record, when available.

### R8.2.5 Robinhood Native Notification Handling

Robinhood native mobile notifications are allowed to serve as the user-facing push channel for Robinhood executions.

Required behavior:

- The Robinhood adapter must still return structured execution results.
- `prescient` must still create an internal notification record for journal completeness.
- If broker-native notifications are configured as enabled, `prescient` may suppress duplicate external push delivery for Robinhood by default.
- Suppressed duplicate delivery must be explicit in the notification result, for example `delivery_status = "suppressed_native_broker_notification_expected"`.
- If the user disables native broker notification reliance, `prescient` should deliver through its configured notification channel instead.

R8.2 must not assume Robinhood native notification delivery is observable or guaranteed. It can only record that native delivery was expected based on configuration.

### R8.2.6 Delivery Results

Notification attempts must return structured results.

Expected result fields:

- `notification_id`
- `event_type`
- `target`
- `broker`
- `execution_mode`
- `order_id`
- `decision_id`
- `run_id`
- `delivery_channel`
- `delivery_status`
- `message`
- `error_type`, when failed
- `audit_trail`

Delivery statuses:

- `queued`
- `sent`
- `failed`
- `suppressed_native_broker_notification_expected`
- `skipped_no_channel_configured`

Notification IDs should be deterministic in tests when inputs are deterministic.

### R8.2.7 Retry and Failure Behavior

Notification failures must be safe and bounded.

Required behavior:

- No infinite retry loops.
- No unbounded polling.
- No retry that blocks execution.
- Failed delivery is journaled.
- Repeated identical execution events should not produce duplicate notifications unless the order state changed.
- Deduplication should use stable event keys such as broker, order ID, status, filled quantity, and execution mode.

Retries may be added later, but MVP should prefer a single deterministic attempt or queued result.

### R8.2.8 Journal Integration

Every notification request and delivery result must be journal-safe.

Required behavior:

- Link notification records to `run_id`, `decision_id`, and order ID when available.
- Include R6.3 audit trail/source citations or internal-rule citations.
- Preserve the original broker execution result unchanged.
- Record delivery failures without losing the trade event.
- Store enough information to answer: "Was I notified about this trade?"

### R8.2.9 Channel Abstraction

Notification delivery must be pluggable.

Required behavior:

- Define a notification adapter interface.
- Keep message construction separate from delivery.
- Allow a fake/in-memory adapter for tests.
- Do not hard-code Telegram, Discord, email, Apple Push, or mobile push into the execution path.
- Do not import broker adapters from notification adapters.

## Non-Functional Requirements

### Reliability

- Trade execution must remain successful even if notification delivery fails.
- Notification delivery must fail closed from an audit perspective: if the user could not be notified, the journal must say so.
- Duplicate suppression must be deterministic.

### Latency

- Notification creation should be fast and local.
- External delivery should not block broker execution.
- MVP may call a fake or synchronous adapter in tests, but production design should allow async/background dispatch later.

### Security

- No secrets in notification body, delivery result, logs, or journal payload.
- No account identifiers in notification body.
- No raw prompts or raw provider payloads.
- Notification adapters must receive only the bounded notification request, not full strategy/risk/broker objects unless explicitly sanitized first.

### Determinism

- Same execution event and settings should produce the same notification request and deterministic test ID.
- Tests must not depend on wall-clock time unless supplied explicitly.

## Proposed Architecture

R8.2 should introduce or extend `prescient.alerts` as a provider-neutral alerting layer.

Suggested components:

- `alerts.models`
  - Notification event/status/channel enums.
  - `TradeNotificationRequest`.
  - `TradeNotificationResult`.
  - Notification settings.

- `alerts.formatter`
  - Builds short user-facing message text from structured execution records.
  - Sanitizes payloads.

- `alerts.dispatcher`
  - Calls a fakeable notification adapter.
  - Handles native-broker suppression.
  - Returns structured delivery results.

- `alerts.interfaces`
  - `NotificationAdapter` protocol.
  - Fake/in-memory adapter for tests.

- `runtime` or `broker.execution`
  - Calls alert dispatcher after broker execution result is produced and journaled.
  - Does not call alerts before risk or broker confirmation.

## Data Flow

```text
StrategyDecision
  -> RiskGateDecision
  -> PositionSizingDecision
  -> BrokerAdapter / ExecutionGuard
  -> OrderExecutionResult
  -> Journal record
  -> TradeNotificationRequest
  -> NotificationAdapter
  -> TradeNotificationResult
  -> Journal record
```

Claude is not in this flow.

## Acceptance Criteria

- Every broker-confirmed submitted, filled, partial-fill, rejected, or cancelled execution event creates a notification request.
- Notification requests are built only after broker execution results exist.
- Robinhood native notification reliance can suppress duplicate external push while still producing an internal notification result.
- Notification failure does not alter strategy, risk, sizing, broker, or journal decisions.
- Notification payloads contain no secrets, account IDs, credentials, raw prompts, or raw provider payloads.
- Duplicate execution events do not produce duplicate notifications unless order state changes.
- Notification results are linked to `run_id`, `decision_id`, and order ID when available.
- Tests use fake notification adapters only.
- No live push provider, broker, or network call is required for MVP tests.

## Test Requirements

Add tests covering:

- Submitted order result creates a notification request.
- Filled order result creates a notification request.
- Broker rejection creates a notification request.
- Cancelled order creates a notification request.
- Propose-only virtual execution result creates a notification request only when it is recorded as a virtual execution result.
- Candidate-ready strategy decision without broker result does not notify.
- Risk-approved but unsubmitted order does not notify.
- Claude analyst output does not notify.
- Robinhood native notification enabled suppresses duplicate external delivery while recording notification result.
- Robinhood native notification disabled uses configured notification adapter.
- Missing notification channel returns `skipped_no_channel_configured`.
- Adapter failure returns `failed` without mutating execution result.
- Duplicate event key suppresses duplicate notification.
- Notification payload contains no API keys, auth headers, account IDs, raw prompts, buying power, or raw provider payloads.
- Same input twice produces equal serialized notification request/result.

## Out of Scope

- Candidate/setup alerts.
- Daily summary alerts.
- P&L outcome alerts.
- Mobile app implementation.
- Real APNs/FCM integration.
- Telegram/Discord/email adapter implementation unless chosen in a later plan.
- User notification preferences UI.
- Trade approval by notification response.
- Manual "confirm trade" workflow.
- Claude-generated notification text.
- Broker polling or WebSocket monitoring.

## Assumptions

- R8.2 follows R5 broker execution and R6 journal records.
- MVP can use fake/in-memory notification adapters.
- Robinhood native notification behavior is not controlled or verified by `prescient`; it is only represented as configured expected behavior.
- Notification dispatch is advisory/user-awareness only and cannot approve, block, resize, cancel, or place trades.
- A future R8 implementation may add channel-specific adapters, but the PRD should keep the first milestone provider-neutral.
