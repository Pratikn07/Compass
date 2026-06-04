# PRD: R6.2 Self-Learning Morning Loop

## Ownership

Owner: Gem

Source note: Requirement from Gem learning phase: each morning the system should read the prior journal, analyze wins and losses, and tune parameters.

## Objective

Add a cold-path learning loop that runs before the trading day, reads prior journal records, analyzes realized and observable outcomes, and produces bounded parameter-tuning recommendations for the next runs.

R6.2 answers:

```text
What should the system learn from yesterday's journal before today's strategy runs, and how can it safely tune behavior without changing the deterministic core or risk safeguards?
```

The loop must improve strategy calibration over time while preserving the project boundaries already established by earlier PRDs:

- The deterministic strategy engine remains pure code.
- Claude, Gemini, sub-agents, or any other LLM cannot modify hot-path decisions.
- Broker adapters cannot be called from the learning analyzer.
- Risk limits, broker mode, and execution safety settings cannot be silently loosened.
- Every parameter recommendation or applied change is journaled and auditable.

## Background

The `prescient` runtime already writes JSONL journal events for hot-path strategy decisions, sub-agent reviews, and cold-path Claude analysis. Later broker and risk milestones add structured execution and risk decisions. Those journals create the audit trail needed for a morning review loop.

Without a learning loop, parameter changes remain manual and anecdotal. The user has to inspect prior decisions, infer which thresholds were too strict or too loose, and edit settings by hand. R6.2 turns that review into a repeatable daily routine:

```text
prior journal records
  -> parse decisions, risk checks, execution outcomes, and data quality
  -> classify wins, losses, missed opportunities, and bad-data days
  -> evaluate whether learnable parameters should move
  -> validate proposals against allowlists, bounds, and sample-size gates
  -> write a learning report and optional settings overlay
```

The first version should prefer conservative recommendations over aggressive automatic tuning. The system is allowed to learn, but it must not create a hidden feedback loop that overfits to a few trades or increases account risk after a lucky day.

## Definitions

### Morning Learning Loop

A scheduled cold-path job that runs once per trading morning before strategy evaluation. It may also be run manually for backfills or tests.

The morning loop reads journal records from a configured lookback period, with special attention to the most recent completed trading day.

### Prior Journal

The append-only JSONL record of prior pipeline decisions, analyst results, sub-agent results, risk decisions, sizing decisions, execution proposals, fills, exits, and realized outcomes.

For MVP, the loop may read from local JSONL files. A future journal database can implement the same reader interface.

### Outcome

An observable result associated with a prior decision or trade.

Outcome types:

- `win`: closed or marked outcome has positive realized PnL after known costs.
- `loss`: closed or marked outcome has negative realized PnL after known costs.
- `flat`: closed or marked outcome is zero or inside a configured neutral band.
- `open`: position is still open and not eligible for win/loss attribution.
- `unknown`: no reliable outcome record exists.
- `not_tradeable`: setup was never eligible for execution due to risk, liquidity, market-hours, or broker preflight checks.

The loop must not infer wins or losses from incomplete data. Unknown outcomes remain unknown.

### Learnable Parameter

A configuration value that is allowed to receive a tuning recommendation.

For MVP, learnable parameters are limited to selected strategy-calibration settings such as peer-signal thresholds and target run-up limits. Risk caps, broker mode, position-sizing ceilings, and safety halts are not learnable by automatic application.

### Parameter Proposal

A structured recommendation to change one learnable parameter from a current value to a proposed value, including evidence, confidence, sample size, bounds, and whether the proposal was applied.

### Settings Overlay

A generated configuration artifact containing only approved parameter changes. The overlay can be loaded by future runs without editing source code or mutating baseline defaults.

## Requirement

Each morning, the system must:

