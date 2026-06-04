# PRD: R3.6 No Auto-Averaging-Down / No Unlimited Daily Trades

## Ownership

Owner: Ours

Source note: Requirement from GPT risk review: do not allow auto-averaging-down, revenge trading, or unlimited daily trade churn.

## Objective

Add a deterministic trade-activity guard to `prescient.risk` that blocks two dangerous behaviors:

- Auto-averaging-down: adding risk to a losing or adverse same-ticker position.
- Unlimited daily trades: continuing to open new risk after a configured daily trade count limit.

R3.6 answers:

```text
Can this account take another risk-increasing trade action today?
```

This is a pure-code safety gate. Claude, sub-agents, strategy conviction, broker adapters, and user-facing thesis text cannot override it.

## Background

R3.1 established the pure-code risk gatekeeper boundary.
R3.2 added a per-trade maximum defined-loss cap.
R3.3 added code-owned position sizing.
R3.4 added a daily realized-loss halt.
R3.5 added max open-position and concentration controls.

R3.6 adds trade-behavior controls. Even if a trade fits the per-trade cap, position size, daily loss limit, and concentration limit, the system still must not keep adding to losing trades or repeatedly opening new risk throughout the day.

The target account size is small, roughly `$2,000` to `$5,000`, so churn control matters. A sequence of small trades can still create large realized losses, emotional overtrading, settlement issues, or broker restrictions.

## Requirement

The risk layer must block risk-increasing trade actions when:

- The proposed action would add risk to a losing same-ticker position.
- The proposed action would add risk to a position with missing adverse-move data.
- The configured daily new-risk trade limit has already been reached.
- The proposed ticker has already had the maximum allowed same-day new-risk actions.
- Required structured daily activity state is missing or not evaluable.

Risk-reducing actions must remain allowed unless a later broker or compliance layer says otherwise.

## Definitions

### Risk-Increasing Trade Action

Risk-increasing actions include:

- New entries.
- Adds to existing positions.
- Opening option contracts.
- Risk-increasing replacement orders.
- Re-entering the same ticker after an earlier same-day exit.

Risk-reducing actions include:

- Exits.
- Reductions.
- Cancellations.
- Risk-reducing replacement orders.

R3.6 should use or align with the existing `DailyRiskAction` model from R3.4.

### Auto-Averaging-Down

Auto-averaging-down is any code-driven attempt to add risk to a same-ticker position after the position has moved against the account.

For MVP, a same-ticker add must be blocked when any supplied structured field indicates the current position is losing or adverse:

- `current_unrealized_pnl < 0`
- `price_vs_average_entry_pct < 0` for a bullish/long position
- `current_mark < average_entry_price` for a bullish/long stock position
- `current_option_mark < average_option_entry_price` for a long option position

If the system cannot determine whether the position is losing because required same-ticker position data is missing, it must fail closed for risk-increasing adds.

### Daily New-Risk Trade Count

Daily new-risk trade count is the number of risk-increasing trade actions already accepted for the same trading day.

Risk-reducing exits, reductions, cancellations, and defensive orders must not consume the daily new-risk trade count.

### Same-Ticker Daily Trade Count

Same-ticker daily trade count is the number of risk-increasing actions already accepted for one ticker on the same trading day.

This prevents repeated same-day attempts to enter, exit, and re-enter the same idea.

### Day Trade Regulatory State

Broker and regulatory day-trading rules are not the same as the internal R3.6 daily trade limit.

As of the current design phase in June 2026, public investor guidance says day-trading margin requirements are changing. Investor.gov states that new intraday margin requirements become effective June 4, 2026, with a broker transition period until October 20, 2027. Broker firms may continue operating under old rules during the transition or migrate sooner.

Therefore, R3.6 must not hard-code a single static pattern-day-trader rule. Broker-specific day-trade status belongs to a future broker/account adapter.

R3.6 still enforces the app's own conservative internal daily trade limits.

Sources:

- [FINRA Day Trading](https://www.finra.org/investors/investing/investment-products/stocks/day-trading)
- [Investor.gov Pattern Day Trader](https://www.investor.gov/introduction-investing/investing-basics/glossary/pattern-day-trader)

## MVP Defaults

The default MVP policy should be conservative:

- `max_new_risk_trades_per_day = 3`
- `absolute_max_new_risk_trades_per_day = 5`
- `max_same_ticker_new_risk_trades_per_day = 1`
- `block_averaging_down = true`
- `allow_risk_reducing_actions = true`
- `broker_day_trade_state_required = false`

Rationale:

- Three new-risk actions is enough for the earnings-read-through MVP without allowing unlimited intraday churn.
- The absolute ceiling of five exists for future review but must not be the default.
- Same-ticker re-entry should be blocked by default because it is usually the same thesis being retried.
- Broker day-trade state is not required for MVP unit tests because live broker integration is not implemented yet.

## Functional Requirements

### R3.6.1 Pure-Code Ownership

The trade-activity guard must live under `prescient.risk`.

It must not:

- Call Claude.
- Import `prescient.analyst`.
- Import broker adapters.
- Fetch live data.
- Place orders.
- Read environment variables.
- Accept risk override fields from Claude.

### R3.6.2 Structured Inputs

The check must accept structured inputs equivalent to:

- Proposed target ticker.
- Proposed action.
- Proposed expression.
- Proposed direction.
- Trading day.
- Daily new-risk trade count.
- Same-ticker daily new-risk trade counts.
- Existing same-ticker position snapshot, when any.
- Existing same-ticker realized/unrealized PnL, when available.
- Existing same-ticker average entry and current mark, when available.
- Risk settings.

Optional future inputs:

- Broker day-trade count.
- Broker day-trade buying power.
- Broker account restriction flags.
- Rolling five-business-day day-trade count.
- Settlement or cash-available state.

Missing optional broker fields may produce warnings. Missing required internal activity fields must fail closed.

### R3.6.3 No Auto-Averaging-Down

The system must block risk-increasing same-ticker adds when the current same-ticker position is losing or adverse.

Required behavior:

- If no same-ticker position exists, this check does not block the first entry.
- If a same-ticker position exists and the proposed action increases risk, evaluate adverse-position data.
- If supplied data shows the position is losing or below entry, block.
- If required same-ticker adverse-position data is missing, return `not_evaluable` or `blocked`.
- If the action is risk-reducing, allow it through this check.

R3.6 does not need to distinguish "averaging down" from "pyramiding up" for MVP execution. Default policy may block all same-ticker risk-increasing adds unless future settings explicitly allow pyramiding winners.

### R3.6.4 No Unlimited Daily Trades

The system must block new risk when the daily new-risk trade count is greater than or equal to `max_new_risk_trades_per_day`.

Default:

```text
max_new_risk_trades_per_day = 3
```

Any configured value above `absolute_max_new_risk_trades_per_day = 5` must be rejected or marked invalid.

Risk-reducing actions must not be blocked by this limit.

### R3.6.5 Same-Ticker Daily Limit

The system must block risk-increasing actions when the same ticker has already reached `max_same_ticker_new_risk_trades_per_day`.

Default:

```text
max_same_ticker_new_risk_trades_per_day = 1
```

This prevents repeated same-day re-entry into the same thesis after a stop, exit, rejection, or failed setup.

### R3.6.6 Broker Day-Trade Awareness

R3.6 must support future broker day-trade state, but MVP must not require live broker data.

When broker day-trade state is supplied, the output should preserve it for audit. When it is missing, the system may emit a warning such as `broker_day_trade_state_missing`.

R3.6 must not claim legal compliance with FINRA, SEC, or broker-specific day-trading rules. Future broker integration must consume broker-provided restrictions and account capabilities directly.

### R3.6.7 Output Contract

The trade-activity decision must be structured, deterministic, and journal-safe.

It should include equivalent fields to:

- `status`: `allowed`, `blocked`, or `not_evaluable`
- `target`
- `trading_day`
- `proposed_action`
- `daily_new_risk_trade_count`
- `max_new_risk_trades_per_day`
- `same_ticker_new_risk_trade_count`
- `max_same_ticker_new_risk_trades_per_day`
- `same_ticker_position_present`
- `same_ticker_position_is_losing`
- `rejection_reasons`
- `warnings`
- `allowed_actions`
- `blocked_actions`
- `broker_execution_allowed_for_new_risk`

### R3.6.8 Rejection Reasons

Required rejection reasons:

- `daily_trade_limit_reached`
- `absolute_daily_trade_limit_exceeded`
- `same_ticker_daily_trade_limit_reached`
- `averaging_down_blocked`
- `same_ticker_position_state_missing`
- `position_pnl_missing`
- `average_entry_missing`
- `current_mark_missing`
- `target_missing`
- `trading_day_missing`
- `daily_trade_count_missing`
- `same_ticker_trade_count_missing`
- `invalid_daily_trade_limit_setting`
- `invalid_same_ticker_limit_setting`
- `unsupported_action`

### R3.6.9 Warnings

Required warnings:

- `broker_day_trade_state_missing`
- `broker_day_trade_policy_unknown`
- `same_ticker_position_mark_missing`
- `same_ticker_position_pnl_missing`
- `risk_reducing_action_allowed`

Warnings must not allow a blocked decision to become allowed.

### R3.6.10 Action Policy

When blocked, the system must block:

- New entries.
- Adds to existing positions.
- Opening option contracts.
- Risk-increasing replacement orders.
- Same-day same-ticker re-entry.

When blocked, the system must still allow:

- Exits.
- Reductions.
- Cancellations.
- Risk-reducing orders.

## Relationship To Existing R3 Work

- R3.1 owns the hard risk gatekeeper boundary.
- R3.2 owns per-trade max loss.
- R3.3 owns position sizing.
- R3.4 owns daily realized-loss and losing-trade halt state.
- R3.5 owns open-position count and concentration.
- R3.6 owns same-day trade behavior: no averaging down and no unlimited new-risk actions.

R3.6 must consume or align with R3.4 `DailyRiskAction` concepts.

R3.6 must not duplicate:

- Per-trade sizing math from R3.3.
- Concentration checks from R3.5.
- Daily loss halt calculations from R3.4.
- Broker-specific day-trade compliance from future broker adapters.

## Acceptance Criteria

- A fourth new-risk action is blocked when `max_new_risk_trades_per_day = 3`.
- A configured daily new-risk limit above `5` is invalid.
- Risk-reducing exits, reductions, and cancellations remain allowed even when the daily trade limit is reached.
- A same-ticker add is blocked when current unrealized PnL is negative.
- A same-ticker add is blocked when current mark is below average entry for a bullish/long position.
- A same-ticker risk-increasing action is blocked after one same-day same-ticker new-risk action by default.
- Missing trading day, daily count, same-ticker count, target, or required same-ticker position state fails closed.
- Broker day-trade state can be absent in MVP but must produce an audit warning when relevant.
- Claude cannot remove trade-activity rejection reasons or approve new risk.
- Same input serializes to the same output.
- Tests require no live data, broker account, Claude call, or network access.
- Import-boundary tests prove `prescient.risk` does not import analyst, broker, runtime, scheduler, event, network, or live-data dependencies for trade-activity checks.

## Out Of Scope

R3.6 does not implement:

- Live broker account sync.
- Live order placement.
- Legal day-trading compliance decisions.
- Real-time settlement or cash-available calculations.
- PDT or new intraday margin rule enforcement.
- Wash sale or tax logic.
- Portfolio concentration. That belongs to R3.5.
- Daily realized-loss halt. That belongs to R3.4.
- Market-hours, spread, and reward/risk checks. Those belong to R3.7.
- Manual override workflows.
- Legal, tax, or investment advice.

## Decision Flow

```text
proposed trade action
  -> risk-reducing action?
      yes -> allowed by R3.6
  -> required activity state present?
      no -> not_evaluable
  -> settings valid?
      no -> blocked or not_evaluable
  -> daily new-risk count below max?
      no -> blocked
  -> same-ticker daily count below max?
      no -> blocked
  -> same-ticker position exists?
      no -> allowed by R3.6
  -> proposed action increases same-ticker risk?
      no -> allowed by R3.6
  -> position losing or adverse?
      yes -> blocked
  -> position state missing?
      yes -> not_evaluable
  -> emit allowed trade-activity decision
```

## Product FAQ

> Is averaging down ever allowed?

Not in MVP. The system should not add risk to a losing same-ticker position.

> Does this mean winners can be pyramided?

Not by default. Future settings may allow controlled pyramiding, but MVP should be conservative and block same-ticker risk-increasing adds unless explicitly allowed by later policy.

> Does the daily trade limit count exits?

No. Exits, reductions, cancellations, and risk-reducing orders do not consume the new-risk trade count.

> Is this the same as FINRA pattern day trader compliance?

No. R3.6 is an internal safety limit. Broker-specific day-trade rules must be handled by future broker/account integration using broker-provided state.

> Does R3.6 place trades?

No. It only returns a structured risk decision for future broker orchestration.
