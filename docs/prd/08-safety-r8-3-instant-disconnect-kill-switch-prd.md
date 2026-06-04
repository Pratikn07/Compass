# PRD: R8.3 Instant Disconnect / Kill Switch

## Ownership

Owner: Ours

Source note: Requirement from Ours safety phase: the user must be able to instantly disconnect the system and activate a kill switch that blocks all new risk.

## Objective

Add a durable emergency kill switch that immediately prevents `prescient` from sending any new risk-increasing broker command, attempts to cancel open orders when requested, and records an auditable emergency state.

R8.3 answers:

```text
How can the user immediately stop the system from creating or increasing live risk, even if a scheduled run, event trigger, broker adapter, or future automation is active?
```

The kill switch must be stronger than execution mode, analyst output, learning settings, and runtime scheduling. When active, it fails closed.

## Background

Earlier PRDs define safety layers:

- R3 risk gates block invalid sizing, concentration, daily loss, and execution-quality conditions.
- R5.4 centralizes `paper | propose_only | live` execution mode.
- R5.5 makes the broker the source of truth for account state.
- R5.6 performs immediate buying-power preflight before order submission.
- R6 journaling records decisions and outcomes.
- R6.2 learning cannot change broker mode or risk limits.

Those controls reduce ordinary execution risk, but they do not provide one operator action that globally stops execution. A real system needs an emergency stop for cases such as:

- Unexpected live-mode configuration.
- Runaway scheduling or repeated event triggers.
- Bad data provider output causing many candidate proposals.
- Broker state divergence or API instability.
- User wants to pause all trading immediately.
- User sees an order they do not recognize and wants all new risk blocked.

R8.3 adds a top-level emergency control that is checked before every broker write and before any runtime path can create new risk.

## Requirement

The system must support an instant kill switch that:

- Can be activated by a single local command or control-plane action.
- Persists an active emergency state until explicitly reset.
- Blocks all new entries, position adds, risk-increasing replacement orders, and any future broker write that can increase exposure.
- Allows defensive actions needed to reduce risk, especially cancelling open orders.
- Optionally attempts best-effort cancellation of all open broker orders.
- Prevents LLMs, learning loops, runtime settings, broker adapters, and execution mode from overriding the active switch.
- Produces journal-safe emergency records for activation, cancellation attempts, blocked orders, and reset.

For MVP, the kill switch does not automatically liquidate or flatten open positions. Forced liquidation is a separate higher-risk capability because market orders can create additional harm under bad liquidity, wrong account state, or partial outages.

## Definitions

### Kill Switch

A durable emergency state that blocks all new risk-increasing actions across runtime and broker execution paths.

### Instant Disconnect

The user-facing emergency action that activates the kill switch and transitions the system into a disconnected execution posture. "Disconnect" means the system must stop sending new order-placement requests. It may still perform read-only broker queries and defensive cancellations.

### Defensive Action

An action that reduces or prevents additional exposure:

- Cancel open order.
- Cancel replace request before submission.
- Exit, reduce, or close position when a later explicit flattening PRD authorizes it.
- Read account, position, or order state.

For R8.3 MVP, cancellation is the only broker write that remains allowed while the kill switch is active.

### Risk-Increasing Action

An action that can create or increase exposure:

- New entry.
- Add to an existing position.
- Open option contract.
- Risk-increasing replacement order.
- Any future broker write that can increase quantity, notional exposure, margin use, or maximum loss.

### Durable Active State

A persisted state outside process memory that survives process restarts. MVP may use a local file sentinel or JSON state file. Future deployments may use Supabase or a control-plane database behind the same interface.

## User Value

R8.3 gives the user:

- One emergency stop that is easier and safer than editing config during a live incident.
- Protection against accidental live execution.
- Protection against scheduled or event-driven loops continuing to place orders.
- A clear audit trail of who activated the switch, why, and what actions were blocked.
- Best-effort open-order cancellation without automatic liquidation.
- Confidence that LLMs, learning, and strategy code cannot bypass the stop.

## Functional Requirements

### R8.3.1 Global Emergency State

