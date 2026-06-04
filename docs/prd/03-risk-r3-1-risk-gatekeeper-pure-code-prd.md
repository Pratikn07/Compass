# PRD: R3.1 Risk Gatekeeper In Pure Code

## Ownership

Owner: Ours

Drafting support: Codex

## Objective

Create a deterministic risk gatekeeper for `prescient` that Claude cannot override.

The risk gatekeeper is the required hard boundary between strategy analysis and any future broker/order layer. It must make explicit, structured allow/block decisions in code before any trade can be proposed for execution.

## Background

`prescient` currently has:

- A deterministic signal engine under `prescient.signal`.
- Optional Claude analyst and sub-agent review under `prescient.analyst`.
- Runtime orchestration under `prescient.runtime`.
- Placeholder folders for future `risk/` and `broker/` layers.

The current system can produce a `candidate_ready_for_analyst` decision and optional Claude analysis. It does not yet have an account-level risk gate, position sizing, daily stop, concentration check, broker execution, or order placement.

R3.1 establishes the risk boundary before any broker integration exists.

```text
deterministic strategy decision
  -> optional Claude analyst / sub-agent review
  -> pure-code risk gatekeeper
  -> future broker adapter
```

Claude may produce advisory analysis. Claude must never approve, bypass, size, or mutate the risk gatekeeper decision.

## Definitions

### Risk Gatekeeper

The risk gatekeeper is a pure-code decision layer under `prescient.risk`.

It evaluates structured inputs and returns a structured risk decision. It does not call Claude, broker APIs, live market data APIs, disk, environment variables, or network services.

### Risk Decision

A risk decision is the final code-owned gate before a future broker adapter can receive an order proposal.

Possible MVP statuses:

- `approved`: the structured input passed the currently implemented risk checks.
- `blocked`: the structured input failed one or more hard risk checks.
- `not_evaluable`: the gatekeeper could not evaluate because required structured risk data was missing.

### Risk Rejection Reason

A risk rejection reason is a stable machine-readable reason explaining why the gatekeeper blocked or could not evaluate the candidate.

Examples:

- `strategy_not_candidate_ready`
- `missing_account_snapshot`
- `missing_order_proposal`
- `claude_override_attempted`
- `risk_checks_not_implemented`

Later R3 requirements will add reasons for max trade risk, daily loss stop, max positions, concentration, market hours, liquidity, and reward/risk.

### Claude Override

A Claude override is any attempt by Claude output, analyst recommendation, sub-agent output, prompt text, or free-form reasoning to:

- Approve a risk decision.
- Increase position size.
- Ignore account limits.
- Bypass a blocked risk check.
- Convert analyst judgment into an executable order.
- Replace code-owned rejection reasons.

All such attempts must be ignored or blocked by code.

## Requirement

The system must include a pure-code risk gatekeeper that is mandatory before future broker execution.

The gatekeeper must:

- Accept only structured inputs.
- Return deterministic structured output.
- Be independent from Claude and broker adapters.
- Never let Claude mutate, approve, or override risk state.
- Produce journal-safe rejection reasons.
- Be testable without API keys, broker accounts, live data, or network calls.

## User Value

This protects the user from the most dangerous failure mode: a good-looking thesis becoming an uncontrolled trade.

It provides:

- A hard safety boundary before execution.
- A place for account-level rules that strategy logic does not own.
- An audit trail for why a candidate was allowed or blocked.
- Confidence that Claude is advisory only.
- A foundation for R3.2 through R3.8.

## Functional Requirements

### R3.1.1 Pure-Code Ownership

The risk gatekeeper must live under `prescient.risk`.

It must not import:

- `prescient.analyst`
- Anthropic or other LLM clients
- Broker adapters
- Network clients
- Runtime schedulers
- Event trigger handlers

It may import typed strategy/risk models when needed.

### R3.1.2 Mandatory Pre-Broker Boundary

Future order execution must require a passing risk decision before reaching broker adapters.

For this milestone, broker execution is still out of scope. The requirement is to establish the code boundary and test it.

The intended future flow is:

```text
StrategyDecision(candidate_ready_for_analyst)
  -> optional ClaudeAnalysisResult
  -> RiskGateDecision(approved)
  -> future broker proposal/execution
```

If risk status is `blocked` or `not_evaluable`, no future broker adapter may receive an executable order.

### R3.1.3 Candidate-Ready Prerequisite

The risk gatekeeper must only consider candidate-ready strategy decisions.

If `StrategyDecision.status` is rejected or no-trade, the risk decision must be blocked with `strategy_not_candidate_ready`.

Claude analysis must not change this.

### R3.1.4 Structured Inputs Only

The gatekeeper may receive structured data such as:

- `StrategyDecision`
- `CandidateBrief`
- Account snapshot
- Existing positions snapshot
- Open orders snapshot
- Order proposal
- Market session snapshot
- Prior trade/day-loss summary
- Claude analysis result as advisory metadata only

