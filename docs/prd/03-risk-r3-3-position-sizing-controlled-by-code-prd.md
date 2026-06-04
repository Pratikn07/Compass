# PRD: R3.3 Position Sizing Controlled By Code

## Ownership

Owner: Ours

Drafting support: Codex

## Objective

Create a deterministic position-sizing layer for `prescient` where code, not Claude, decides the maximum allowable trade quantity.

Position sizing must convert the risk cap from R3.2 into whole shares or whole option contracts using structured account and trade inputs. Claude may provide advisory analysis, but Claude must never choose quantity, position size, notional allocation, account allocation, or any risk override.

## Background

`prescient` now has a pure-code risk gatekeeper boundary from R3.1 and a product requirement for the R3.2 maximum per-trade loss cap.

R3.3 is the next risk component:

```text
candidate-ready strategy decision
  -> optional Claude analyst/sub-agent advisory review
  -> pure-code risk gatekeeper
  -> pure-code position sizing
  -> future broker adapter
```

R3.3 does not make a trade executable by itself. It produces an auditable sizing decision that later risk checks and future broker adapters can consume.

## Definitions

### Position Sizing

Position sizing is the code-owned calculation of how many shares or contracts may be used for a proposed trade while staying inside the configured risk budget.

### Risk Budget

The maximum dollar loss allowed for one trade.

For MVP, this comes from R3.2:

```text
risk_budget = account_equity * max_trade_loss_pct
```

The default product cap is 3% of account equity, subject to R3.2 review flags and ceiling validation.

### Unit Maximum Loss

The maximum loss for one smallest executable unit.

Examples:

- Stock: maximum loss for one share.
- Long option: maximum loss for one contract.

### Approved Quantity

The largest whole number of shares or contracts that fits inside the risk budget and available account constraints.

Approved quantity must always be rounded down. The system must never round up to make a trade possible.

### Sizing Decision

A structured, journal-safe output explaining whether the proposed trade can be sized, what quantity is allowed, and why a proposal was rejected or not evaluable.

This is not a broker order.

## Requirement

The risk layer must include a deterministic position-sizing component that controls trade quantity in code.

The sizing component must:

- Use only structured account, risk, and order-proposal inputs.
- Respect the R3.2 per-trade maximum-loss cap.
- Calculate quantity using conservative loss math.
- Round down to valid trade increments.
- Fail closed when required inputs are missing or invalid.
- Reject any Claude attempt to provide or override sizing.
- Produce deterministic, JSON-safe output.

## User Value

This protects the user from a high-conviction thesis becoming an oversized trade.

It provides:

- A hard separation between analyst judgment and account exposure.
- Clear quantity math for small accounts.
- Predictable rejection when even one contract or share block is too large.
- A reusable foundation for later broker execution.
- An audit trail for why a quantity was allowed, reduced, rejected, or not evaluable.

## Functional Requirements

### R3.3.1 Pure-Code Ownership

Position sizing must live under `prescient.risk`.

It must not import:

- `prescient.analyst`
- Anthropic or other LLM clients
- Broker adapters
- Runtime schedulers
- Event trigger handlers
- Network clients

It may use structured risk and signal models needed to identify the target, theme, expression, account snapshot, and order proposal.

### R3.3.2 Claude Cannot Size

Claude output must never be accepted as a quantity or sizing instruction.

The sizing layer must reject or block advisory payloads containing unsafe sizing or execution fields, including:

- `position_size`
- `order_quantity`
- `quantity`
- `contracts`
- `shares`
- `notional`
- `account_allocation`
- `portfolio_allocation`
- `broker_action`
- `risk_override`
- `execute_trade`

Claude may say "I prefer calls" or "avoid the setup" only through the existing analyst schema. It may not decide how many contracts, shares, or dollars to use.

### R3.3.3 Structured Inputs

The sizing layer should consume structured inputs equivalent to:

- Candidate or strategy decision identity: target, theme, strategy status.
- Account snapshot: equity, cash, buying power.
- Risk settings: max trade loss percentage, review flags, and cap validation from R3.2.
- Order proposal: expression, entry estimate, stop or maximum-loss model, and instrument metadata.

Required instrument data depends on expression:

- Stock sizing requires entry price and either stop price or maximum loss per share.
- Long option sizing requires entry premium and contract multiplier. If no valid stop model exists, maximum loss defaults to full premium paid.

If required data is missing, zero, negative, or internally inconsistent, sizing must return `not_evaluable` or `blocked`.

### R3.3.4 Quantity Calculation

The sizing algorithm must calculate the largest valid quantity that does not exceed the risk budget.

Required behavior:

- Compute risk budget from account equity and configured cap.
- Compute unit maximum loss.
- Compute raw quantity as `risk_budget / unit_max_loss`.
- Floor raw quantity to the valid trade increment.
- Reject if floored quantity is below the minimum valid trade unit.
- Compute projected maximum loss from floored quantity.
- Verify projected maximum loss is less than or equal to the risk budget.

The implementation must never round up.

### R3.3.5 Stock Sizing

For stock trades:

- Default minimum unit is 1 whole share.
- Fractional shares are out of scope unless a later broker/risk policy explicitly enables them.
- A valid stop or maximum-loss-per-share model is required.
- If no valid stop/loss model exists, sizing must fail closed.
- Buying power or cash constraints must be respected when present.

Example:

```text
account_equity = 5000
max_trade_loss_pct = 0.03
risk_budget = 150
unit_max_loss = 12
approved_quantity = floor(150 / 12) = 12 shares
projected_max_loss = 144
```

### R3.3.6 Option Sizing

For long option trades:

- Default minimum unit is 1 contract.
- Fractional contracts are not allowed.
- Contract multiplier defaults to 100 unless supplied by structured metadata.
- If no valid stop model exists, maximum loss must default to full premium paid.
- If one contract exceeds the risk budget, reject.
- Buying power or cash constraints must be respected when present.

Example:

```text
account_equity = 5000
max_trade_loss_pct = 0.03
risk_budget = 150
unit_max_loss = 60
approved_quantity = floor(150 / 60) = 2 contracts
projected_max_loss = 120
```

The system must not approve 3 contracts in this example because projected maximum loss would be 180.

### R3.3.7 Output Contract

The sizing decision must be structured and auditable.

It should include equivalent fields to:

- `target`
- `theme`
- `strategy_status`
- `expression`
- `sizing_status`: `sized`, `blocked`, or `not_evaluable`
- `account_equity`
- `risk_budget`
- `unit_max_loss`
- `approved_quantity`
- `projected_max_loss`
- `estimated_entry_cost`
- `cash_or_buying_power_required`
- `rejection_reasons`
- `warnings`
- `explanation`
- `claude_present`
- `claude_sizing_override_attempted`

Exact implementation names may differ, but the same information must be available for tests and future journal storage.

### R3.3.8 Rejection Reasons

The system must provide deterministic rejection reasons.

Required reasons:

- `strategy_not_candidate_ready`
- `missing_account_snapshot`
- `missing_order_proposal`
- `account_equity_missing`
- `risk_budget_missing`
- `entry_price_missing`
- `stop_price_missing`
- `unit_max_loss_missing`
- `unit_max_loss_invalid`
- `smallest_trade_exceeds_risk_budget`
- `insufficient_cash_or_buying_power`
- `unsupported_expression`
- `invalid_contract_multiplier`
- `quantity_not_integer`
- `max_loss_not_computable`
- `claude_sizing_override_attempted`

### R3.3.9 Integration With Risk Gatekeeper

Position sizing must not bypass the R3.1 gatekeeper.

Expected flow:

```text
StrategyDecision
  -> RiskGateDecision prerequisite checks
  -> PositionSizingDecision
  -> future R3 checks
  -> future final risk approval
  -> future broker adapter
```

A candidate-ready strategy decision is only eligible for sizing. It is not automatically executable.

If sizing fails, any later risk gate result must block broker execution.

