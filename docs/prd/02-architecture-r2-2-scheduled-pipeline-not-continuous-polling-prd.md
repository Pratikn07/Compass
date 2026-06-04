# PRD: R2.2 Scheduled Pipeline, Not Continuous Polling

## Objective

Ensure `prescient` runs as a scheduled earnings-calendar-driven pipeline, not as a continuous market polling loop.

The system should wake when there is a reason to evaluate earnings setups, run the deterministic hot path, optionally run cold-path Claude analysis for qualified candidates, journal the results, and then stop until the next scheduled wake.

## Background

`prescient` is an earnings read-through strategy system. Its core signal engine evaluates upcoming target earnings against already reported peer earnings. This means the natural trigger is the earnings calendar, not every market tick.

R2.1 already establishes the two-brain boundary:

```text
deterministic hot path
  -> journal decision
  -> optional Claude cold path
```

R2.2 defines how that pipeline should be invoked over time.

The app should not behave like a high-frequency trading system or a constantly running quote scanner. It should run at deliberate times based on earnings calendar windows and configured strategy needs.

## Definitions

### Scheduled Pipeline

A scheduled pipeline is a bounded job that starts, loads required inputs, evaluates candidates, writes outputs, and exits.

It may be triggered by:

- A calendar schedule.
- A known earnings-calendar wake time.
- A manual run command.
- A catch-up run after a missed schedule.

### Continuous Polling

Continuous polling is a loop that repeatedly wakes every few seconds or minutes to ask whether anything changed.

For R2.2, continuous polling is out of scope.

The system must not run an always-on loop that repeatedly scans earnings, quotes, news, or broker state.

### Earnings Calendar Wake

An earnings calendar wake is a planned time when the system runs because one or more configured-universe tickers report earnings soon or because peers may have reported recently enough to affect an upcoming target.

## Requirement

The pipeline must be scheduled from earnings calendar context, not driven by continuous polling.

The scheduler's job is to answer:

> When should the strategy engine run next based on configured themes and upcoming earnings dates?

The strategy engine's job remains:

> Given structured inputs, what deterministic strategy decisions should be produced?

The scheduler must not change strategy scores, rejection reasons, target filters, or Claude gating.

## User Value

This requirement keeps the product practical and reliable for an earnings strategy.

It gives the user:

- Lower infrastructure cost than a continuously running scanner.
- Fewer duplicate decisions.
- Easier debugging because each run has clear inputs and outputs.
- Clear run history around earnings events.
- Lower risk of accidentally building low-latency trading behavior before the strategy is ready.
- A natural place to later add alerts, dashboards, and manual review.

## Functional Requirements

### R2.2.1 Calendar-Derived Wakeups

The system must determine scheduled wakeups from configured themes and earnings calendar data.

A ticker should matter to the scheduler only if it belongs to the configured strategy universe.

Wakeups should be based on:

- Upcoming target earnings inside the configured earnings window.
- Recent peer earnings inside the configured peer-result window.
- Manual operator request.

### R2.2.2 Bounded Pipeline Runs

Each scheduled run must be bounded.

A run must:

- Start from explicit inputs.
- Execute the hot/cold runtime pipeline once.
- Write or return journal-safe records.
- Finish without entering a long-running polling loop.

### R2.2.3 No Continuous Polling Loop

The system must not:

- Poll quotes continuously.
- Poll earnings calendars continuously.
- Poll news continuously.
- Poll broker/account state continuously.
- Keep Claude warm in a loop.
- Sleep and rescan indefinitely inside the strategy process.

Any later fast event handling belongs to R2.3, not R2.2.

### R2.2.4 Configurable Run Windows

The scheduler must support configuration for when runs occur around earnings events.

The initial product expectation is:

- Run before upcoming earnings candidates are due.
- Run after peer earnings results are available.
- Allow manual re-run for a specific date.

Exact clock times can be implementation configuration, but the PRD requires the schedule to be explicit and auditable.

### R2.2.5 Idempotent Run Identity

Each scheduled run should have a stable run identity derived from scheduled context, such as run date and run type.

The product must be able to avoid confusing duplicate runs.

If the same scheduled run is executed twice with the same inputs:

- Deterministic strategy decisions should be identical.
- Journal records should preserve enough run context to identify the duplicate.
- The scheduler should not create a different strategy decision just because the run was retried.

### R2.2.6 Manual Run Support

The system must support a manual run mode for development, testing, and operator review.

Manual runs should:

- Use the same runtime pipeline as scheduled runs.
- Mark the trigger as manual.
- Avoid special strategy behavior.

### R2.2.7 Missed Schedule Catch-Up

If a scheduled run is missed, the system should support a catch-up run.

Catch-up runs should:

- Be explicitly marked as catch-up.
- Use the same deterministic strategy engine.
- Avoid replaying unrelated historical periods unless requested.

### R2.2.8 Respect Hot/Cold Boundary

Scheduled execution must preserve R2.1.

The scheduled runner must:

- Call the deterministic signal/runtime pipeline first.
- Journal hot-path decisions before Claude analysis.
- Skip Claude for rejected and no-trade decisions.
- Keep Claude optional.

### R2.2.9 Run Observability

Every scheduled run must expose enough information to understand what happened.

The run record should include:

- Run identity.
- Trigger type.
- Scheduled date or window.
- Current date used for strategy evaluation.
- Number of upcoming events evaluated.
- Number of strategy decisions produced.
- Number of candidate-ready decisions.
- Number of rejected decisions.
- Journal path, if written.
- Whether Claude analysis was enabled.

## Non-Functional Requirements

### Reliability

The scheduler must be safe to retry.

A failed Claude analysis must not cause the scheduler to lose deterministic hot-path decisions.

### Determinism

The scheduler must pass `current_date` explicitly into the strategy engine.

The strategy engine must not infer time from system clock during deterministic evaluation.

### Simplicity

The first version should be a simple scheduled runner, not a distributed job system.

It should be possible to test it with mocked calendar inputs and temporary journal files.

### Testability

Tests must be able to run the scheduled pipeline without:

- Real market data.
- Broker credentials.
- Real Claude calls.
- A real cron daemon.
- Network access.

### Auditability

Each run must produce structured output suitable for later journaling, dashboarding, or alerting.

## Decision Flow

```text
configured themes
  -> earnings calendar snapshot
    -> derive scheduled run date/window
      -> scheduled/manual/catch-up trigger
        -> run hot/cold runtime pipeline once
          -> journal run summary and decision events
            -> exit
```

## Out Of Scope

This PRD does not require:

- Continuous polling.
- WebSocket event triggers.
- Fast quote or news event classification.
- Live broker integration.
- Order placement.
- Position sizing.
- Real cron deployment.
- Cloud scheduler setup.
- UI scheduling dashboard.
- Real earnings-calendar provider integration.

WebSocket, webhook, or fast-poll event handling belongs to R2.3.

## Acceptance Criteria

R2.2 is complete when:

- The app has a scheduled-run abstraction that invokes the existing hot/cold runtime pipeline once per run.
- The scheduled runner can be tested with mocked earnings calendar inputs.
- The runner does not contain an infinite loop or sleep-and-rescan polling behavior.
- Manual and scheduled trigger types are represented explicitly.
- The runner passes `current_date` explicitly into the strategy engine.
- The runner can write or return a structured run summary.
- Hot-path decisions are preserved even when Claude is disabled or fails.
- Tests prove that the runner calls the runtime pipeline once for a scheduled run.
- Tests prove that no Claude client is required for scheduled deterministic execution.
- Tests prove repeated runs with the same inputs produce equal serialized output.

## Success Criteria

This requirement is successful when the product can answer:

> When does `prescient` wake up to evaluate the strategy?

The answer must be:

> It wakes on an explicit schedule derived from earnings-calendar context or manual operator request, runs the hot/cold pipeline once, records the result, and exits. It does not continuously poll the market.

## Current Implementation Notes

The current code already has the core pieces needed for R2.2:

- `prescient.signal` contains deterministic strategy evaluation.
- `prescient.runtime.run_hot_cold_strategy_pipeline(...)` runs the hot path first and optional Claude analysis second.
- JSONL journal writing exists for pipeline events.
- No scheduler package currently exists.

The next implementation milestone should add a small scheduler/runtime wrapper around the existing runtime pipeline without changing strategy scoring or Claude analyst behavior.