The system must define a structured kill-switch state.

Expected model:

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class KillSwitchStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class KillSwitchActivationSource(StrEnum):
    CLI = "cli"
    API = "api"
    ENVIRONMENT = "environment"
    FILE_SENTINEL = "file_sentinel"
    TEST = "test"


class KillSwitchState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: KillSwitchStatus
    activated_at: datetime | None = None
    activated_by: str | None = None
    activation_source: KillSwitchActivationSource | None = None
    reason: str | None = None
    reset_at: datetime | None = None
    reset_by: str | None = None
    reset_reason: str | None = None
    state_version: int = 1
    warnings: list[str] = Field(default_factory=list)
```

When `status == active`, the system must block new risk regardless of execution mode.

### R8.3.2 Durable Activation

Activation must persist outside process memory.

MVP acceptable storage:

- `PRESCIENT_KILL_SWITCH=1` environment variable for process startup.
- Local JSON state file, for example `.prescient/kill-switch.json`.
- Local sentinel file, for example `.prescient/KILL_SWITCH_ACTIVE`.

Activation through a file or CLI must be atomic enough that another process cannot observe a partially written state.

The state must remain active across restarts until explicitly reset.

### R8.3.3 Check Before Every Broker Write

Every broker write path must check the kill switch immediately before sending a command to the concrete broker adapter.

For MVP, the required enforcement point is a broker wrapper, such as:

```python
from typing import Protocol

from prescient.broker.interfaces import BrokerAdapter
from prescient.broker.models import BrokerExecutionError, OrderExecutionResult
from prescient.risk.models import RiskOrderProposal


class KillSwitchProvider(Protocol):
    def read_state(self) -> KillSwitchState:
        ...


class KillSwitchBrokerWrapper:
    def __init__(self, inner: BrokerAdapter, provider: KillSwitchProvider) -> None:
        self._inner = inner
        self._provider = provider

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        state = self._provider.read_state()
        if state.status == KillSwitchStatus.ACTIVE:
            raise BrokerExecutionError("Kill switch active: order placement blocked.")
        return self._inner.place_order(proposal)

    def cancel_order(self, order_id: str) -> None:
        return self._inner.cancel_order(order_id)
```

The wrapper must sit outside concrete broker adapters so it protects Alpaca, Robinhood, mock adapters, and future brokers uniformly.

### R8.3.4 Runtime-Level Check

Runtime orchestration must check the kill switch before any step that can produce a broker write.

When the switch is active, runtime must:

- Skip new order placement.
- Skip risk-increasing replacement orders.
- Return a structured kill-switch-blocked result.
- Journal the blocked decision.
- Avoid falling back to a different broker adapter, execution mode, or local simulated state.

The runtime may still run read-only signal analysis, journal summaries, or account-state inspection, but no new risk may be transmitted.

### R8.3.5 Defensive Cancellation

The kill switch must support an optional best-effort cancel-open-orders action.

Expected flow:

```text
activate kill switch
  -> persist active state
  -> block new risk immediately
  -> optionally get open orders from broker
  -> attempt cancel_order(order_id) for each open order
  -> journal cancellation result for each order
  -> keep kill switch active
