# PRD: R6.1 Journal Every Decision

## Ownership

Owner: Ours

Source note: Requirement from Ours learning phase: journal every decision, win or lose, with thesis, data snapshot, outcome, and P&L for all decisions.

---

## Objective

Add a durable, append-only decision journal that records every strategy decision and its lifecycle outcome, including rejected decisions, no-trade decisions, risk-blocked candidates, trade proposals, fills, exits, realized P&L, and unresolved outcomes.

R6.1 answers:

```text
What did the system decide, what data and thesis supported that decision, what happened afterward, and what was the realized or unresolved P&L?
```

The decision journal is the audit foundation for R6.2 self-learning. R6.2 can only analyze wins, losses, missed opportunities, data failures, and parameter behavior if R6.1 first preserves the full decision record.

---

## Background

The runtime already writes JSONL pipeline events for:

- hot-path strategy decisions
- optional sub-agent review packets
- optional cold-path Claude analysis

Those events are useful, but they are stage-specific. They do not yet define a complete decision ledger that can join:

- the original deterministic thesis
- the data snapshot used at decision time
- risk and sizing decisions
- execution mode
- order proposal or broker order state
- final outcome
- realized P&L and fees

Without a full journal, the system can only review executed trades or ad hoc logs. That misses two important learning cases:

1. Good rejected ideas that would have worked but were blocked for a reason worth reviewing.
2. Bad ideas that never traded because the deterministic, risk, liquidity, or broker gates correctly rejected them.

R6.1 requires journaling every decision, not just every trade.

```text
scheduled/manual/event run
  -> deterministic strategy decision
    -> append decision journal record
      -> optional analyst/sub-agent records
        -> risk gate and position sizing
          -> proposal/order/fill/exit records when applicable
            -> final outcome and P&L record
```

The journal must remain compatible with existing project boundaries:

- `prescient.signal` returns deterministic, journal-safe decisions but does not write journal records.
- `prescient.risk` returns deterministic, journal-safe risk and sizing decisions but does not write journal records.
- `prescient.broker` returns broker state and order results but does not decide learning attribution.
- `prescient.runtime` or a dedicated journal package owns orchestration-level record creation.
- Claude, Gemini, sub-agents, or any LLM cannot edit hot-path decisions, P&L, fills, or broker facts.

---

## Definitions

### Decision

A decision is any strategy evaluation result produced by the deterministic signal/runtime pipeline.

Decision statuses include candidate-ready, rejected, no-trade, and any future status returned by `StrategyDecision`.

### Decision ID

A stable identifier for one evaluated decision within one run. It must be deterministic from run context and decision content, or explicitly assigned by the runtime before journaling.

The ID must allow later records to attach risk results, order results, outcomes, notes, and learning reports to the original decision.

### Run ID

The scheduler or runtime identity for one bounded run. Scheduled runs already include `run_id` in `ScheduledRunRequest`; manual, event-driven, and future broker/execution runs must provide an equivalent value.

### Data Snapshot

A compact, structured record of the inputs used for the decision.

For MVP, this is not a full raw provider payload. It is a journal-safe snapshot of features and references that matter for replay and analysis:

- current date
- target ticker and earnings date
- strategy type
- theme and drivers
- peer tickers and peer result summaries
- target market data
- option-chain summary or selected option
- technical indicator snapshot when available
- data provider names, fetch times, and missing-data reasons
- relevant settings and thresholds used at decision time

Raw API headers, credentials, full transcripts, full OHLCV history, account identifiers, and secrets must never be written.

### Thesis

The concise reason the system considered or rejected the setup.

For candidate-ready decisions, the thesis should come from the deterministic candidate brief and any optional analyst summary must be stored separately. For rejected or no-trade decisions, the thesis must explain the rejection in structured terms rather than inventing a trade narrative.

### Outcome

The observed lifecycle result of a decision.

Outcome types:

- `pending`: a decision has been recorded but has no final result yet.
- `rejected`: the deterministic strategy layer rejected the setup.
- `no_trade`: the setup did not become new risk.
- `risk_blocked`: risk, sizing, daily halt, concentration, liquidity, market-hours, or broker preflight blocked the setup.
- `proposed`: the setup produced a proposal but no broker order was submitted.
- `submitted`: an order was sent to the broker.
- `filled`: an order filled but the position is not closed.
- `cancelled`: the order was cancelled.
- `broker_rejected`: the broker rejected the order.
- `closed_win`: the decision produced a closed position with positive realized P&L after known costs.
- `closed_loss`: the decision produced a closed position with negative realized P&L after known costs.
- `closed_flat`: the decision produced a closed position with zero realized P&L or a configured neutral band.
- `unknown`: no reliable outcome can be assigned.