- Read prior journal records from the configured previous trading day and rolling lookback window.
- Parse only structured, schema-valid, journal-safe data.
- Join decisions to available risk, sizing, execution, and outcome records.
- Classify wins, losses, unknown outcomes, missed opportunities, data failures, and not-tradeable decisions.
- Compute performance diagnostics by theme, ticker, strategy type, expression, rejection reason, data source, and parameter band.
- Generate deterministic parameter proposals for allowlisted settings.
- Reject proposals that lack sufficient evidence, exceed configured bounds, or would loosen safety controls.
- Write a learning report to the journal.
- Optionally write a settings overlay when learning mode explicitly allows safe auto-application.

The morning learning loop must be a cold-path scheduled job. It must never run inside the hot-path strategy evaluation.

## User Value

R6.2 gives the user:

- A daily review of what worked and what failed.
- Less manual threshold tuning.
- Evidence-backed parameter changes instead of intuition.
- Protection from overfitting to a small number of trades.
- Clear visibility into why a parameter moved.
- A journaled audit trail for every recommendation and applied change.
- A safer path to continuous improvement without handing control to an LLM or broker adapter.

## Functional Requirements

### R6.2.1 Cold-Path Ownership

The learning loop must live outside the deterministic hot path, preferably under a dedicated package such as `prescient.learning`.

The learning package may import structured runtime, signal, and journal models. It must not be imported by:

- `prescient.signal`
- `prescient.risk`
- `prescient.broker`
- data provider adapters
- hot-path strategy evaluation functions

The hot path must produce the same decision for the same input whether the learning loop exists or not.

### R6.2.2 Morning Schedule

The system must support a scheduled morning request with fields equivalent to:

```python
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LearningTriggerType(StrEnum):
    SCHEDULED_MORNING = "scheduled_morning"
    MANUAL = "manual"
    BACKFILL = "backfill"


class LearningRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    trigger_type: LearningTriggerType
    run_date: date
    prior_trading_date: date
    lookback_start: date
    lookback_end: date
    journal_paths: list[str] = Field(default_factory=list)
    settings_snapshot_path: str | None = None
```

The default scheduled run should execute before the normal scheduled strategy pipeline for that date.

The exact scheduler implementation is out of scope for this PRD, but the runner must be callable directly by tests and future schedulers.

### R6.2.3 Journal Reader Boundary

The learning loop must read journal records through an interface, not by hard-coding one storage backend.

Expected interface:

```python
from collections.abc import Sequence
from datetime import date
from typing import Protocol


class LearningJournalReader(Protocol):
    def read_records(
        self,
        *,
        start_date: date,
        end_date: date,
        paths: Sequence[str],
    ) -> list["LearningJournalRecord"]:
        ...
```

MVP implementation:

- Local JSONL reader.
- Strict JSON parsing.
- Per-record schema validation.
- Malformed lines reported as structured warnings.
- No raw stack traces or secrets in learning reports.

Future implementations may read from a database, object store, or analytics warehouse behind the same interface.

### R6.2.4 Normalized Learning Records

The loop must normalize input journal records into a compact learning schema before analysis.

Expected record shape:

```python
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LearningRecordType(StrEnum):
    STRATEGY_DECISION = "strategy_decision"
    RISK_DECISION = "risk_decision"
    POSITION_SIZING = "position_sizing"
    EXECUTION_PROPOSAL = "execution_proposal"
    ORDER_FILL = "order_fill"
    TRADE_OUTCOME = "trade_outcome"
    DATA_PROVIDER_ERROR = "data_provider_error"
    LEARNING_REPORT = "learning_report"


class LearningJournalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_type: LearningRecordType
    run_id: str | None = None
    decision_id: str | None = None
    order_id: str | None = None
    trading_date: date | None = None
    created_at: datetime | None = None
    target: str | None = None
    theme: str | None = None
    strategy_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
```

The normalized schema must preserve enough features for learning:

- Strategy status.
- Rejection reasons and stages.
- Peer signal values.
- Thresholds used at decision time.
- Target run-up.
- Liquidity and options filter outcomes.
- Preferred expression.
- Risk decision status.
- Sizing decision status.
- Execution mode.
- Entry, exit, realized PnL, and fees when available.
- Data provider errors and missing-data reasons.