```

Cancellation behavior:

- If broker read fails, keep the kill switch active and record `open_order_query_failed`.
- If a cancellation fails, keep the kill switch active and record `cancel_failed`.
- If some cancellations succeed and some fail, record partial success.
- Do not retry indefinitely inside the emergency action.
- Do not place offsetting trades to compensate for failed cancellations.

### R8.3.6 No Automatic Liquidation In MVP

R8.3 must not automatically submit sell orders, market orders, option closes, or position-flattening orders.

Reason:

- Liquidation can increase harm under poor liquidity.
- Position close logic needs instrument-specific behavior.
- Broker state may be stale or unreachable during the same incident.
- The user's emergency intent may be to stop new orders, not to exit existing positions.

A future PRD may define an explicit `flatten_all_positions` capability with additional confirmations and broker-specific execution rules.

### R8.3.7 Reset Requires Explicit User Action

The kill switch must not auto-reset.

Reset must require:

- Explicit user/admin action.
- Reset reason.
- Reset actor or source.
- Journal record.

Reset must not cancel prior audit records. It only changes future execution permission.

### R8.3.8 Precedence Over Execution Mode

Kill-switch state has higher precedence than execution mode.

Behavior matrix:

| Kill Switch | Execution Mode | New Orders | Cancel Orders | Broker Reads |
| --- | --- | --- | --- | --- |
| inactive | propose_only | blocked by propose-only | allowed | allowed |
| inactive | paper | allowed after risk/preflight | allowed | allowed |
| inactive | live | allowed after live guardrails | allowed | allowed |
| active | propose_only | blocked by kill switch | allowed | allowed |
| active | paper | blocked by kill switch | allowed | allowed |
| active | live | blocked by kill switch | allowed | allowed |

The kill switch must block new orders even in paper mode so tests and operator behavior match production safety semantics.

### R8.3.9 No LLM Or Learning Override

Claude, Gemini, sub-agents, learning loops, analyst confidence, strategy score, or generated recommendations must not reset, weaken, ignore, or bypass the kill switch.

The following must be forbidden:

- LLM output that sets kill-switch state.
- Learning overlay that resets kill-switch state.
- Strategy decision field that enables broker writes while active.
- Broker adapter fallback when a wrapper blocks execution.

### R8.3.10 Journal-Safe Emergency Audit

Every activation, blocked write, cancellation attempt, cancellation result, and reset must be journal-safe.

Expected model:

```python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class KillSwitchEventType(StrEnum):
    ACTIVATED = "activated"
    BLOCKED_ORDER = "blocked_order"
    CANCEL_ATTEMPTED = "cancel_attempted"
    CANCEL_SUCCEEDED = "cancel_succeeded"
    CANCEL_FAILED = "cancel_failed"
    RESET = "reset"


class KillSwitchEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: KillSwitchEventType
    created_at: datetime
    run_id: str | None = None
    actor: str | None = None
    source: KillSwitchActivationSource
    reason: str | None = None
    order_id: str | None = None
    target: str | None = None
    broker: str | None = None
    message: str
    warnings: list[str] = Field(default_factory=list)
```

The event must not include:

- API keys.
- Broker credentials.
- Account identifiers.
- Full raw broker responses.
- Raw stack traces.
- LLM prompts or responses.

### R8.3.11 Operator Interface

MVP must expose a local programmatic interface equivalent to:

```python
def activate_kill_switch(
    *,
    reason: str,
    actor: str,
    source: KillSwitchActivationSource,
    cancel_open_orders: bool = False,
) -> KillSwitchActivationResult:
    ...


def reset_kill_switch(
    *,
    reason: str,
    actor: str,
    source: KillSwitchActivationSource,
) -> KillSwitchState:
    ...


def get_kill_switch_state() -> KillSwitchState:
    ...
```

A CLI command is recommended for MVP:

```bash
prescient kill-switch activate --reason "unexpected live activity" --cancel-open-orders
prescient kill-switch status
prescient kill-switch reset --reason "manual review complete"
```

If CLI routing does not exist yet, the implementation may expose the service functions first and add CLI wiring in the next implementation slice.

### R8.3.12 Fail-Closed Error Handling

If kill-switch state cannot be read at an enforcement point, broker writes must be blocked.

Examples:

- State file unreadable.
- JSON corrupted.
- State provider unavailable.
- Environment variable indicates active but file state says inactive.
- Multiple state sources disagree.

When sources disagree, active wins.

### R8.3.13 Multi-Process Behavior

The kill switch must be safe when more than one scheduled run or process may exist.

MVP requirements:

- Enforcement reads the durable state immediately before broker write.
- Activation writes the durable state atomically.
- Reset writes the durable state atomically.
- No process-local cached inactive state may authorize a broker write.

This does not require distributed locking for MVP, but the state interface should allow future database-backed locking.

### R8.3.14 Import Boundaries

The kill-switch state and broker wrapper may live under `prescient.broker` or a dedicated `prescient.safety` package.

The deterministic layers must not depend on broker execution code:

- `prescient.signal` must not import kill-switch broker wrappers.
- `prescient.risk` must not call broker APIs or read kill-switch files directly.
- `prescient.learning` must not reset or modify kill-switch state.

Runtime and broker wrappers own enforcement.

## Technical Architecture

Recommended package layout:

```text
src/prescient/safety/
  __init__.py
  kill_switch.py
  models.py

