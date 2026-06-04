# PRD: R3.7 Liquid Names, Market Hours, Spread, and Reward/Risk

## Ownership

Owner: Ours

Source note: Requirement from GPT risk review: trade only liquid names, during acceptable market hours, with acceptable bid/ask spread, and reward/risk of at least 1:2.

## Objective

Add a deterministic execution-quality gate to `prescient.risk` that answers:

```text
Is this proposed trade executable under minimum liquidity, market-hours, spread, and reward/risk rules?
```

This is a pure-code safety gate. Claude, sub-agents, strategy conviction, broker adapters, and user-facing thesis text cannot override it.

## Background

Earlier R3 milestones established pure-code risk ownership, max loss, position sizing, and daily halt controls. R3.7 adds execution-quality controls before any future broker adapter can receive an order.

The MVP account size is roughly `$2,000` to `$5,000`, so bad fills matter. Wide spreads, stale quotes, illiquid options, trading outside regular hours, and weak reward/risk can overwhelm the expected edge even when a thesis is directionally correct.

## Exchange-Hours Sources

The MVP does not fetch exchange calendars directly. Market-hours truth must be supplied as a structured `MarketSessionSnapshot`.

Official references for the assumptions are:

- [NYSE hours and calendars](https://www.nyse.com/trade/hours-calendars)
- [Nasdaq market activity](https://www.nasdaq.com/market-activity)
- [Cboe U.S. options hours](https://www.cboe.com/about/hours/us-options/)

## MVP Defaults

The default MVP policy is conservative:

```text
min_reward_to_risk_ratio = 2.0
min_avg_daily_volume = 1_000_000
max_stock_bid_ask_spread_pct = 0.50
max_option_bid_ask_spread_pct = 15.0
min_option_open_interest = 100
max_quote_age_seconds = 15
min_minutes_before_close_for_new_risk = 5
allow_risk_reducing_actions = true
```

## Functional Requirements

### R3.7.1 Pure-Code Ownership

The execution-quality gate must live under `prescient.risk`.

It must not:

- Call Claude.
- Import `prescient.analyst`.
- Import broker adapters.
- Fetch live market data.
- Place orders.
- Read environment variables.
- Read the system clock.
- Sleep, poll, or run continuously.

### R3.7.2 Structured Inputs

The check must accept structured inputs equivalent to:

- Proposed action.
- Market session snapshot.
- Quote/liquidity snapshot.
- Reward/risk proposal.
- Execution-quality settings.

The market session snapshot must be supplied by a future scheduler, event, data, or broker layer. R3.7 does not compute time zones or exchange calendars.

### R3.7.3 Market-Hours Rule

Risk-increasing actions must be blocked unless the supplied session is explicitly regular open and the symbol is not halted.

Unknown or missing session data must fail closed as not evaluable.

New risk must also be blocked when the session is too close to market close based on the configured minute threshold.

### R3.7.4 Liquidity and Spread Rule

Risk-increasing stock trades require:

- Fresh quote.
- Valid positive bid and ask.
- Average daily volume greater than or equal to `min_avg_daily_volume`.
- Bid/ask spread less than or equal to `max_stock_bid_ask_spread_pct`.

Risk-increasing option trades additionally require:

- Option open interest greater than or equal to `min_option_open_interest`.
- Bid/ask spread less than or equal to `max_option_bid_ask_spread_pct`.

Spread percentage is:

```text
(ask - bid) / midpoint * 100
```

### R3.7.5 Reward/Risk Rule

Risk-increasing trades require reward/risk greater than or equal to `min_reward_to_risk_ratio`.

The ratio may be computed from:

- Explicit `expected_reward / maximum_loss`, or
- `entry_price`, `stop_price`, and `target_price` for bullish long proposals.

Missing or non-computable reward/risk must fail closed as not evaluable.

### R3.7.6 Risk-Reducing Actions

Risk-reducing actions may pass this gate without new-risk checks when `allow_risk_reducing_actions = true`.

This does not guarantee broker acceptance. It only means R3.7 should not block defensive exits, reductions, cancellations, or risk-reducing orders.

### R3.7.7 Output Contract

The execution-quality decision must be structured, deterministic, and journal-safe.

It must include:

- Status.
- Target and expression when supplied.
- Proposed action.
- Market date and session status when supplied.
- Spread percentage when computable.
- Reward/risk ratio when computable.
- Rejection reasons.
- Warnings.
- Allowed and blocked action lists.
- `broker_execution_allowed_for_new_risk`.

The output must not include credentials, account identifiers, raw prompts, broker order objects, or raw provider payloads.

## Non-Goals

- No broker integration.
- No order placement.
- No live market-data adapter.
- No exchange-calendar engine.
- No system-time reads.
- No Claude or analyst integration.
- No runtime orchestration changes.

