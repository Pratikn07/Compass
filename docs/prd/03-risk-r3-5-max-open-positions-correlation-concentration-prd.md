# PRD: R3.5 Max Open Positions + Correlation / Concentration Check

## Ownership

Owner: Ours

Source note: Requirement from GPT/Gem/Ours risk phase: do not allow multiple open trades that effectively move together.

## Objective

Add a deterministic account exposure gate to `prescient.risk` that limits how many positions can be open and blocks new risk when the proposed trade would create excessive correlated or concentrated exposure.

R3.5 answers:

```text
Can this account add another open position without becoming over-concentrated?
```

The system must prevent the failure mode where the app holds several names that appear diversified but are exposed to the same driver, theme, sector, or earnings read-through.

## Background

R3.1 established the pure-code risk gatekeeper boundary.
R3.2 added a per-trade maximum defined-loss cap.
R3.3 added code-owned position sizing.
R3.4 added a daily realized-loss halt.

R3.5 adds portfolio-shape constraints before any future broker adapter can add new risk.

The current strategy universe is theme-based, and many candidate trades can come from related peers. That makes the correlation problem practical even before live statistical correlation is implemented: five storage/AI infrastructure names can move together even if they are separate tickers.

## Requirement

The risk layer must reject a proposed new position when:

- The account is already at the configured maximum number of open positions.
- The proposed target belongs to a correlation/theme group that is already full.
- The proposed trade would exceed configured concentration limits by theme, sector, direction, or risk budget.
- Required structured exposure data is missing or not evaluable.

Claude, sub-agents, analyst conviction, strategy score, or broker adapters cannot override these checks.

## Definitions

### Open Position

An open position is any currently held risk exposure in the account.

For MVP, the input is a structured snapshot. It may include stock shares, option contracts, or future strategy expressions, but R3.5 only needs the normalized exposure fields needed for portfolio checks.

### Correlation Group

A correlation group is a deterministic label for positions expected to move together.

Examples:

- `AI_STORAGE`
- `SEMIS_AI`
- `MEGA_CAP_TECH`
- `FINTECH_RATE_SENSITIVE`

For MVP, correlation groups are configured or supplied as structured metadata. R3.5 does not calculate rolling statistical correlations from price history.

### Concentration

Concentration is excessive exposure to one ticker, theme, correlation group, sector, strategy direction, or driver.

For MVP, concentration is measured using structured position count and projected maximum loss, not live beta or portfolio VaR.

### New Risk

New risk includes:

- Opening a new position.
- Adding to an existing position.
- Opening option contracts.
- Replacing an order in a way that increases maximum loss.

Risk-reducing actions such as exits, reductions, and cancellations are not blocked by R3.5.

## MVP Defaults

The default MVP policy should be conservative for a small account:

- `max_open_positions = 3`
- `absolute_max_open_positions = 5`
- `max_positions_per_correlation_group = 1`
- `max_positions_per_theme = 1`
- `max_positions_per_direction = 3`
- `max_aggregate_open_risk_pct = 0.06`
- `max_correlation_group_open_risk_pct = 0.03`
- `allow_risk_reducing_actions = true`

Rationale:

- With a 3% per-trade cap from R3.2, three fully sized positions can represent up to 9% defined open risk. The MVP aggregate cap of 6% prevents stacking three max-risk positions.
- A small account should not hold several highly related names at once.
- The absolute ceiling of 5 exists for future review but must not be the default.

## Functional Requirements

### R3.5.1 Pure-Code Ownership

The concentration gate must live under `prescient.risk`.

It must not:

- Call Claude.
- Import `prescient.analyst`.
- Import broker adapters.
- Fetch live data.
- Calculate live price correlations.
- Place orders.
- Accept risk override fields from Claude.

### R3.5.2 Structured Inputs

The check must accept structured inputs equivalent to:

- Account equity.
- Proposed target ticker.
- Proposed theme.
- Proposed sector, if available.
- Proposed direction.
- Proposed correlation groups.
- Proposed maximum loss or projected maximum loss.
- Existing open positions snapshot.
- Existing open orders that would become positions if filled, when available.
- Risk settings.

Open position records should include equivalent fields to:

- `ticker`
- `theme`
- `sector`
- `direction`
- `correlation_groups`
- `quantity`
- `expression`
- `opened_at`
- `projected_max_loss`
- `current_unrealized_pnl`, optional

Missing optional fields may produce warnings. Missing required fields must fail closed.

### R3.5.3 Max Open Positions

The system must block new risk when the number of open positions is greater than or equal to `max_open_positions`.

Risk-reducing actions must remain allowed.

The default `max_open_positions` is `3`.

Any configured value above `absolute_max_open_positions = 5` must be rejected or marked invalid by settings validation.

### R3.5.4 Theme And Correlation Group Limits

The system must block a proposed trade if it would exceed:

- `max_positions_per_theme`
- `max_positions_per_correlation_group`
- `max_correlation_group_open_risk_pct`

MVP grouping rules:

- If explicit correlation groups are supplied, use them.
- If no explicit correlation group is supplied but theme is present, use theme as the fallback group.
- If neither correlation group nor theme is present, reject or mark not evaluable.