src/prescient/broker/
  execution_guard.py  # add KillSwitchBrokerWrapper or compose with existing wrappers
```

Recommended enforcement order:

```text
runtime trigger
  -> read kill-switch state
    -> active: skip broker write and journal blocked result
    -> inactive: proceed to risk/preflight
      -> broker wrapper reads kill-switch state again
        -> active: block place_order
        -> inactive: delegate to inner adapter
```

This double check prevents a race where the switch activates after runtime starts but before broker submission.

## Non-Functional Requirements

### Latency

Activation must take effect before the next broker write attempt. The system cannot guarantee reversal of an order already transmitted to the broker, but it must attempt cancellation when requested.

### Durability

The active state must survive process restarts.

### Determinism

Given the same kill-switch state and order proposal, enforcement must always return the same allow/block decision.

### Reliability

State-read failures must block broker writes. Cancellation failures must not reset the switch.

### Security

Only local trusted operators or an authenticated future control plane may activate or reset the switch. R8.3 does not require full user-account RBAC, but the model must preserve actor/source fields for audit.

### Testability

Tests must run with mock providers and mock brokers. No live broker account, API key, network access, Claude call, Gemini call, or market data provider is required.

## Acceptance Criteria

R8.3 is complete when:

- A durable kill-switch state model exists.
- The system can activate, read, and reset the switch through a local service interface.
- Active state survives process restart when using the MVP file provider.
- Broker order placement is blocked when the kill switch is active.
- Broker order placement fails closed when state cannot be read.
- Defensive `cancel_order` remains allowed while the switch is active.
- Optional cancel-open-orders flow attempts to cancel all open broker orders and journals per-order results.
- Runtime checks the switch before any order placement path.
- Broker wrapper checks the switch immediately before delegating `place_order`.
- Kill-switch active state overrides `paper`, `propose_only`, and `live` execution modes.
- Learning overlays, analyst outputs, and strategy decisions cannot reset or override the switch.
- Reset requires explicit actor and reason.
- Activation, blocked order, cancel attempt/result, and reset events are journal-safe.
- Tests verify active, inactive, unreadable-state, cancel-success, cancel-failure, and reset behavior.
- Boundary tests verify `prescient.signal`, `prescient.risk`, and `prescient.learning` do not import broker kill-switch wrappers or perform broker writes.

## Non-Goals

R8.3 does not require:

- Automatic liquidation or flattening of open positions.
- Market-order emergency exits.
- Broker-specific order-replacement logic.
- Distributed locking across machines.
- Full RBAC or web UI.
- Mobile push controls.
- SMS or phone-call emergency controls.
- Changing execution mode automatically.
- Modifying risk limits.
- LLM-triggered emergency actions.
- Backtesting kill-switch behavior.

## Open Questions

- Should a later PRD add a separate `flatten_all_positions` command with multiple confirmations?
- Should reset require a second confirmation in live mode?
- Should future deployments store kill-switch state in Supabase instead of the local filesystem?
- Should an active kill switch also pause scheduled runs entirely, or only block broker-write stages?

## Product FAQ

### Does the kill switch sell all open positions?

No. R8.3 blocks new risk and can cancel open orders. It does not automatically liquidate positions.

### Can the system keep analyzing while the switch is active?

Yes, read-only analysis may continue. Broker writes that increase risk are blocked.

### Can an LLM or learning overlay turn the switch off?

No. Only an explicit reset action with actor and reason can reset it.

### What happens if the kill-switch file is corrupted?

The system fails closed. Broker writes are blocked until the state is repaired or reset through a valid control path.

### What if an order was already sent before activation?

R8.3 cannot unsend an already transmitted order. If requested, it attempts to cancel open orders and records the result.
