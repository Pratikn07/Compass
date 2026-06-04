# PRD: R8.1 Telegram, Discord, and Email Alerts on Setups and Every Trade

## Ownership

Owner: Ours

Source note: Requirement from GPT and Gemini: add outbound alerts for actionable setups and every trade lifecycle event through Telegram, Discord, and email.

## Objective

Add a read-only outbound alerting layer under `prescient.alerts` that can notify configured channels when Prescient detects a setup, proposes a trade, submits an order, receives broker lifecycle updates, exits a trade, or records a final outcome.

R8.1 answers:

```text
How does Prescient notify the user, with journal-safe context, whenever a setup appears or a trade lifecycle event occurs?
```

Alerts are notification infrastructure only. R8.1 must not make strategy decisions, change risk gates, place trades, modify broker state, call LLMs for trade judgment, or mutate the configured strategy universe.

## Background

Earlier milestones define the facts that alerts should report:

- R2.2 creates bounded scheduled pipeline runs.
- R5.x defines broker adapters, execution modes, broker preflight, and broker lifecycle facts.
- R6.1 records every decision and trade lifecycle event in an append-only journal.
- R6.3 preserves source citations and audit-safe provenance.
- R6.4 adds durable Supabase storage behind a storage boundary.

R8.1 turns those normalized runtime and journal events into operator-facing notifications. The alert layer should make it easy to know:

- A new candidate setup was detected.
- A setup was blocked by risk, liquidity, preflight, broker, or daily halt.
- A trade was proposed, submitted, filled, cancelled, rejected, exited, or resolved.
- The final realized or unresolved outcome was recorded.