### P&L

P&L means realized profit and loss associated with a decision once the position is closed or otherwise resolved.

For MVP, P&L attribution should be realized-only. Mark-to-market unrealized P&L may be recorded as an observation, but it must not classify a decision as a win or loss unless a future policy explicitly enables that behavior.

---

## Requirement

Every strategy decision must produce a durable journal record with:

- run identity
- decision identity
- target, theme, strategy type, and strategy status
- thesis or rejection explanation
- compact data snapshot
- settings snapshot or setting references used at decision time
- optional analyst and sub-agent results
- risk, sizing, execution-quality, and broker-preflight decisions when available
- proposal/order/fill/exit lifecycle records when applicable
- final outcome
- realized P&L and fees when known
- warnings, missing data, ambiguity markers, and provenance

The journal must capture decisions that win, lose, never trade, are rejected, are blocked, or remain unresolved.

---

## User Value

R6.1 gives the user:

- A complete audit trail for every system decision.
- A way to inspect why the system acted or refused to act.
- A reliable source for post-trade reviews.
- A way to learn from non-trades, not just executed trades.
- Evidence for whether strategy thresholds, data providers, risk gates, and broker adapters are helping or hurting.
- The structured input needed by R6.2 without scraping raw logs or guessing outcome attribution.

---

## Functional Requirements

### R6.1.1 Journal Every Strategy Decision

The runtime must journal every `StrategyDecision` produced by the hot path.

This includes:

- candidate-ready decisions
- rejected decisions
- no-trade decisions
- decisions skipped by Claude
- decisions later blocked by risk
- decisions that never reach broker execution

The system must not restrict journaling to executed orders or closed trades.

### R6.1.2 Runtime-Owned Journal Boundary

Journal writing must be owned by `prescient.runtime` or a dedicated package such as `prescient.journal`.

The following packages must not write decision journal records directly:

- `prescient.signal`
- `prescient.risk`
- `prescient.broker`
- data provider adapters
- `prescient.analyst`

Those packages may return journal-safe models. The runtime assembles and appends records.

### R6.1.3 Stable Record Identity

Each journaled decision must include:

- `journal_record_id`
- `run_id`
- `decision_id`
- `decision_index`
- `created_at`
- `trading_date`
- `source`

The `decision_id` must be stable enough for later lifecycle records to reference the original decision.

MVP identity rule:

```text
decision_id = hash(run_id + decision_index + target + strategy_type + strategy_status)
```

If a future decision model includes a canonical decision fingerprint, the journal should use that fingerprint instead.

### R6.1.4 Append-Only Lifecycle Records

The journal must be append-only.

Later lifecycle changes must append new records rather than mutating earlier records in place.

Record types should include:

```python
from enum import StrEnum


class DecisionJournalRecordType(StrEnum):
    STRATEGY_DECISION = "strategy_decision"
    ANALYST_REVIEW = "analyst_review"
    SUB_AGENT_REVIEW = "sub_agent_review"
    RISK_DECISION = "risk_decision"
    POSITION_SIZING = "position_sizing"
    EXECUTION_PROPOSAL = "execution_proposal"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILL = "order_fill"
    ORDER_CANCELLED = "order_cancelled"
    BROKER_REJECTION = "broker_rejection"
    TRADE_EXIT = "trade_exit"
    TRADE_OUTCOME = "trade_outcome"
    OUTCOME_CORRECTION = "outcome_correction"
```

The latest state of a decision is derived by replaying records for the same `decision_id`.

### R6.1.5 Normalized Decision Journal Schema

Journal records must use a structured schema equivalent to:

```python
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DecisionJournalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    journal_record_id: str
    record_type: DecisionJournalRecordType
    run_id: str
    decision_id: str
    decision_index: int | None = None
    trading_date: date
    created_at: datetime
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    strategy_status: str | None = None
    execution_mode: str | None = None
    source: str
    order_id: str | None = None
    parent_record_id: str | None = None
    duplicate_of_record_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
```

The `payload` must contain only schema-valid, JSON-serializable, journal-safe data.

### R6.1.6 Required Strategy Decision Payload

Every `strategy_decision` record must include payload fields equivalent to:

- `thesis`
- `decision_summary`
- `strategy_decision`
- `candidate_brief`, if present
- `rejection_reasons`
- `warnings`
- `data_snapshot`
- `settings_snapshot`
- `missing_data`
- `source_events`