The gatekeeper must not receive:

- Raw Claude transcripts
- Free-form prompts
- Broker credentials
- Environment variables
- Unbounded news documents
- Raw order instructions from Claude

### R3.1.5 Claude Cannot Override

Claude output must never be able to:

- Change `RiskGateDecision.status`.
- Remove rejection reasons.
- Increase allowed exposure.
- Approve missing required risk data.
- Convert a blocked decision into an approved decision.
- Submit or authorize orders.

If a structured Claude result contains unsafe fields such as `position_size`, `order_quantity`, `broker_action`, `risk_override`, or `execute_trade`, the risk gatekeeper must block with `claude_override_attempted`.

### R3.1.6 Deterministic Output

Given the same structured input, the risk gatekeeper must return the same serialized output.

The output must include:

- Target ticker.
- Strategy status.
- Risk status.
- Rejection reasons.
- Human-readable explanation.
- Whether broker execution is allowed.
- Whether Claude was present.
- Whether a Claude override attempt was detected.

### R3.1.7 Fail Closed

The gatekeeper must fail closed.

Missing required risk inputs must produce `not_evaluable` or `blocked`, not approval.

For R3.1, because detailed sizing/account checks belong to R3.2 and later, candidate-ready trades should not automatically become executable. The gatekeeper may return `not_evaluable` until an explicit structured account/order snapshot is supplied and implemented checks pass.

### R3.1.8 Journal Safety

Risk decisions must be safe to write to JSONL or a future journal database.

Risk decision output must not include:

- Secrets.
- API keys.
- Broker credentials.
- Full account identifiers.
- Raw Claude prompts or transcripts.

## Non-Functional Requirements

### Safety

The default posture is deny unless code can explicitly approve.

### Reproducibility

Risk checks must be deterministic and unit-testable.

### Maintainability

R3.1 should be a narrow boundary milestone. R3.2 through R3.8 should add specific checks without changing the core principle that risk is code-owned.

### Security

No secrets or credentials are accepted or emitted by the risk gatekeeper.

## Out Of Scope

R3.1 does not implement:

- Max 3% per-trade sizing.
- Position sizing formulas.
- Daily loss stop.
- Max open positions.
- Correlation or concentration checks.
- Auto-averaging-down checks.
- Unlimited daily trade checks.
- Market-hours validation.
- Reward/risk validation.
- Live account adapters.
- Broker execution.
- Order placement.
- UI controls.

These belong to R3.2 through R3.8 and broker/risk integration milestones.

## Decision Flow

```text
StrategyDecision
  -> rejected/no_trade
      -> RiskGateDecision(blocked, strategy_not_candidate_ready)

StrategyDecision(candidate_ready_for_analyst)
  -> no structured risk/account/order inputs
      -> RiskGateDecision(not_evaluable, missing_required_risk_inputs)

StrategyDecision(candidate_ready_for_analyst)
  -> Claude tries to provide size/order/risk override
      -> RiskGateDecision(blocked, claude_override_attempted)

StrategyDecision(candidate_ready_for_analyst)
  -> structured risk inputs pass implemented checks
      -> RiskGateDecision(approved)
```

## Acceptance Criteria

- `prescient.risk` exists as a pure-code package.
- Risk gatekeeper can evaluate structured strategy decisions without Claude, broker, live data, or network calls.
- Rejected/no-trade strategy decisions are blocked.
- Candidate-ready decisions are not automatically executable without risk inputs.
- Claude analysis can be attached as advisory metadata but cannot approve or override risk.
- Unsafe Claude fields cause a blocked risk decision.
- Missing required risk data fails closed.
- Same input serializes to the same risk decision output.
- Risk output is journal-safe.
- Tests require no API keys, broker account, or live market data.
- Import-boundary tests prove `prescient.risk` does not import `prescient.analyst`, `anthropic`, broker adapters, or network clients.

## Current Implementation Notes

The current repo has a `src/prescient/risk/` folder but no implemented risk gatekeeper files.

Existing target filters already check some pre-trade market constraints:

- Average daily volume.
- Extreme illiquidity.
- Pre-earnings run-up.
- Conflicting news.
- Invalidating target events.
- Options bid/ask spread and open interest.

R3.1 should not duplicate those filters. It should establish the account/order risk boundary that later R3 requirements will extend.

## Product FAQ

> Can Claude approve a trade if the risk gate blocks it?

No. Claude is advisory only.

> Can Claude choose position size?

No. Position sizing belongs to pure code in later R3 milestones.

> Can a candidate-ready strategy decision skip risk checks?

No. Candidate-ready means “eligible for review,” not “executable.”

> Does R3.1 place trades?

No. R3.1 only defines and implements the hard risk gate boundary.

> Why fail closed?

Because missing account/risk data is not a reason to trade. The system should block or mark the decision not evaluable until code has enough structured information to approve.
