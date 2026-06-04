# R3.5 Max Open Positions + Correlation / Concentration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the R3.5 PRD as a pure-code portfolio concentration gate under `prescient.risk`.

**Architecture:** Add a small deterministic risk module that evaluates structured portfolio exposure snapshots and proposed risk snapshots. It should block new risk when open-position count, same-ticker exposure, theme/correlation grouping, or aggregate open-risk limits are exceeded, while still allowing risk-reducing actions. The API must remain Claude-free, broker-free, network-free, and independently testable.

**Tech Stack:** Python, Pydantic v2, pytest, uv, ruff.

---

## PRD Check

Use this PRD as source of truth:

`/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/03-risk-r3-5-max-open-positions-correlation-concentration-prd.md`

Current repo state:

- `prescient.risk` already exposes R3.1 `evaluate_risk_gate`.
- R3.2 `evaluate_trade_risk` exists.
- R3.3 `size_position` exists.
- R3.4 `evaluate_daily_halt` exists.
- `DailyRiskAction` already models new-risk and risk-reducing actions; reuse it.
- `contains_unsafe_claude_key(...)` exists in `prescient.risk.safety`, but R3.5 should not accept Claude input at all.

## File Structure

Modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/models.py`
  - Add R3.5 enums and Pydantic models.

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/__init__.py`
  - Export R3.5 models and `evaluate_portfolio_concentration`.

- `/Users/pratik.nandoskar/Documents/working/prescient/README.md`
  - Add a short R3.5 note under Risk gate.

Create:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/portfolio_concentration.py`
  - Implement the pure concentration check.

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r3_5_portfolio_concentration.py`
  - Cover PRD acceptance criteria and output contract.

Do not modify:

- `prescient.signal`
- `prescient.analyst`
- `prescient.runtime`
- `prescient.scheduler`
- `prescient.events`
- Broker placeholders or live data adapters

## Public API And Models

Add these model names in `prescient.risk.models`.

```python
class ConcentrationStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    NOT_EVALUABLE = "not_evaluable"


class ConcentrationRejectionReason(StrEnum):
    MAX_OPEN_POSITIONS_REACHED = "max_open_positions_reached"
    ABSOLUTE_MAX_OPEN_POSITIONS_EXCEEDED = "absolute_max_open_positions_exceeded"
    SAME_TICKER_ALREADY_OPEN = "same_ticker_already_open"
    THEME_CONCENTRATION_LIMIT_EXCEEDED = "theme_concentration_limit_exceeded"
    CORRELATION_GROUP_LIMIT_EXCEEDED = "correlation_group_limit_exceeded"
    CORRELATION_GROUP_RISK_LIMIT_EXCEEDED = "correlation_group_risk_limit_exceeded"
    AGGREGATE_OPEN_RISK_LIMIT_EXCEEDED = "aggregate_open_risk_limit_exceeded"
    ACCOUNT_EQUITY_MISSING = "account_equity_missing"
    PROPOSED_MAX_LOSS_MISSING = "proposed_max_loss_missing"
    OPEN_POSITIONS_MISSING = "open_positions_missing"
    CORRELATION_GROUP_MISSING = "correlation_group_missing"
    TARGET_MISSING = "target_missing"
    INVALID_POSITION_COUNT_SETTING = "invalid_position_count_setting"
    INVALID_CONCENTRATION_SETTING = "invalid_concentration_setting"


class ConcentrationWarning(StrEnum):
    THEME_USED_AS_CORRELATION_GROUP_FALLBACK = (
        "theme_used_as_correlation_group_fallback"
    )
    SECTOR_MISSING = "sector_missing"
    POSITION_UNREALIZED_PNL_MISSING = "position_unrealized_pnl_missing"
    OPEN_ORDERS_NOT_INCLUDED = "open_orders_not_included"
```

Add settings:

```python
class PortfolioConcentrationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_open_positions: int = 3
    absolute_max_open_positions: int = 5
    max_positions_per_correlation_group: int = 1
    max_positions_per_theme: int = 1
    max_positions_per_direction: int = 3
    max_aggregate_open_risk_pct: float = 0.06
    max_correlation_group_open_risk_pct: float = 0.03
    allow_risk_reducing_actions: bool = True
```

Add snapshots:

```python
class OpenPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    theme: str | None
    sector: str | None = None
    direction: str
    correlation_groups: list[str] = Field(default_factory=list)
    quantity: int
    expression: TradeExpression
    opened_at: date | None = None
    projected_max_loss: float
    current_unrealized_pnl: float | None = None


class ProposedPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str | None
    theme: str | None
    sector: str | None = None
    direction: str
    correlation_groups: list[str] = Field(default_factory=list)
    proposed_max_loss: float | None
    action: DailyRiskAction = DailyRiskAction.NEW_ENTRY


class PortfolioExposureState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_equity: float | None
    open_positions: list[OpenPositionSnapshot] | None
    open_orders_included: bool = False
```

Add decision:

```python
class PortfolioConcentrationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ConcentrationStatus
    target: str | None
    theme: str | None
    correlation_groups: list[str] = Field(default_factory=list)
    open_position_count: int | None
    max_open_positions: int
    projected_open_position_count: int | None
    account_equity: float | None
    existing_open_risk: float | None
    proposed_max_loss: float | None
    projected_aggregate_open_risk: float | None
    max_aggregate_open_risk: float | None
    correlation_group_exposures: dict[str, float] = Field(default_factory=dict)
    rejection_reasons: list[ConcentrationRejectionReason] = Field(default_factory=list)
    warnings: list[ConcentrationWarning] = Field(default_factory=list)
    allowed_actions: list[DailyRiskAction] = Field(default_factory=list)
    blocked_actions: list[DailyRiskAction] = Field(default_factory=list)
    broker_execution_allowed_for_new_risk: bool
```

Public function:

```python
def evaluate_portfolio_concentration(
    state: PortfolioExposureState,
    proposed: ProposedPositionSnapshot,
    settings: PortfolioConcentrationSettings | None = None,
) -> PortfolioConcentrationDecision:
    ...
```

No Claude, analyst, broker, runtime, scheduler, event, or network parameter is allowed.

## Task 1: Add Failing R3.5 Tests

**Files:**

- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r3_5_portfolio_concentration.py`

- [ ] **Step 1: Create test helpers**

Use this helper shape:

```python
from __future__ import annotations

from datetime import date
from inspect import signature
from pathlib import Path

from prescient.risk import (
    ConcentrationRejectionReason,
    ConcentrationStatus,
    ConcentrationWarning,
    DailyRiskAction,
    OpenPositionSnapshot,
    PortfolioConcentrationSettings,
    PortfolioExposureState,
    ProposedPositionSnapshot,
    TradeExpression,
    evaluate_portfolio_concentration,
)


R3_5_PRD_PATH = Path(
    "docs/prd/03-risk-r3-5-max-open-positions-correlation-concentration-prd.md"
)


def _position(
    ticker: str,
    *,
    theme: str = "AI_STORAGE",
    sector: str | None = "Technology",
    direction: str = "bullish",
    correlation_groups: list[str] | None = None,
    projected_max_loss: float = 100.0,
) -> OpenPositionSnapshot:
    return OpenPositionSnapshot(
        ticker=ticker,
        theme=theme,
        sector=sector,
        direction=direction,
        correlation_groups=correlation_groups or [theme],
        quantity=1,
        expression=TradeExpression.CALL_OPTION,
        opened_at=date(2026, 6, 3),
        projected_max_loss=projected_max_loss,
        current_unrealized_pnl=0.0,
    )


def _state(
    *,
    account_equity: float | None = 5_000.0,
    open_positions: list[OpenPositionSnapshot] | None = None,
    open_orders_included: bool = True,
) -> PortfolioExposureState:
    return PortfolioExposureState(
        account_equity=account_equity,
        open_positions=open_positions if open_positions is not None else [],
        open_orders_included=open_orders_included,
    )


def _proposed(
    *,
    target: str | None = "NTNX",
    theme: str | None = "AI_STORAGE",
    sector: str | None = "Technology",
    direction: str = "bullish",
    correlation_groups: list[str] | None = None,
    proposed_max_loss: float | None = 100.0,
    action: DailyRiskAction = DailyRiskAction.NEW_ENTRY,
) -> ProposedPositionSnapshot:
    groups = correlation_groups if correlation_groups is not None else ([theme] if theme else [])
    return ProposedPositionSnapshot(
        target=target,
        theme=theme,
        sector=sector,
        direction=direction,
        correlation_groups=groups,
        proposed_max_loss=proposed_max_loss,
        action=action,
    )