For rejected decisions, `thesis` may be a structured rejection explanation. It must not claim a bullish or bearish trade thesis if the deterministic engine did not produce one.

### R6.1.7 Data Snapshot Requirements

The data snapshot must be compact and replay-oriented.

It should include:

- universe version or configured theme names
- target ticker
- target earnings date
- target market data summary
- peer result summaries
- option selection or option-chain summary
- technical indicator snapshot summary
- data provider names
- provider fetch timestamps when available
- feature values used in filters and scores
- missing fields and provider errors

It must not include:

- API keys or auth tokens
- raw provider request headers
- full raw provider payloads
- full raw transcripts
- full candle history
- account numbers or personal identifiers

### R6.1.8 Analyst And Sub-Agent Journaling

Optional Claude and sub-agent outputs must be journaled as separate lifecycle records linked to the original `decision_id`.

The journal must preserve the hot/cold boundary:

- The hot-path `strategy_decision` record must be written before any Claude or sub-agent analysis runs.
- Claude analysis must not alter the original strategy decision record.
- Analyst review records must preserve `status`, `recommendation`, `thesis`, `reasoning`, `conviction_score`, `missing_context`, and `contradictions` when available.
- Failed or skipped analyst calls must be journaled as skipped or failed, with journal-safe error text.

### R6.1.9 Risk, Sizing, And Execution-Quality Journaling

Risk and sizing outputs must be journaled as lifecycle records linked to the decision.

Records should preserve:

- daily halt decision
- risk gate decision
- position sizing decision
- execution-quality decision, when available
- broker preflight decision, when available
- rejection reasons
- warnings
- approved quantity
- projected maximum loss
- entry cost required
- broker execution permission

Risk-blocked and not-evaluable decisions must still receive an outcome classification such as `risk_blocked` or `unknown`.

### R6.1.10 Proposal, Order, Fill, Exit, And P&L Records

When a decision produces a proposal, order, fill, or exit, the runtime must append linked lifecycle records.

Expected fields:

- `execution_mode`
- `broker_name`
- `order_id`
- `symbol`
- `side`
- `expression`
- `quantity`
- `limit_price`
- `submitted_at`
- `status`
- `filled_quantity`
- `average_fill_price`
- `entry_price`
- `exit_price`
- `fees`
- `gross_realized_pnl`
- `net_realized_pnl`
- `closed_at`
- `pnl_currency`

P&L must remain nullable until it is reliably known.

### R6.1.11 Outcome Attribution

The system must attach outcomes to decisions deterministically.

Join precedence:

1. `decision_id`
2. `order_id`
3. `run_id + target + strategy_type + trading_date`
4. `target + theme + nearest prior candidate decision`, only when unambiguous

If an outcome cannot be matched to exactly one decision, the journal must write an `unknown` or `ambiguous_outcome_match` marker rather than guessing.

### R6.1.12 Outcome Classification

Outcome classification must be structured and journal-safe.

Expected model:

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DecisionOutcomeType(StrEnum):
    PENDING = "pending"
    REJECTED = "rejected"
    NO_TRADE = "no_trade"
    RISK_BLOCKED = "risk_blocked"
    PROPOSED = "proposed"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    BROKER_REJECTED = "broker_rejected"
    CLOSED_WIN = "closed_win"
    CLOSED_LOSS = "closed_loss"
    CLOSED_FLAT = "closed_flat"
    UNKNOWN = "unknown"


class DecisionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome_type: DecisionOutcomeType
    net_realized_pnl: float | None = None
    gross_realized_pnl: float | None = None
    fees: float | None = None
    pnl_currency: str = "USD"
    open_quantity: float | None = None
    closed_quantity: float | None = None
    outcome_reasons: list[str] = Field(default_factory=list)
    ambiguous: bool = False
```

Win/loss classification must use net realized P&L after known costs.

### R6.1.13 Storage Backend

MVP storage should remain local JSONL to match the existing runtime journal behavior.

The implementation must expose a small writer/reader boundary so future storage can move to a database, object store, or analytics warehouse without changing signal or risk code.

Expected interfaces:

```python
from collections.abc import Iterable, Sequence
from typing import Protocol


class DecisionJournalWriter(Protocol):
    def append_records(self, records: Iterable[DecisionJournalRecord]) -> None:
        ...


class DecisionJournalReader(Protocol):
    def read_records(
        self,
        *,
        run_id: str | None = None,
        decision_id: str | None = None,
    ) -> Sequence[DecisionJournalRecord]:
        ...