This prevents holding several names from the same read-through theme, even when tickers differ.

### R3.5.5 Aggregate Open Risk Limit

The system must calculate projected aggregate open risk:

```text
aggregate_open_risk = existing_projected_max_loss + proposed_projected_max_loss
max_aggregate_open_risk = account_equity * max_aggregate_open_risk_pct
```

If projected aggregate open risk exceeds the cap, the proposed new risk must be blocked.

MVP default:

```text
max_aggregate_open_risk_pct = 0.06
```

### R3.5.6 Same Ticker Handling

The system must reject a new entry for a ticker that is already open unless the action is explicitly risk-reducing.

Adding to an existing position is considered risk-increasing and must pass all concentration checks.

R3.6 later adds explicit no-averaging-down and daily trade-count rules.

### R3.5.7 Output Contract

The concentration decision must be structured, deterministic, and journal-safe.

It should include equivalent fields to:

- `status`: `allowed`, `blocked`, or `not_evaluable`
- `target`
- `theme`
- `correlation_groups`
- `open_position_count`
- `max_open_positions`
- `projected_open_position_count`
- `account_equity`
- `existing_open_risk`
- `proposed_max_loss`
- `projected_aggregate_open_risk`
- `max_aggregate_open_risk`
- `correlation_group_exposures`
- `rejection_reasons`
- `warnings`
- `allowed_actions`
- `blocked_actions`
- `broker_execution_allowed_for_new_risk`

### R3.5.8 Rejection Reasons

Required rejection reasons:

- `max_open_positions_reached`
- `absolute_max_open_positions_exceeded`
- `same_ticker_already_open`
- `theme_concentration_limit_exceeded`
- `correlation_group_limit_exceeded`
- `correlation_group_risk_limit_exceeded`
- `aggregate_open_risk_limit_exceeded`
- `account_equity_missing`
- `proposed_max_loss_missing`
- `open_positions_missing`
- `correlation_group_missing`
- `target_missing`
- `invalid_position_count_setting`
- `invalid_concentration_setting`

### R3.5.9 Warnings

Required warnings:

- `theme_used_as_correlation_group_fallback`
- `sector_missing`
- `position_unrealized_pnl_missing`
- `open_orders_not_included`

Warnings must not allow a blocked decision to become allowed.

### R3.5.10 Action Policy

When blocked, the system must block:

- New entries.
- Adds to existing positions.
- Opening option contracts.
- Risk-increasing replacement orders.

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
- R3.5 owns account-level open-position count and concentration.

R3.5 must consume or align with R3.3 projected max loss but must not redo sizing math.

R3.5 must consume R3.4 halt decisions later in final risk orchestration, but it must remain independently testable as a pure concentration check.

## Acceptance Criteria

- A new trade is blocked when there are already `3` open positions by default.
- A configured `max_open_positions` above `5` is invalid.
- A new trade is blocked when the same ticker is already open and the action is risk-increasing.
- A new trade is blocked when another open position has the same correlation group and `max_positions_per_correlation_group = 1`.
- A new trade is blocked when theme fallback creates a duplicate correlation group.
- A new trade is blocked when projected aggregate open risk exceeds `6%` of account equity.
- A new trade is blocked when one correlation group would exceed `3%` of account equity.
- Risk-reducing exits, reductions, and cancellations remain allowed.
- Missing required account equity, proposed max loss, open positions, target, or grouping data fails closed.
- Same input serializes to the same output.
- Claude cannot remove concentration rejection reasons or approve new risk.
- Tests require no live data, broker account, Claude call, or network access.
- Import-boundary tests prove `prescient.risk` does not import analyst, broker, runtime, scheduler, event, network, or live-data dependencies for concentration checks.

## Out Of Scope

R3.5 does not implement:

- Live broker account sync.
- Live order placement.
- Rolling statistical correlation from price history.
- Beta, VaR, factor models, or portfolio optimization.
- Sector classification data providers.
- Averaging-down detection. That belongs to R3.6.
- Market-hours, spread, and reward/risk checks. Those belong to R3.7.
- Legal, tax, or investment advice.

## Decision Flow

```text
proposed new risk
  -> required account/proposal/open-position data present?
      no -> not_evaluable
  -> settings valid?
      no -> blocked or not_evaluable
  -> risk-reducing action?
      yes -> allowed
  -> open position count below max?
      no -> blocked
  -> same ticker already open?
      yes -> blocked
  -> correlation group/theme exposure below limits?
      no -> blocked
  -> aggregate open risk below cap?
      no -> blocked
  -> emit allowed concentration decision
```

## Product FAQ

> Does max positions mean we can hold five related names?

No. The absolute ceiling of five is not permission to hold five names with the same driver. The correlation and theme checks must block that.

> Should R3.5 calculate real market correlation?

Not in MVP. R3.5 uses explicit correlation groups and theme fallback. Live statistical correlation can be a later data/portfolio enhancement.

> Can Claude say two names are not correlated?

No. Claude can comment after deterministic risk output exists, but it cannot override code-owned concentration groups or rejection reasons.

> Does R3.5 place trades?

No. It only returns a structured risk decision for future broker orchestration.