```

- [ ] **Step 2: Add acceptance tests**

Cover these exact scenarios:

```python
def test_r3_5_prd_exists_and_names_concentration_defaults() -> None:
    prd = R3_5_PRD_PATH.read_text(encoding="utf-8")
    assert "# PRD: R3.5 Max Open Positions" in prd
    assert "`max_open_positions = 3`" in prd
    assert "`absolute_max_open_positions = 5`" in prd
    assert "`max_aggregate_open_risk_pct = 0.06`" in prd


def test_blocks_when_default_max_open_positions_reached() -> None:
    decision = evaluate_portfolio_concentration(
        state=_state(open_positions=[
            _position("A"),
            _position("B", theme="SEMIS_AI", correlation_groups=["SEMIS_AI"]),
            _position("C", theme="FINTECH", correlation_groups=["FINTECH"]),
        ]),
        proposed=_proposed(target="D", theme="HEALTHCARE", correlation_groups=["HEALTHCARE"]),
    )
    assert decision.status == ConcentrationStatus.BLOCKED
    assert decision.rejection_reasons == [
        ConcentrationRejectionReason.MAX_OPEN_POSITIONS_REACHED
    ]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_invalid_max_open_positions_above_absolute_ceiling_blocks() -> None:
    decision = evaluate_portfolio_concentration(
        state=_state(),
        proposed=_proposed(),
        settings=PortfolioConcentrationSettings(max_open_positions=6),
    )
    assert decision.status == ConcentrationStatus.BLOCKED
    assert decision.rejection_reasons == [
        ConcentrationRejectionReason.ABSOLUTE_MAX_OPEN_POSITIONS_EXCEEDED
    ]
```

Also include tests for:

- same ticker already open
- explicit correlation group duplicate
- theme fallback duplicate with `THEME_USED_AS_CORRELATION_GROUP_FALLBACK`
- aggregate open risk over 6%
- correlation group risk over 3%
- risk-reducing action allowed despite max open positions
- missing account equity, proposed max loss, open positions, target, and grouping fail closed
- warnings for missing sector, missing unrealized PnL, and open orders not included
- identical input serializes deterministically
- `evaluate_portfolio_concentration` signature has no `claude`, `analyst`, or `broker` parameter

- [ ] **Step 3: Run the focused test and verify it fails red**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_r3_5_portfolio_concentration.py -q
```

Expected: import error for missing R3.5 models or `evaluate_portfolio_concentration`.

## Task 2: Add R3.5 Models And Exports

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/models.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/__init__.py`

- [ ] **Step 1: Add R3.5 enums and models**

Add the models from the **Public API And Models** section.

Validation rules:

- Normalize tickers, themes, sectors, directions, and correlation groups to uppercase.
- Remove blank duplicate correlation groups while preserving first-seen order.
- `OpenPositionSnapshot.projected_max_loss` must be positive.
- `OpenPositionSnapshot.quantity` must be positive.
- `PortfolioConcentrationDecision` with `BLOCKED` or `NOT_EVALUABLE` must include rejection reasons.
- `broker_execution_allowed_for_new_risk` may be true only for `ALLOWED`.

- [ ] **Step 2: Export names from `prescient.risk`**

Export:

```python
"ConcentrationRejectionReason",
"ConcentrationStatus",
"ConcentrationWarning",
"OpenPositionSnapshot",
"PortfolioConcentrationDecision",
"PortfolioConcentrationSettings",
"PortfolioExposureState",
"ProposedPositionSnapshot",
"evaluate_portfolio_concentration",
```

- [ ] **Step 3: Run focused test and verify it still fails on missing function/module**

```bash
uv run pytest tests/test_r3_5_portfolio_concentration.py -q
```

Expected: import succeeds for models, then fails for missing `evaluate_portfolio_concentration` or missing implementation behavior.

## Task 3: Implement Portfolio Concentration Evaluation

**Files:**

- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/portfolio_concentration.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/__init__.py`

- [ ] **Step 1: Add action policy constants**

Use the same policy as R3.4:

```python
_RISK_INCREASING_ACTIONS = [
    DailyRiskAction.NEW_ENTRY,
    DailyRiskAction.ADD_TO_POSITION,
    DailyRiskAction.OPEN_OPTION_CONTRACT,
    DailyRiskAction.RISK_INCREASING_REPLACEMENT_ORDER,
]

_RISK_REDUCING_ACTIONS = [
    DailyRiskAction.EXIT_POSITION,
    DailyRiskAction.REDUCE_POSITION,
    DailyRiskAction.CANCEL_ORDER,
    DailyRiskAction.RISK_REDUCING_ORDER,
]
```

- [ ] **Step 2: Implement `evaluate_portfolio_concentration`**

Decision order for risk-increasing actions:

1. Validate settings.
2. Validate required state/proposed fields.
3. Resolve proposed correlation groups:
   - explicit groups win
   - fallback to theme when groups are empty
   - if both missing, `NOT_EVALUABLE` with `CORRELATION_GROUP_MISSING`
4. Compute warnings.
5. Count open positions.
6. Check max open positions.
7. Check same ticker.
8. Check theme count.
9. Check correlation group count.
10. Check correlation group risk.
11. Check aggregate open risk.
12. Return `ALLOWED` only if no rejection reasons.

Risk-reducing actions:

- Return `ALLOWED`.
- Keep `broker_execution_allowed_for_new_risk=False`.
- Allow only reducing actions.
- Do not require account equity, proposed max loss, or open position data.

- [ ] **Step 3: Implement exposure helpers**

Required helper behavior:

- Existing open risk is the sum of all `position.projected_max_loss`.
- Projected aggregate risk is existing open risk plus proposed max loss.
- Max aggregate open risk is `account_equity * max_aggregate_open_risk_pct`.
- Correlation group exposure includes existing group risk plus proposed risk for each proposed group.
- A position with no explicit groups uses its theme as fallback and emits fallback warning.

- [ ] **Step 4: Run focused tests**

```bash
uv run pytest tests/test_r3_5_portfolio_concentration.py -q
```

Expected: all R3.5 tests pass.

## Task 4: Documentation And Boundary Regression

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/README.md`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_risk_boundaries.py`

- [ ] **Step 1: Add README note**

Under `## Risk gate`, add:

```markdown
R3.5 exposes `evaluate_portfolio_concentration`, a deterministic open-position
and concentration gate. It limits max open positions, same-ticker exposure,
theme/correlation-group stacking, and aggregate defined open risk without
calculating live statistical correlation or allowing Claude overrides.
```

- [ ] **Step 2: Extend risk boundary tests**

Add a signature assertion:

```python
def test_evaluate_portfolio_concentration_accepts_no_claude_analyst_or_broker_parameter() -> None:
    signature = inspect.signature(evaluate_portfolio_concentration)

    assert list(signature.parameters) == ["state", "proposed", "settings"]
    assert not any(
        unsafe_name in parameter_name
        for parameter_name in signature.parameters
        for unsafe_name in ["claude", "analyst", "broker"]
    )
```

Ensure `test_risk_package_has_no_cold_path_broker_network_or_polling_imports` still scans `src/prescient/risk/*.py` and catches the new file.

- [ ] **Step 3: Run boundary tests**

```bash
uv run pytest tests/test_risk_boundaries.py tests/test_r3_5_portfolio_concentration.py -q
```

Expected: all pass.

## Task 5: Full Verification

**Files:**

- No additional edits unless verification fails.

- [ ] **Step 1: Run focused risk suite**

```bash
uv run pytest \
  tests/test_r3_5_portfolio_concentration.py \
  tests/test_risk_boundaries.py \
  tests/test_risk_gatekeeper.py \
  tests/test_position_sizing.py \
  tests/test_r3_4_daily_halt.py \
  tests/test_r3_2_trade_risk.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run full tests**

```bash
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 3: Run Ruff**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

## Assumptions

- R3.5 does not calculate live statistical correlation; explicit correlation groups and theme fallback are the MVP.
- `max_open_positions=3` is the default; `5` is only the absolute configuration ceiling.
- Risk-reducing actions are allowed even when concentration checks would block new risk.
- `open_orders_included=False` produces a warning, not a rejection.
- Existing open positions must carry positive `projected_max_loss`; this keeps aggregate-risk math deterministic.
- R3.5 remains independent from final orchestration across R3.2/R3.3/R3.4; final risk composition is a later milestone.