If a prior journal lacks the fields needed for a specific analysis, the learning loop must emit `insufficient_journal_features` instead of guessing.

### R6.2.5 Outcome Attribution

The loop must join decisions and outcomes deterministically.

Join precedence:

1. `decision_id`
2. `order_id`
3. `run_id + target + strategy_type + trading_date`
4. `target + theme + nearest prior candidate decision`, only when unambiguous

If multiple candidate decisions can match an outcome, the outcome must be marked `ambiguous_outcome_match` and excluded from parameter tuning.

Open positions must not count as wins or losses unless a configured mark-to-market policy is enabled. The MVP should default to realized outcomes only.

### R6.2.6 Win/Loss Analysis

The loop must compute metrics equivalent to:

- Total evaluated decisions.
- Candidate-ready count.
- Executed count.
- Closed outcome count.
- Win count.
- Loss count.
- Flat count.
- Unknown outcome count.
- Average realized PnL.
- Median realized PnL.
- Win rate.
- Average win.
- Average loss.
- Payoff ratio.
- Largest loss.
- Decision-to-execution drop-off count.
- Rejections by reason.
- Losses by theme, target, strategy type, and expression.
- Wins by theme, target, strategy type, and expression.
- Data-provider error counts.
- Decisions excluded from tuning and why.

The loop must separate:

- A bad strategy signal.
- A valid signal blocked by risk.
- A valid signal blocked by liquidity or market-hours checks.
- A missing-data day.
- A broker/execution failure.

Parameter tuning must use only outcomes attributable to strategy-calibration behavior. Broker failures, missing provider data, and safety-gate blocks may produce operational recommendations, but they must not loosen strategy thresholds.

### R6.2.7 Learnable Parameter Allowlist

Only explicitly allowlisted parameters may receive auto-application proposals.

MVP allowlist:

```python
from pydantic import BaseModel, ConfigDict


class LearnableParameterPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    min_value: float | int | bool
    max_value: float | int | bool
    max_daily_delta: float | int | None = None
    min_closed_outcomes: int = 10
    min_distinct_trading_days: int = 5
    auto_apply_allowed: bool = False


DEFAULT_LEARNABLE_PARAMETERS = [
    LearnableParameterPolicy(
        path="strategy.min_positive_peer_ratio",
        min_value=0.50,
        max_value=0.90,
        max_daily_delta=0.05,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.min_average_peer_score",
        min_value=1.0,
        max_value=3.5,
        max_daily_delta=0.25,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.max_target_runup_pct",
        min_value=5.0,
        max_value=15.0,
        max_daily_delta=1.0,
        min_closed_outcomes=10,
        min_distinct_trading_days=5,
        auto_apply_allowed=True,
    ),
    LearnableParameterPolicy(
        path="strategy.peer_result_window_days",
        min_value=7,
        max_value=45,
        max_daily_delta=7,
        min_closed_outcomes=15,
        min_distinct_trading_days=7,
        auto_apply_allowed=False,
    ),
    LearnableParameterPolicy(
        path="strategy.min_reported_peers",
        min_value=2,
        max_value=5,
        max_daily_delta=1,
        min_closed_outcomes=20,
        min_distinct_trading_days=10,
        auto_apply_allowed=False,
    ),
]
```

The policy must be configurable, but the defaults must remain conservative.

### R6.2.8 Forbidden Auto-Tuned Parameters

The loop must never automatically loosen or modify:

- `RiskSettings.max_trade_loss_pct`
- `AccountSizePolicySettings.absolute_trade_loss_pct_ceiling`
- `AccountSizePolicySettings.tier_default_trade_loss_pct`
- `DailyHaltSettings.max_daily_realized_loss_pct`
- `DailyHaltSettings.max_losing_trades_per_day`
- `ConcentrationSettings.max_open_positions`
- `ConcentrationSettings.max_single_ticker_exposure_pct`
- execution mode
- broker adapter selection
- broker credentials
- API keys
- position quantity
- order type
- limit price
- stop price
- Claude model selection
- Claude prompts
- sub-agent enablement
- data provider credentials

