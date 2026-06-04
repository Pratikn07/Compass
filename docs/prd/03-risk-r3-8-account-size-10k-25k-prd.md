# PRD: R3.8 Account Size $10k-$25k

## Summary

R3.8 defines the primary supported account tier for `prescient`: accounts with
equity from `$10,000` through `$25,000`.

This is a pure-code risk policy milestone under `prescient.risk`. It must
classify account size, set conservative tier defaults, and determine whether a
trade may be considered live-eligible after all other deterministic R3 gates
pass.

Chosen defaults:

- `$10k-$25k` is the supported account tier.
- Default per-trade risk for this tier is `1%`.
- R3.2's `3%` cap remains the absolute ceiling and requires review.
- Live trading is eligible in this tier only when all deterministic code gates
  pass.

## Requirement

The risk layer must answer:

```text
Is this account size eligible for this trading mode and risk profile?
```

Claude, analyst conviction, sub-agents, broker adapters, or strategy confidence
cannot override account-size restrictions.

## Functional Requirements

- Add an account-size policy check under `prescient.risk`.
- Accept structured account input: account equity, requested execution mode,
  optional account type, optional broker day-trade regime, and risk settings.
- Classify account equity into:
  - `below_supported_tier`: `< $10,000`
  - `supported_10k_25k`: `$10,000 <= equity <= $25,000`
  - `above_supported_tier`: `> $25,000`
- For the supported tier:
  - Default `max_trade_loss_pct = 0.01`
  - Absolute ceiling remains `0.03`
  - Any cap above `0.01` must create a review flag.
  - Any cap above `0.03` must be rejected.
- Accounts below `$10,000` must not be live-eligible in R3.8, but may still be
  paper/propose-only.
- Accounts above `$25,000` must not automatically receive higher limits; return
  a review flag until a future larger-account policy exists.
- Missing, zero, or invalid equity must fail closed for live eligibility.
- R3.8 must not bypass R3.2 per-trade risk, R3.4 daily halt, R3.5 concentration
  checks, R3.6 activity limits, or R3.7 execution-quality checks.

## Decision Output

The account-size decision must be deterministic and JSON-serializable, with
equivalent data to:

- `status`: `eligible`, `restricted`, or `review_required`
- `account_equity`
- `account_size_tier`
- `recommended_max_trade_loss_pct`
- `absolute_max_trade_loss_pct`
- `recommended_max_trade_loss_amount`
- `absolute_max_trade_loss_amount`
- `live_trading_eligible`
- `paper_trading_allowed`
- `propose_only_recommended`
- `rejection_reasons`
- `review_flags`
- `warnings`

Required reasons and flags:

- `account_equity_missing`
- `account_equity_invalid`
- `account_below_supported_tier`
- `account_above_supported_tier`
- `risk_cap_above_tier_default`
- `risk_cap_above_absolute_ceiling`
- `broker_day_trade_policy_unverified`

## Regulatory Context

R3.8 must not hard-code a static PDT rule. FINRA and Investor.gov state that new
intraday margin requirements become effective on `June 4, 2026`, with a broker
transition period through `October 20, 2027`. Broker firms may continue old
day-trading margin rules during transition or migrate sooner.

Therefore, R3.8 may surface warnings, but broker-specific day-trade enforcement
belongs to a future broker/account adapter.

Sources:

- [FINRA Day Trading](https://www.finra.org/investors/investing/investment-products/stocks/day-trading)
- [FINRA New Intraday Margin Requirements](https://syndication.finra.org/content/understanding-new-intraday-margin-requirements)
- [Investor.gov Pattern Day Trader](https://www.investor.gov/introduction-investing/investing-basics/glossary/pattern-day-trader)

## Acceptance Criteria

- `$10,000` account is classified as `supported_10k_25k`.
- `$25,000` account is classified as `supported_10k_25k`.
- `$9,999.99` account is restricted from live eligibility.
- `$25,000.01` account produces an above-tier review flag, not higher automatic
  limits.
- Supported-tier default risk is `1%`.
- A `$10,000` account has recommended max trade loss of `$100`.
- A `$25,000` account has recommended max trade loss of `$250`.
- A configured `3%` cap remains allowed only as review-required.
- A configured cap above `3%` is rejected.
- Missing/invalid equity fails closed.
- Claude-like fields cannot change the decision.
- Identical input produces identical serialized output.
- Import-boundary tests prove `prescient.risk` remains Claude-free,
  broker-free, runtime-free, network-free, scheduler-free, and deterministic.

## Out Of Scope

R3.8 does not implement:

- Broker account sync.
- PDT compliance.
- Live order placement.
- Intraday margin calculations.
- Buying-power checks.
- Cash-settlement checks.
- Tax logic.
- Deposits or withdrawals.
- Larger-account leverage policy.
