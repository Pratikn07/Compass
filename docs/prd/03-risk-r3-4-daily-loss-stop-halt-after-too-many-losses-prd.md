# PRD: R3.4 Daily Loss Stop / Halt After Too Many Losses

## Summary

R3.4 adds a pure-code daily loss halt to `prescient.risk`. The system must block new risk for the rest of the trading day when realized daily losses exceed the configured limit or when too many losing trades occur.

MVP defaults:

- Daily realized-loss cap: `5%` of account equity.
- Max losing trades per day: `2`.
- PnL basis: realized closed-trade P&L only.
- Halt behavior: block entries and position increases, but allow exits, reductions, and cancellations.

## Requirement

The risk layer must include a deterministic daily halt check that Claude, sub-agents, strategy confidence, and broker adapters cannot override.

The check answers:

```text
Can this account take new risk today?
```

If the account is halted, no future broker adapter may submit a new entry order or risk-increasing order for the same trading day.

## Functional Requirements

### R3.4.1 Daily Risk State

The daily halt check must accept structured daily risk state:

- `account_equity`
- `trading_day`
- `realized_pnl`
- `losing_trade_count`
- optional `halted_until`
- optional prior halt reasons

The MVP input is a structured snapshot supplied by tests, paper runtime, or future broker/account adapters. R3.4 does not fetch live broker state.

### R3.4.2 Daily Halt Settings

The daily halt check must support deterministic settings:

- `max_daily_realized_loss_pct = 0.05`
- `max_losing_trades_per_day = 2`
- `halt_scope = "new_risk_only"`
- `allow_risk_reducing_actions = true`

### R3.4.3 Daily Halt Decision

The output must be structured, deterministic, and JSON-serializable.

It must include equivalent data to:

- `status`: `allowed` or `halted`
- `trading_day`
- `account_equity`
- `max_daily_loss_pct`
- `max_daily_loss_amount`
- `realized_pnl`
- `losing_trade_count`
- `halt_reasons`
- `allowed_actions`
- `blocked_actions`
- `broker_execution_allowed_for_new_risk`

### R3.4.4 Halt Reasons

Required halt reasons:

- `daily_loss_limit_exceeded`
- `too_many_losing_trades`
- `account_equity_missing`
- `daily_pnl_missing`
- `losing_trade_count_missing`
- `trading_day_missing`

Missing required state must fail closed as halted.

### R3.4.5 Action Policy

When halted, the system must block:

- New entries.
- Adds to existing positions.
- Opening option contracts.
- Risk-increasing replacement orders.

When halted, the system must still allow:

- Exits.
- Reductions.
- Cancellations.
- Risk-reducing orders.

The halt lasts until the next trading day unless a future broker/account-state PRD defines a stricter broker-provided halt window.

## Relationship To Existing R3 Work

- R3.1 owns the hard risk gatekeeper boundary.
- R3.2 owns max per-trade loss.
- R3.3 owns position sizing.
- R3.4 owns daily account-level halt state.
- R3.4 must not duplicate per-trade sizing math or target filters.
- R3.4 must live under `prescient.risk` and remain Claude-free, broker-free, network-free, deterministic, and JSON-serializable.

## Acceptance Criteria

- A `$5,000` account halts when realized daily P&L is `-$250` or worse.
- A `$2,000` account halts when realized daily P&L is `-$100` or worse.
- A second losing trade in the same trading day triggers a halt even if the dollar loss is below 5%.
- Positive or flat realized P&L with fewer than 2 losing trades allows new risk.
- Missing equity, trading day, realized P&L, or loss count fails closed.
- Halted decisions block new risk but allow exits/reductions/cancellations.
- Claude output cannot remove halt reasons or approve new risk.
- Identical input produces identical serialized output.
- Import-boundary tests prove `prescient.risk` does not import analyst, broker, runtime, scheduler, event, network, or live-data dependencies.

## Out Of Scope

R3.4 does not implement:

- Broker account sync.
- Live order placement.
- Unrealized P&L drawdown halts.
- Max open positions.
- Concentration checks.
- Market-hours checks.
- Reward/risk checks.
- Manual override workflows.

Those belong to later R3 broker/risk integration milestones.