The loop may generate review-only observations for these areas, such as "losses cluster around poor liquidity" or "risk gate blocked all candidates", but it must not apply changes.

### R6.2.9 Deterministic Tuning Rules

The MVP tuning engine must be deterministic and testable.

It may use rules such as:

- If candidate-ready decisions with low peer ratios produce repeated losses, propose increasing `strategy.min_positive_peer_ratio`.
- If candidate-ready decisions just above `min_average_peer_score` lose repeatedly while higher-score decisions win, propose increasing `strategy.min_average_peer_score`.
- If losses cluster in targets with high pre-earnings run-up, propose lowering `strategy.max_target_runup_pct`.
- If many high-quality winners were rejected only because `min_reported_peers` was too high, produce a review-only proposal to lower `strategy.min_reported_peers`.
- If most rejections are due to missing data, produce an operational data-quality recommendation instead of changing signal thresholds.
- If closed outcomes are below the sample-size threshold, produce a no-op report with the evidence collected.

Any statistical method must be explainable from journaled features. The loop must not use opaque model output as the source of truth for parameter application.

### R6.2.10 LLM Role

Gem, Claude, Gemini, or another LLM may be used only as an optional narrative summarizer for the learning report.

An LLM may:

- Summarize observed wins and losses.
- Identify questions for human review.
- Explain why the deterministic tuner made no change.
- Draft a daily learning note.

An LLM must not:

- Modify parameter values directly.
- Override allowlist checks.
- Override sample-size gates.
- Increase risk limits.
- Change broker mode.
- Invent outcomes not present in the journal.
- Read raw secrets, credentials, account identifiers, or full raw transcripts.

The deterministic `ParameterProposal` objects are the contract. Narrative commentary is secondary and non-authoritative.

### R6.2.11 Learning Modes

The loop must support explicit modes:

```python
from enum import StrEnum


class LearningMode(StrEnum):
    REPORT_ONLY = "report_only"
    SHADOW_OVERLAY = "shadow_overlay"
    AUTO_APPLY_SAFE = "auto_apply_safe"
```

Mode behavior:

- `report_only`: default. Write diagnostics and proposals only. Do not write a settings overlay.
- `shadow_overlay`: write a settings overlay for paper/backtest comparison, but do not load it into live runs automatically.
- `auto_apply_safe`: apply only allowlisted, bounded, sample-backed proposals where `auto_apply_allowed = true`. This mode must be blocked when execution mode is `live`.

The default must be `report_only`.

### R6.2.12 Parameter Proposal Contract

Each recommendation must be structured and journal-safe.

Expected model:

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ParameterProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"
    REVIEW_ONLY = "review_only"
    NO_OP = "no_op"


class ParameterProposalReason(StrEnum):
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    OUTSIDE_ALLOWLIST = "outside_allowlist"
    OUTSIDE_BOUNDS = "outside_bounds"
    DAILY_DELTA_EXCEEDED = "daily_delta_exceeded"
    LIVE_MODE_BLOCKED = "live_mode_blocked"
    SAFETY_PARAMETER_FORBIDDEN = "safety_parameter_forbidden"
    AMBIGUOUS_OUTCOME_DATA = "ambiguous_outcome_data"
    EVIDENCE_SUPPORTED = "evidence_supported"
    DATA_QUALITY_ISSUE = "data_quality_issue"


class ParameterProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    current_value: float | int | bool | str
    proposed_value: float | int | bool | str
    status: ParameterProposalStatus
    reasons: list[ParameterProposalReason] = Field(default_factory=list)
    evidence_summary: str
    sample_size: int
    distinct_trading_days: int
    confidence: float
    auto_apply_allowed: bool
    applied: bool = False