```

### R6.1.14 Idempotency And Duplicate Handling

The journal must be safe for retried runs.

If a scheduled run is retried with the same `run_id` and same decision content, the writer must either:

- avoid duplicate `journal_record_id` values, or
- write duplicate-safe records with an explicit `duplicate_of_record_id` marker.

The journal must not create conflicting final outcomes for the same decision without an explicit `outcome_correction` record.

### R6.1.15 Journal Safety

All records must be safe to serialize to JSONL and safe to read by R6.2.

Requirements:

- no secrets
- no credentials
- no raw headers
- no personal account identifiers
- no raw provider payloads
- no full transcripts
- no raw stack traces
- no non-JSON objects
- no unserializable datetime objects

Errors must be normalized into structured, journal-safe warnings.

### R6.1.16 Learning Compatibility

The journal must preserve enough features for R6.2 to compute:

- evaluated decision count
- candidate-ready count
- rejected count
- no-trade count
- executed count
- closed outcome count
- win count
- loss count
- flat count
- unknown outcome count
- P&L by theme, target, strategy type, expression, and execution mode
- rejections by reason
- data errors and missing-data reasons
- loss clusters by data features and threshold bands
- decisions excluded from learning and why

If a decision lacks fields required for a learning analysis, the journal record must make the gap explicit through `missing_data` or `insufficient_journal_features`.

---

## Acceptance Criteria

R6.1 is complete when:

- Every hot-path `StrategyDecision` produces a `strategy_decision` journal record.
- Rejected and no-trade decisions are journaled, not just executed trades.
- Each decision record has a stable `run_id` and `decision_id`.
- The hot-path journal record is written before optional Claude or sub-agent work.
- Analyst, sub-agent, risk, sizing, proposal, order, fill, exit, and outcome events can be appended as linked lifecycle records.
- Outcome and P&L records remain nullable until reliable facts are available.
- Closed outcomes classify wins and losses using net realized P&L.
- Ambiguous outcome matches are marked unknown or ambiguous instead of guessed.
- The signal, risk, broker, data, and analyst packages do not write journal records directly.
- JSONL storage works for MVP and preserves schema-valid records.
- Tests prove journal records are JSON-serializable and do not leak secrets or raw payloads.
- R6.2 can read normalized records without scraping unstructured logs.

---

## Verification Plan

### Automated Tests

1. **Every Decision Is Journaled**
   - Run the hot/cold pipeline with candidate-ready, rejected, and no-trade decisions.
   - Assert each decision produces a linked `strategy_decision` record.

2. **Hot Before Cold**
   - Enable Claude and sub-agents.
   - Assert the first record for a decision is always `strategy_decision`.
   - Assert analyst records do not mutate the original strategy decision payload.

3. **Risk And Sizing Lifecycle Records**
   - Run with a mock broker adapter.
   - Assert risk gate and sizing decisions are appended with the same `decision_id`.
   - Assert blocked decisions still receive structured outcome state.

4. **Outcome And P&L Records**
   - Append fill and exit records for a mock order.
   - Assert net realized P&L determines `closed_win`, `closed_loss`, or `closed_flat`.
   - Assert P&L remains null for open or unresolved decisions.

5. **Ambiguous Attribution**
   - Create multiple same-target candidate decisions and an outcome without `decision_id` or `order_id`.
   - Assert the outcome is marked ambiguous and excluded from win/loss classification.

6. **Journal Safety**
   - Serialize records to JSONL and parse them back.
   - Assert no secrets, raw headers, account identifiers, raw provider payloads, or raw stack traces are present.

7. **Boundary Tests**
   - Assert `prescient.signal`, `prescient.risk`, `prescient.broker`, and data provider modules do not import the journal writer.

### Manual Verification

- Run a manual scheduled pipeline with a temporary JSONL journal path.
- Confirm every evaluated target has a decision record.
- Confirm a rejected target includes thesis/rejection context and no fake P&L.
- Confirm a proposed or filled mock trade receives linked lifecycle records.
- Confirm the resulting JSONL can be read by a simple R6.2-style parser.

---

## Non-Goals

- This PRD does not require a database journal backend.
- This PRD does not require a UI for journal browsing.
- This PRD does not implement the R6.2 learning algorithm.
- This PRD does not require automatic parameter tuning.
- This PRD does not require mark-to-market win/loss classification.
- This PRD does not change risk limits, broker mode behavior, or order placement logic.
- This PRD does not require full raw provider payload replay.
- This PRD does not make Claude, Gemini, or any LLM authoritative for outcomes or P&L.

---

## Open Questions

None for MVP. The first implementation should use local JSONL, realized-only P&L classification, and append-only lifecycle records.
