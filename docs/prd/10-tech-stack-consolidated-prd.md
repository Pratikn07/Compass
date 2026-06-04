# PRD: R10 Consolidated Tech Stack

Owner: All

## Summary

R10 consolidates the Prescient technical stack into a small, explicit platform
baseline:

- Python as the implementation language.
- `uv` as the canonical environment, dependency, lockfile, and command runner.
- Claude Code as the agentic development and operator-assist surface.
- MCP connectors as the integration layer for external systems when connector
  access is needed.
- SQLite as the default local durable store for MVP journals, run state, caches,
  and fixtures.
- cron-compatible scheduling as the default trigger mechanism for bounded,
  idempotent scheduled jobs.

This PRD is a platform-standardization requirement. It does not add a trading
feature by itself, and it does not relax any existing safety boundaries around
Claude, broker adapters, risk gates, or deterministic signal logic.

## Problem

The project now has deterministic signal, risk, data, broker, learning, alert,
storage, and backtest layers. Without a consolidated stack decision, future work
can drift into ad hoc runtimes, dependency managers, connector styles, storage
engines, and schedulers. That drift increases test cost, operational ambiguity,
and the risk that live-trading code depends on tools meant only for development
or cold-path review.

R10 creates a shared implementation baseline so all future PRDs, plans, and
modules use the same assumptions unless a later PRD explicitly overrides them.

## Goals

- Establish Python + `uv` as the default development and execution path.
- Keep Claude Code out of deterministic hot-path business logic while preserving
  it as the preferred developer/operator-assist environment.
- Standardize MCP connector usage as a bounded integration mechanism, not a
  hidden dependency inside pure signal or risk code.
- Use SQLite as the default local durable store for MVP persistence and
  repeatable testing.
- Use cron-compatible scheduling for scheduled runs, with explicit idempotency,
  locking, and exit-code behavior.
- Define acceptance criteria that prevent future stack drift.

## Non-Goals

- No rewrite of existing modules purely to rename or reshuffle dependencies.
- No live broker, live provider, or cloud deployment changes.
- No replacement of existing adapter interfaces with direct MCP calls.
- No direct Claude Code dependency inside importable application packages.
- No new trading strategy, risk rule, alert channel, or backtest metric.
- No mandatory hosted database migration. SQLite is the local/default baseline;
  remote storage can remain behind storage interfaces when explicitly required.

## Scope

R10 applies to:

- repository tooling and developer commands
- dependency and lockfile management
- local persistence defaults
- scheduled job execution conventions
- connector access patterns
- future PRD and implementation-plan assumptions
- boundary tests that enforce stack separation

R10 does not require code changes in this PRD pass unless an implementation plan
later chooses to add tests, docs, CLI commands, SQLite migrations, or scheduler
wrappers.

## Platform Requirements

### Python

- Python is the canonical language for application code, tests, adapters, CLI
  commands, and scheduled jobs.
- The project must continue using a `src/` package layout.
- New application modules must use typed models and deterministic helper
  functions consistent with existing `prescient.*` package boundaries.
- Shared domain contracts should use Pydantic models where structured validation
  and JSON-safe serialization matter.
- Pure deterministic packages must not depend on local machine state, network
  clients, MCP tools, or Claude Code.

### uv

- `uv` is the canonical way to run project commands.
- `pyproject.toml` is the source of dependency declarations.
- `uv.lock` is the committed dependency lock.
- Verification commands should prefer `uv run ...`, for example:
  - `uv run pytest -q`
  - `uv run ruff check .`
- New implementation plans must not introduce parallel dependency managers
  unless explicitly justified by a later PRD.

### Claude Code

- Claude Code is the preferred environment for agentic development,
  PRD/plan authoring, code review assistance, and operator-assist workflows.
- Claude Code must not be required to execute deterministic strategy, risk,
  broker, storage, scheduler, or backtest modules.
- Claude Code may read project files and help produce proposals, but final
  trading authority remains in deterministic code-owned gates and explicit human
  review where required.
- Agent-facing instructions such as `CLAUDE.md`, PRDs, and implementation plans
  must remain prose mirrors or workflow guides. They must not become the source
  of truth for risk caps, broker state, or live execution settings.

### MCP Connectors

- MCP connectors are approved integration surfaces for systems such as GitHub,
  Google Drive, Slack, Jira/Confluence, email, calendar, or other external tools.
- Connector usage must be explicit at workflow edges: PRD authoring, ticketing,
  document access, reporting, operator notifications, or future adapter
  implementations that are intentionally connector-backed.
- Deterministic hot-path packages must not import connector-specific clients or
  assume connector availability.
- Connector results must be normalized into local typed models before entering
  signal, risk, backtest, learning, storage, or runtime decision code.