```

The proposal must include enough information for the user to understand why the value moved or why it did not move.

### R6.2.13 Learning Run Report

Each morning run must produce a durable report equivalent to:

```python
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LearningRunReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    run_date: date
    prior_trading_date: date
    lookback_start: date
    lookback_end: date
    created_at: datetime
    mode: LearningMode
    records_read: int
    records_skipped: int
    malformed_record_count: int
    evaluated_decision_count: int
    closed_outcome_count: int
    win_count: int
    loss_count: int
    flat_count: int
    unknown_outcome_count: int
    proposals: list[ParameterProposal] = Field(default_factory=list)
    operational_recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    settings_overlay_path: str | None = None
```

The report must be appended to the journal as a `learning_report` event and may also be written as a standalone JSON artifact for easier review.

### R6.2.14 Settings Overlay

When mode allows a settings overlay, the generated file must:

- Include only applied parameter changes.
- Include the source learning run ID.
- Include the prior value and proposed value.
- Include the evidence summary.
- Include the effective date.
- Be loadable without changing source code.
- Be ignored by live execution unless explicitly enabled by future configuration.

Example overlay:

```yaml
learning_overlay:
  run_id: "learn-2026-06-03"
  effective_date: "2026-06-03"
  mode: "auto_apply_safe"
  parameters:
    strategy.min_positive_peer_ratio:
      previous_value: 0.67
      value: 0.72
      reason: "Losses clustered in candidate decisions with positive peer ratio below 0.72."
      sample_size: 14
      distinct_trading_days: 8
```

### R6.2.15 Fail-Closed Behavior

The learning loop must produce no applied changes when:

- Journal files are missing.
- Journal records are malformed beyond the configured tolerance.
- Outcome records are missing.
- Outcomes cannot be joined unambiguously.
- The settings snapshot cannot be read.
- Current parameter values cannot be determined.
- Proposed values are outside policy bounds.
- The run is in live execution mode.
- The sample size is below policy requirements.

In these cases, the report should still be written with warnings and no applied changes.

### R6.2.16 Idempotency

Running the learning loop twice with the same request, same journal records, and same settings snapshot must produce the same report content except for timestamps.

If a report with the same `run_id` already exists, the runner should either:

- refuse to write a duplicate unless `allow_overwrite` is set, or
- write a deterministic duplicate marker without applying changes twice.

### R6.2.17 Audit And Rollback

Every applied parameter change must be reversible.

The system must preserve:

- Baseline value.
- Prior overlay value, if any.
- Proposed value.
- Effective date.
- Learning run ID.
- Evidence summary.
- Policy bounds used.

The PRD does not require a rollback command, but it requires the data needed to implement one later.

## Technical Architecture

### Package Layout

Recommended files:

```text
src/prescient/learning/
  __init__.py
  models.py
  journal_reader.py
  analyzer.py
  tuner.py
  overlay.py
  runner.py
```

Responsibilities:

- `models.py`: learning request, report, outcome, metric, policy, and proposal models.
- `journal_reader.py`: JSONL reader and normalized record conversion.
- `analyzer.py`: win/loss, attribution, and diagnostics calculation.
- `tuner.py`: deterministic parameter proposal logic and policy validation.
- `overlay.py`: settings overlay writer.
- `runner.py`: orchestrates the morning learning run.

### Dependency Direction

```text
scheduler/manual trigger
  -> prescient.learning.runner
    -> LearningJournalReader
    -> learning analyzer
    -> deterministic tuner
    -> optional overlay writer
    -> journal append

prescient.signal  -> no dependency on learning
prescient.risk    -> no dependency on learning
prescient.broker  -> no dependency on learning
```

### Morning Flow

```text
scheduled morning trigger
  -> build LearningRunRequest
  -> read settings snapshot
  -> read prior journal JSONL
  -> normalize learning records
  -> join decisions to outcomes
  -> compute diagnostics
  -> generate parameter proposals
  -> validate allowlist, bounds, sample size, and mode
  -> write learning report
  -> optionally write settings overlay
  -> return LearningRunReport
