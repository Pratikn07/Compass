# PRD: R3.2 Max 3 Percent Per Trade

## Ownership

Owner: Ours

Review flag: The 3% cap is intentionally high for a small account and must be reviewed before any live-trading workflow. GPT suggested a lower 0.25% to 1% risk range.

## Objective

Define a hard per-trade maximum loss cap for `prescient`.

The system must reject any proposed trade whose maximum defined loss exceeds the configured per-trade cap.

For MVP, the absolute ceiling is:

```text
max_trade_loss_pct = 3.0% of account equity
```

This is a maximum loss cap, not a maximum position size or notional allocation.

## Background

`prescient` now has deterministic signal generation, optional Claude analysis, sub-agent review, runtime orchestration, and preprocessed indicator context. It can identify candidate setups, but it still needs a hard risk gate before any future order can exist.

The attached review makes five product decisions that R3.2 should preserve:

- Risk belongs in deterministic code, not Claude.
- 3% means maximum loss if stopped out, not capital allocated.
- Small accounts make this constraint binding.
- Existing target filters already cover some tradability concerns, so R3 should add account/order-level risk.
- The first R3 milestone should focus on deterministic risk and sizing with mocked account state before broker integration.

R3.2 is the per-trade cap requirement inside that broader risk phase.

## Definitions

### Account Equity

The account value used to calculate the cap.

For MVP tests, this is a structured input value, not live broker state.

Future broker integration must define whether account equity means net liquidation value, cash, settled cash, margin equity, or another broker-provided field.

### Maximum Trade Loss

The worst allowed loss for the proposed trade under the provided exit model.

Examples:

- Long stock with stop: `(entry_price - stop_price) * shares`
- Long call option with no usable stop: `option_premium * 100 * contracts`
- Long call option with valid stop: `(entry_option_price - stop_option_price) * 100 * contracts`

The risk gate must use conservative loss math when stop data is missing or unreliable.

### Per-Trade Risk Cap

The maximum loss allowed for one trade.

Formula:

```text
max_allowed_loss = account_equity * max_trade_loss_pct
```

With a 3% cap:

- `$2,000` account -> `$60` maximum loss.
- `$5,000` account -> `$150` maximum loss.

### Smallest Valid Trade

The minimum executable unit for an expression.

Examples:

- Stock: `1` share.
- Listed option: `1` contract.

If the smallest valid trade cannot fit inside the cap, the system must reject the trade.

## Requirement

The risk layer must enforce a hard maximum defined loss per trade.

Claude, sub-agents, analyst conviction, signal strength, or user-facing thesis quality cannot override the cap.

No future broker adapter may submit an order unless the deterministic risk result is approved.

## User Value

This gives the user:

- A hard final "may this trade exist?" control.
- Protection against oversized trades in a `$2,000` to `$5,000` account.
- A deterministic rejection when options contracts are too large for the account.
- Clear auditability for why a trade was sized, reduced, or rejected.
- Separation between analyst judgment and account risk.

## Functional Requirements

### R3.2.1 Pure Code Enforcement

The cap must be enforced by deterministic code in a future `prescient.risk` package.

The risk package must not:

- Call Claude.
- Import `prescient.analyst`.
- Depend on analyst conviction score.
- Accept risk override fields from Claude.
- Place broker orders directly.

### R3.2.2 Configured Cap With Absolute Ceiling

The system must support a configured `max_trade_loss_pct`.

Rules:

- Default MVP cap: `0.03`.
- Absolute ceiling: `0.03`.
- Any value above `0.03` must be rejected by configuration validation.
- The value `0.03` must produce a `review_required` flag because it is aggressive for small accounts.
- Lower caps such as `0.0025`, `0.005`, and `0.01` must be supported for review.

### R3.2.3 Maximum Loss, Not Position Notional

The cap applies to defined maximum loss, not gross position value.

The system must not approve a trade simply because the premium, debit, or notional is less than 3% unless that amount also represents maximum defined loss.

When maximum loss cannot be computed, the system must reject or mark the trade as not risk-reviewable.

### R3.2.4 Options Contract Handling

For long option trades:

- If no valid stop model exists, maximum loss must default to full premium paid.
- If a valid stop model exists, maximum loss may be calculated from entry premium to stop premium.
- Contract multiplier defaults to `100` unless supplied by structured contract metadata.
- Quantity must be an integer number of contracts.
- If `1` contract exceeds the max allowed loss, reject.

The system must not size fractional listed option contracts.

### R3.2.5 Stock Handling

For stock trades:

- Quantity must be whole shares unless a future broker adapter explicitly supports fractional shares and risk policy allows them.
- A valid stop price is required to calculate max loss.
- If no stop exists, the trade is not risk-reviewable in R3.2 and must be rejected.
- Quantity must be rounded down so projected loss does not exceed the cap.

### R3.2.6 Output Contract

The risk decision must be structured and auditable.

It should include:

- `status`: `approved`, `rejected`, or `review_required`
- `account_equity`
- `max_trade_loss_pct`
- `max_allowed_loss`
- `proposed_expression`
- `entry_price`
- `stop_price`
- `unit_max_loss`
- `approved_quantity`
- `projected_max_loss`
- `rejection_reasons`
- `warnings`
- `review_flags`

R3.2 does not require the exact implementation names, but the implementation must expose equivalent data.