### R3.3.10 Journal Safety

Sizing output must be safe to write to JSONL or a future journal database.

It must not include:

- API keys.
- Broker credentials.
- Full account identifiers.
- Raw Claude prompts.
- Raw Claude transcripts.
- Unbounded news or event payloads.

## Non-Functional Requirements

### Determinism

The same structured input must produce the same serialized sizing output.

### Safety

The default posture is reject or not evaluable when sizing math is incomplete.

### Testability

Sizing must be testable with mocked account snapshots and mocked order proposals.

No API keys, broker accounts, live market data, Claude calls, or network access are required.

### Maintainability

The sizing layer should be small and isolated so later R3 checks can add daily loss, max positions, concentration, market hours, and reward/risk without changing the sizing contract.

## Out Of Scope

R3.3 does not implement:

- Choosing the 3% cap value. That belongs to R3.2.
- Daily loss stop. That belongs to R3.4.
- Max open positions or concentration checks. That belongs to R3.5.
- Averaging-down or daily trade-count rules. That belongs to R3.6.
- Market-hours, spread, or reward/risk checks. That belongs to R3.7.
- Live broker account retrieval.
- Broker order placement.
- Portfolio optimization.
- Margin modeling.
- PDT or broker-specific day-trading enforcement.
- Legal, tax, or investment advice.

## Decision Flow

```text
candidate-ready strategy decision
  -> account snapshot present?
      no -> not_evaluable
  -> order proposal present?
      no -> not_evaluable
  -> Claude sizing override attempted?
      yes -> blocked
  -> risk budget computable?
      no -> not_evaluable
  -> unit maximum loss computable?
      no -> not_evaluable
  -> smallest unit fits risk budget?
      no -> blocked
  -> cash or buying power sufficient?
      no -> blocked
  -> floor quantity to valid increment
  -> emit sized decision
```

## Acceptance Criteria

- Position quantity is calculated by deterministic code only.
- Claude cannot supply or override quantity, contracts, shares, notional, allocation, or broker action.
- A `$5,000` account with a 3% cap produces a `$150` risk budget.
- A `$2,000` account with a 3% cap produces a `$60` risk budget.
- If option unit maximum loss is `$60` and risk budget is `$150`, approved quantity is 2 contracts.
- If option unit maximum loss is `$200` and risk budget is `$150`, the trade is rejected.
- If stock unit maximum loss is `$12` and risk budget is `$150`, approved quantity is 12 shares.
- If stock has no stop or maximum-loss-per-share model, sizing fails closed.
- Quantity is always rounded down.
- Sizing output includes risk budget, unit loss, approved quantity, projected max loss, and rejection reasons.
- Same input serializes to the same output.
- Sizing output is journal-safe.
- Tests require no live data, broker account, Claude call, or network access.
- Import-boundary tests prove `prescient.risk` does not import analyst, broker, Anthropic, runtime, event, scheduler, network, disk, or environment dependencies for sizing.

## Current Implementation Notes

The repo currently has an implemented `prescient.risk` package for R3.1.

Existing R3.1 behavior:

- Non-candidate strategy decisions are blocked.
- Candidate-ready decisions fail closed without structured account and order inputs.
- Unsafe Claude advisory fields are detected.
- Broker execution is never allowed unless code approves.

Existing `RiskOrderProposal` already contains `estimated_entry_cost` and `maximum_loss`, which can be extended or reused for R3.3 sizing.

R3.3 should build on the existing risk package instead of creating a separate execution or broker sizing path.

## Product FAQ

> Can Claude say how many contracts to buy?

No. Claude can give advisory analysis only. Quantity belongs to deterministic code.

> Does sizing mean the trade is approved?

No. Sizing only answers how large the trade may be if all other risk checks pass.

> What if the calculated quantity is zero?

Reject the trade. Do not round up.

> What if one option contract is too large for a small account?

Reject the trade. Do not use fractional contracts or override the cap.

> Does this place orders?

No. R3.3 produces structured sizing output only.