- Secrets, authorization headers, raw connector payloads, prompts, and account
  identifiers must not be stored in journals, SQLite tables, test fixtures, or
  serialized decisions unless a later security-reviewed PRD explicitly permits a
  specific safe field.

### SQLite

- SQLite is the default local durable store for MVP persistence.
- SQLite-backed storage should use explicit schema migrations or versioned
  initialization logic rather than ad hoc table creation scattered across
  modules.
- SQLite is appropriate for:
  - decision journals
  - scheduler run logs
  - provider/cache snapshots
  - backtest fixtures and results
  - settings snapshots
  - alert outbox or delivery audit records
- SQLite is not the broker source of truth, a secret store, or an unbounded raw
  provider-payload dump.
- SQLite access must remain behind storage interfaces where application code
  needs persistence. Pure domain logic should accept typed inputs rather than
  reaching into the database directly.
- Tests must be able to run against temporary SQLite databases without network
  access or local user secrets.

### Scheduler: cron

- cron-compatible scheduling is the default mechanism for recurring jobs.
- Scheduled jobs must invoke bounded CLI or module entrypoints, not infinite
  polling loops.
- Scheduled commands must be idempotent for a given run key, trading date, or
  request ID.
- Scheduled commands must emit clear exit codes:
  - `0` for successful completion or no-op
  - non-zero for actionable failure
- Scheduler implementations must include a lock or run-state guard to prevent
  overlapping executions of the same job.
- Scheduled jobs must respect existing execution-mode gates such as
  propose-only, paper, or live modes.
- Scheduler behavior must not bypass risk gates, broker source-of-truth checks,
  kill switches, daily halts, or preflight checks.

## Boundary Requirements

- `prescient.signal` and `prescient.risk` must remain deterministic and free of
  Claude Code, MCP connector, broker, scheduler, and SQLite runtime dependencies.
- Broker adapters must not depend on Claude Code or MCP connector tooling.
- Runtime/scheduler code may orchestrate adapters and storage, but it must not
  duplicate signal scoring, risk decisions, or broker-source-of-truth logic.
- Backtest and learning code may use SQLite fixtures or journals, but must not
  call live brokers, live providers, or connector-backed systems during tests.
- All connector, scheduler, and storage integration must be covered by boundary
  tests when implementation begins.

## Functional Requirements

### Stack Inventory

The project must have a documented stack inventory that names:

- supported Python version range
- `uv` as dependency/command runner
- primary test and lint commands
- storage backend defaults
- scheduler mechanism
- connector usage policy
- Claude Code usage policy

### Local Development

A new developer or agent must be able to:

- install/sync dependencies with `uv`
- run the full test suite with one `uv run pytest -q` command
- run lint with `uv run ruff check .`
- understand where SQLite state is stored in local/dev mode
- understand which scheduled commands cron should invoke

### Persistence

SQLite persistence must support deterministic local operation:

- schema initialization is repeatable
- writes are structured and typed at module boundaries
- database paths are configurable
- tests use temporary databases
- sensitive material is excluded from persisted records

### Scheduling

cron entries or cron-compatible wrappers must be documented with:

- command
- cadence
- expected mode
- lock/run key behavior
- log path or journal target
- failure handling expectation

### Connector Use

MCP connector usage must be documented per workflow:

- connector name
- purpose
- read/write capabilities
- local model or artifact produced from connector output
- safety boundary that prevents direct connector output from entering hot-path
  decision logic

## Acceptance Criteria

- A durable R10 PRD exists under `docs/prd/`.
- README or equivalent developer documentation names the consolidated stack.
- Future implementation plans use `uv run` verification commands by default.
- Boundary tests prevent deterministic layers from importing connector, Claude
  Code, scheduler, broker, or SQLite integration modules directly.
- SQLite storage tests use temporary databases and do not require network access.
- Scheduler tests prove jobs are bounded and do not contain infinite polling.
- Serialized records do not contain secrets, authorization headers, raw connector
  payloads, prompts, broker account identifiers, or live order credentials.

## Suggested Implementation Plan Inputs

An implementation plan for R10 should consider:

- adding a stack section to `README.md`
- adding or tightening dependency-manager checks around `pyproject.toml` and
  `uv.lock`
- adding SQLite storage-interface tests if local SQLite storage is not already
  covered
- adding scheduler boundary tests for cron-compatible commands
- adding connector boundary tests so deterministic layers cannot import MCP
  connector modules
- documenting sample cron entries without enabling live trading by default

## Verification

Recommended verification commands for an R10 implementation:

- `uv run pytest tests/test_data_boundaries.py tests/test_learning_boundaries.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