### R3.2.7 Rejection Reasons

The system must provide deterministic rejection reasons.

Required reasons:

- `account_equity_missing`
- `account_equity_too_small`
- `max_trade_loss_exceeded`
- `smallest_trade_exceeds_cap`
- `stop_price_missing`
- `entry_price_missing`
- `invalid_contract_multiplier`
- `invalid_quantity`
- `risk_cap_above_allowed_ceiling`
- `max_loss_not_computable`

### R3.2.8 Review Flags

The system must flag review cases without letting them bypass the cap.

Required review flags:

- `three_percent_cap_requires_review`
- `small_account`
- `options_contract_near_cap`
- `propose_only_recommended`

For account equity between `$2,000` and `$5,000`, `small_account` and `propose_only_recommended` should be present.

### R3.2.9 Relationship To R3.1 And R3.3

R3.2 depends on R3.1 for the pure-code risk gatekeeper boundary.

R3.2 feeds R3.3 position sizing by defining the maximum allowed loss and rejection behavior.

R3.2 does not itself implement:

- Daily loss stop.
- Max open positions.
- Correlation checks.
- No averaging down.
- Market-hours checks.
- Broker order placement.

Those belong to R3.4 through R3.7 or later broker integration PRDs.

### R3.2.10 Regulatory And Broker Context

Small-account trading must remain broker/regulatory aware.

As of the current R3 design phase, FINRA's public day-trading material describes pattern day trader requirements and states that day trading margin rules apply to securities including options. FINRA also states that new intraday margin requirements become effective June 4, 2026, with a broker transition period through October 20, 2027.

Therefore, R3.2 must not hard-code one static pattern-day-trader assumption.

Future broker integration must consume broker/account capability data such as:

- Cash account vs margin account.
- Broker day-trading restrictions.
- Intraday margin rules in effect at that broker.
- Account-level order blocks or restrictions.

Sources:

- [FINRA Day Trading](https://www.finra.org/investors/investing/investment-products/stocks/day-trading)
- [FINRA: Understanding the New Intraday Margin Requirements](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)
- [SEC Release 34-105226](https://www.sec.gov/files/rules/sro/finra/2026/34-105226.pdf)

## Non-Functional Requirements

### Determinism

The same structured account, trade, and risk settings input must produce the same serialized risk decision.

### Safety

Any uncertainty in loss calculation must reject or require review. It must not approve.

### Testability

R3.2 must be testable with mocked account equity and mocked trade proposals.

No live broker credentials are required.

### Auditability

Every risk decision must preserve:

- Inputs used.
- Cap percentage.
- Dollar cap.
- Loss math.
- Quantity decision.
- Rejection reasons.
- Review flags.

### Claude Boundary

Claude may comment on risk context after deterministic risk output exists, but Claude must not size, approve, override, or bypass the cap.

## Out Of Scope

R3.2 does not include:

- Broker API integration.
- Live account state retrieval.
- Live order placement.
- Daily loss limits.
- Max open positions.
- Concentration or correlation checks.
- Market-hours validation.
- Spread or liquidity checks already covered by target filters.
- Legal, tax, or investment advice.

## Decision Flow

```text
candidate-ready strategy decision
  -> proposed expression and entry/stop model
  -> account equity snapshot
  -> max allowed loss = equity * max_trade_loss_pct
  -> compute unit max loss
  -> if unit loss cannot be computed: reject
  -> if smallest valid unit exceeds cap: reject
  -> else size down to fit cap
  -> emit structured risk decision
```

## Acceptance Criteria

- A `$2,000` account with 3% cap allows at most `$60` defined loss.
- A `$5,000` account with 3% cap allows at most `$150` defined loss.
- The cap is based on maximum loss, not notional value.
- One option contract is rejected when its maximum loss exceeds the cap.
- A stock trade without a stop is rejected as not risk-reviewable.
- Configured caps above 3% are rejected.
- A 3% cap emits `three_percent_cap_requires_review`.
- Small accounts emit `small_account` and `propose_only_recommended`.
- Claude cannot approve or override a rejected risk decision.
- Risk output is JSON-serializable and deterministic.

## Current Implementation Notes

The current repo has no `prescient.risk` package yet.

Relevant existing boundaries:

- `prescient.signal` creates deterministic strategy decisions and candidate briefs.
- `prescient.analyst` and sub-agents are advisory and already forbid position sizing, broker action, and risk overrides.
- Target filters already handle volume, run-up, options spread/open interest, conflicting news, and invalidating events.

Known R3.2 implementation gaps:

- Add risk models for account snapshots, trade proposals, risk settings, and risk decisions.
- Add pure risk sizing/rejection functions.
- Add tests for stock and option sizing against the 3% cap.
- Add tests proving Claude output cannot override risk rejection.

## Product FAQ

> Does 3% mean 3% of account used to buy the trade?

No. It means the maximum defined loss may not exceed 3% of account equity.

> Why flag 3% for review?

Because 3% is aggressive for a small account. The system supports it as the selected cap, but it must be visible as a review-required risk setting.

> What happens if one option contract is too expensive?

Reject the trade. Do not round up, use fractional contracts, or let Claude override the cap.

> Should small accounts live auto-trade?

R3.2 does not authorize live auto-trading. For `$2,000` to `$5,000` accounts, the risk decision should flag propose-only or paper-trading review.