Sources:

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Discord Webhook Resource](https://docs.discord.com/developers/resources/webhook)
- [Amazon SES SendEmail API](https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_SendEmail.html)
- [Twilio SendGrid Mail Send API](https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send)

## Functional Requirements

### R8.1.1 Alert Boundary

Alert code must live behind a dedicated boundary such as `prescient.alerts`.

The following packages must not import Telegram, Discord, SMTP, SES, SendGrid, or other alert-provider clients:

- `prescient.signal`
- `prescient.risk`
- `prescient.broker`
- `prescient.data`
- `prescient.analyst`

Those packages may produce normalized decisions, broker facts, and journal records. Runtime, scheduler, journal/storage readers, or a dedicated alert dispatcher owns notification delivery.

### R8.1.2 Provider-Neutral Alert Interface

The alert layer must expose a provider-neutral interface for:

- Building alert events from normalized runtime/journal records.
- Formatting channel-specific messages.
- Sending one alert to one or more configured channels.
- Returning structured delivery results and errors.
- Deduplicating alerts by stable alert ID.
- Supporting dry-run/test mode without sending external messages.

Provider adapters:

- Telegram adapter: uses Bot API credentials and chat IDs configured server-side.
- Discord adapter: uses configured incoming webhook URLs.
- Email adapter: supports a provider-neutral email interface with SMTP, SES, or SendGrid implementation choices in later implementation.

Missing provider credentials must return structured errors and must not block other configured channels.

### R8.1.3 Alert Event Model

Normalize outbound alerts into internal models before channel formatting.

Minimum model concepts:

- `AlertEvent`: stable alert ID, event type, severity, run ID, decision ID, journal record ID, target, theme, strategy type, execution mode, title, summary, detail fields, source citations, created_at.
- `AlertRecipient`: channel type, destination label, provider, address/chat/webhook reference, enabled flag.
- `AlertDeliveryResult`: alert ID, provider, channel type, destination label, status, sent_at, provider message ID when available, structured errors.
- `AlertError`: provider, error type, message, retryable flag, source, redacted provider details.

Tickers and themes must normalize to uppercase. Alert IDs must be deterministic from event type plus the source journal/runtime record identity so reruns do not duplicate notifications.

### R8.1.4 Alert Types

R8.1 must support these alert event types:

- `SETUP_DETECTED`: candidate-ready deterministic setup.
- `SETUP_BLOCKED`: setup rejected or blocked by deterministic, analyst, risk, daily halt, liquidity, broker preflight, or broker-source-of-truth checks.
- `TRADE_PROPOSED`: trade proposal created in propose-only or paper/live workflow.
- `ORDER_SUBMITTED`: order submitted to broker.
- `ORDER_FILLED`: broker fill observed.
- `ORDER_CANCELLED`: order cancelled.
- `ORDER_REJECTED`: broker or preflight rejection.
- `TRADE_EXITED`: exit order or close event recorded.
- `TRADE_OUTCOME_RECORDED`: final or unresolved outcome recorded, including realized P&L when known.
- `DAILY_HALT_ACTIVE`: daily loss/trade-count halt activated.

Every trade lifecycle record from proposal through outcome must be eligible for an alert. Setup alerts must be emitted for actionable setups and for blocked setups when the block materially explains why no trade happened.

### R8.1.5 Message Content

Alert messages must be concise, journal-safe, and source-linked when citations are available.

Required fields for setup alerts:

- target ticker
- theme
- strategy status
- earnings date or relevant event date
- setup direction/expression when available
- thesis or rejection/blocking reason
- peer/read-through summary when available
- execution mode
- run ID and decision ID

Required fields for trade alerts:

- target ticker
- theme
- event type
- execution mode
- order ID when available
- side, symbol, quantity, order type, limit/filled price when available
- broker status
- realized P&L and fees when outcome is known
- run ID, decision ID, and journal record ID

Messages must not include:

- API keys, bot tokens, webhook URLs, SMTP credentials, bearer tokens, or request headers.
- Raw provider payloads, raw broker account IDs, unrestricted stack traces, or raw prompts.
- Full transcripts or long unbounded analyst text.

### R8.1.6 Channel Formatting

Each channel may format the same normalized alert differently, but content semantics must stay consistent.

Telegram:

- Send compact text messages through Bot API `sendMessage`.
- Support optional parse mode only when escaping is deterministic and tested.
- Support configured chat IDs for direct or group delivery.

Discord:

- Send messages through incoming webhooks.
- Support plain content for MVP; embeds are optional if deterministic and tested.
- Must never log or expose webhook URLs.

Email:

- Send transactional email through the configured email provider.
- Subject must include alert type, ticker, and execution mode.
- Body may be plain text for MVP; HTML is optional if generated from the same normalized fields.

### R8.1.7 Routing and Preferences

Alert routing must be configurable without changing strategy code.

Configuration must support:

- Enable/disable alerting globally.
- Enable/disable individual channels.
- Configure destinations per channel.
- Route by event type and severity.
- Route paper/live/propose-only events separately.
- Suppress low-severity blocked setup alerts if configured.
- Always alert on live order submitted, fill, rejection, exit, and outcome events.

Default posture:

- Alerts disabled unless explicitly configured.
- Test/dry-run mode available.
- Live trade lifecycle alerts should be treated as high priority when live execution exists.

### R8.1.8 Delivery, Idempotency, and Retry

Alert delivery must be idempotent at the alert-event level.

Requirements:

- Build deterministic `alert_id` values from source event identity.
- Do not send duplicate alerts for the same alert ID and destination within one run.
- If durable storage is available, persist alert delivery attempts in a future-compatible way.
- Return structured retryable errors for transient provider failures.
- Do not retry indefinitely inside the hot path.
- Do not block deterministic strategy evaluation when alerts fail.

Fatal vs non-fatal behavior:

- In propose-only and paper mode, alert delivery failures are non-fatal.
- In live mode, failure to alert on order submission/fill/rejection should be recorded as an operational error, but must not change broker facts or silently retry orders.

### R8.1.9 Provider Error Handling

Return structured provider errors for:

- Missing Telegram bot token or chat ID.
- Missing Discord webhook URL.
- Missing email provider configuration.
- Unauthorized or forbidden provider access.
- Provider rate limiting.
- Timeout.
- Network unavailable.
- Malformed provider response.
- Empty provider response.
- Recipient/channel unavailable.
- Message too long or invalid formatting.

Errors must be journal-safe and must not include secrets, raw headers, webhook URLs, bot tokens, email API keys, or full raw payloads.

### R8.1.10 Observability and Storage

Alert delivery attempts should be recordable as journal-safe operational records.

Minimum fields:

- alert ID
- event type
- provider
- channel type
- destination label
- delivery status
- provider message ID when safe and available
- retryable flag
- redacted error type/message
- created_at/sent_at
- run ID, decision ID, and source journal record ID when available

R8.1 may write alert delivery records through the storage/journal boundary, but it must not require live Supabase to run tests.

## Acceptance Criteria and Test Scenarios

- A PRD exists for R8.1 Telegram, Discord, and email alerts with explicit alert boundaries, event types, routing, formatting, idempotency, and failure handling.
- Alert event models normalize ticker/theme casing and preserve run/decision/journal provenance.
- Setup detected and setup blocked records can be converted into `SETUP_DETECTED` and `SETUP_BLOCKED` alerts.
- Trade proposal, order submitted, fill, cancellation, rejection, exit, and outcome records can be converted into trade lifecycle alerts.
- Telegram, Discord, and email adapters send only normalized message fields and never receive raw strategy/provider/broker payloads.
- Missing credentials for one channel return structured errors without blocking other configured channels.
- Provider 401/403/429/timeout/malformed response/message-too-long cases return redacted structured errors.
- Alert IDs are deterministic and prevent duplicate sends per destination.
- Dry-run mode builds messages and delivery results without external network calls.
- Existing signal, risk, broker, data, analyst, runtime, scheduler, journal, and storage tests continue to pass unchanged unless explicitly extended for alert dispatch.
- Boundary tests prove deterministic layers do not import Telegram, Discord, email, SMTP, SES, SendGrid, or alert-provider adapter code.

## Non-Goals

- No broker integration changes.
- No order placement.
- No strategy scoring changes.
- No Claude, GPT, or Gemini calls for trade decisions or alert routing.
- No inbound Telegram, Discord, or email command handling.
- No chat bot conversation interface.
- No dashboard UI.
- No push notifications, SMS, Slack, PagerDuty, or mobile app notifications in R8.1.
- No rich HTML email templates unless a later design milestone requires them.
- No alert-based auto-approval or manual trading command flow.

## Assumptions and Defaults

- Alerting is outbound-only.
- Runtime, scheduler, journal, or storage readers are the source of alert events.
- JSONL/local tests must run without live Telegram, Discord, email, or Supabase credentials.
- Provider credentials are server-side environment variables only.
- Telegram and Discord are fast notification channels; email is the durable fallback channel.
- GPT and Gemini are treated as source-note contributors for this PRD, not runtime alerting dependencies.