```

## Non-Functional Requirements

### Determinism

Given the same journal records, settings snapshot, learning policy, and run request, the deterministic analysis and proposals must be repeatable.

### Safety

The learning loop must default to no automatic settings mutation. Any automatic application must be bounded, allowlisted, sample-backed, and blocked in live mode.

### Testability

The loop must be testable with temporary JSONL files and in-memory reader fakes. Tests must not require network access, broker credentials, Claude, Gemini, or a real market data provider.

### Security

Reports and proposals must be journal-safe. They must not contain:

- API keys.
- Broker credentials.
- Account identifiers.
- Raw order credentials.
- Raw provider payloads.
- Raw earnings call transcripts.
- Full prompt or model responses if they contain sensitive data.

### Performance

The morning loop is not in the trading hot path, but it should be bounded. For MVP, local JSONL processing should complete within a few seconds for normal journal sizes.

### Explainability

Each proposal must explain:

- Which parameter is affected.
- What value is changing.
- Which evidence supports the change.
- Why the proposal was applied, rejected, or review-only.
- Which policy bounds were used.

## Acceptance Criteria

R6.2 is complete when:

- A `prescient.learning` package exists with models, JSONL journal reading, analyzer, tuner, overlay writer, and runner boundaries.
- The learning runner can be invoked with a `LearningRunRequest` and returns a `LearningRunReport`.
- The runner reads prior journal records from local JSONL through a `LearningJournalReader` interface.
- Malformed journal lines are counted and reported without crashing the run, unless they exceed a configured tolerance.
- Strategy decisions can be joined to trade outcomes using deterministic matching rules.
- Ambiguous or missing outcomes are excluded from parameter tuning.
- The report includes win/loss/flat/unknown counts, evaluated decision counts, data-quality warnings, and parameter proposals.
- The tuner emits no applied changes when sample-size requirements are not met.
- The tuner rejects proposals outside the allowlist or outside configured bounds.
- The tuner never applies changes to risk caps, broker mode, broker credentials, execution quantities, order prices, or LLM settings.
- `report_only` mode writes recommendations but no settings overlay.
- `shadow_overlay` mode writes an overlay artifact without marking changes as live-applied.
- `auto_apply_safe` applies only allowlisted safe parameters and is blocked when execution mode is live.
- Every applied proposal records prior value, proposed value, evidence, sample size, distinct trading days, policy bounds, and learning run ID.
- Running the same request twice does not apply the same change twice.
- Boundary tests verify that `prescient.signal`, `prescient.risk`, and `prescient.broker` do not import `prescient.learning`.
- Tests require no network, broker, Claude, Gemini, or market data credentials.

## Non-Goals

R6.2 does not require:

- Live broker calls.
- Real-time intraday learning.
- Reinforcement learning.
- Neural-network training.
- Automatic strategy creation.
- Automatic risk-limit increases.
- Automatic live-mode configuration changes.
- A dashboard UI.
- A journal database migration.
- Backtest engine implementation.
- Raw transcript analysis.
- LLM-authoritative parameter updates.

## Open Questions

- Should future outcome records come from broker fills only, manual journal entries, or both?
- Should missed-opportunity analysis require a formal backtest/counterfactual engine before it can affect proposals?
- Should settings overlays be stored as YAML, JSON, or in a future config database?
- Should review-only recommendations be routed to a daily Slack/email digest in a later milestone?

## Product FAQ

### Does this mean the system will change itself every morning?

No. The default mode is `report_only`, which writes diagnostics and recommendations but does not change settings. Automatic application is limited to explicitly allowlisted strategy-calibration parameters and is blocked in live mode.

### Can the loop increase risk after a profitable day?

No. Risk caps, daily halt settings, concentration limits, broker mode, and order parameters are forbidden from automatic tuning.

### Can Gem, Claude, or Gemini decide the new parameters?

No. LLMs may summarize the report, but deterministic code owns parameter proposals and policy validation.

### What happens if yesterday's journal has no closed outcomes?

The loop writes a no-op report with warnings. It may summarize decision quality and missing data, but it must not apply parameter changes.

### What is the minimum useful MVP?

A local JSONL reader, deterministic win/loss analyzer, conservative tuner for a small allowlist of strategy settings, report-only default mode, and tests proving unsafe parameters cannot be changed.
