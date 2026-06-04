# R5.3 Robinhood Secondary Broker Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Robinhood secondary broker adapter (`RobinhoodAdapter`) conforming to the standardized `BrokerAdapter` Protocol, allowing live stock execution while enforcing capability constraints (no paper trading, no options).

**Architecture:** Integrate the `robin_stocks.robinhood` library within `prescient.broker` as a concrete adapter class. Ensure that the core application remains fully decoupled from Robinhood SDK details.

**Tech Stack:** Python, Pydantic v2, pytest, uv, ruff, mypy.

---

## User Review Required

> [!IMPORTANT]
> **Dependency Addition:** This plan adds `robin_stocks` to the project's dependencies inside `pyproject.toml`. Please confirm if there are specific version constraints or specific forks of `robin_stocks` we should use.
>
> **MFA Authentication:** This adapter requires `ROBINHOOD_TOTP` using an authenticator app's secret key for headless execution. If the user's Robinhood account only supports SMS-based verification or has MFA disabled, authentication will fail.

---

## Open Questions

> [!NOTE]
> There are no outstanding open questions blocking the initiation of this plan.

---

## Proposed Changes

### Dependencies and Initialization

#### [MODIFY] [pyproject.toml](file:///Users/pratik.nandoskar/Documents/working/prescient/pyproject.toml)
- Add `robin-stocks>=3.3` to the dependencies section.

#### [MODIFY] [__init__.py](file:///Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/__init__.py)
- Import `prescient.broker.robinhood` at the bottom of the file to trigger auto-registration in the broker registry.

---

### Broker Implementation

#### [NEW] [robinhood.py](file:///Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/robinhood.py)
- Create `RobinhoodAdapter` conforming to `BrokerAdapter` Protocol.
- Encapsulate login via `robin_stocks.robinhood.login()`.
- Validate that `ExecutionMode.PAPER` is rejected with `ConfigurationError`.
- Implement `get_capabilities()` to return `supports_options=False` and `supports_paper_trading=False`.
- Implement `place_order` to submit a limit buy/sell order via `robin_stocks`, rejecting `CALL_OPTION` or `PUT_OPTION` with `UnsupportedCapabilityError`.
- Implement `get_positions` to query holdings and filter out non-stock positions (crypto, options).
- Implement `get_orders` and `cancel_order` wrapping the Robinhood API endpoints.
- Map Robinhood/HTTP/requests exceptions to the unified `BrokerError` hierarchy.

---

### Tests

#### [NEW] [test_robinhood_adapter.py](file:///Users/pratik.nandoskar/Documents/working/prescient/tests/test_robinhood_adapter.py)
- Test cases for checking paper mode raising `ConfigurationError`.
- Test cases for credential missing/authentication error mapping.
- Test cases for options trading raising `UnsupportedCapabilityError`.
- Test cases for positions filtering (proving crypto/options are filtered out).
- Test cases for ordering mechanics with mocked Robinhood API endpoints.
- Test cases for checking standardized exceptions (Rate limits, Execution errors, Connection errors).

---

## Task 1: Add Dependencies and Registries

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/pyproject.toml`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/__init__.py`

- [ ] **Step 1: Add `robin-stocks` dependency**
  Edit `pyproject.toml` to add `"robin-stocks>=3.3.0"` to the dependencies array.
  Run `uv sync` to install the dependency.

- [ ] **Step 2: Add Robinhood import to package init**
  Append `import prescient.broker.robinhood` at the end of `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/__init__.py` to register the adapter on package load.

---

## Task 2: Create Failing Tests (TDD)

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_robinhood_adapter.py`

- [ ] **Step 1: Write test layout and mock decorators**
  Set up mocks for `robin_stocks.robinhood` calls (`login`, `build_holdings`, `build_user_profile`, etc.).

- [ ] **Step 2: Add tests for initialization and capabilities checks**
  - Verify constructing with `ExecutionMode.PAPER` raises `ConfigurationError`.
  - Verify credentials validation (raises `BrokerAuthenticationError` on missing environment variables).
  - Verify `get_capabilities()` returns the expected settings (`supports_options=False`, `supports_paper_trading=False`, `broker_name="robinhood"`).

- [ ] **Step 3: Add tests for position filtering**
  - Mock Robinhood holdings returns containing equity (`AAPL`), crypto (`DOGE`), and options (`AAPL260619C00150000`).
  - Assert `get_positions` returns exactly one position for `AAPL` and zero for others.

- [ ] **Step 4: Add tests for order execution and constraints**
  - Verify placing an option order raises `UnsupportedCapabilityError`.
  - Verify placing a valid stock order invokes `robin_stocks` order placements correctly.

- [ ] **Step 5: Add tests for error mapping**
  - Assert that mock API exceptions map cleanly to `BrokerConnectionError`, `BrokerAuthenticationError`, etc.

- [ ] **Step 6: Run tests to confirm failures**
  Run:
  ```bash
  uv run pytest tests/test_robinhood_adapter.py -v
  ```
  *(Expected: Fails due to missing `prescient.broker.robinhood` module or class)*

---

## Task 3: Implement RobinhoodAdapter Class

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/robinhood.py`

- [ ] **Step 1: Set up imports, class definition, and auto-registration**
  - Import `robin_stocks.robinhood as r` and `requests`.
  - Define `RobinhoodAdapter` conforming to the `BrokerAdapter` interface protocol.
  - Call `register_broker("robinhood", RobinhoodAdapter)` at the bottom of the file.

- [ ] **Step 2: Implement init and authentication**
  - Handle `ExecutionMode` evaluation.
  - Read `ROBINHOOD_USERNAME`, `ROBINHOOD_PASSWORD`, and `ROBINHOOD_TOTP`.
  - Call `r.login(...)` inside a try/except, translating login failures to `BrokerAuthenticationError`.

- [ ] **Step 3: Implement `get_capabilities` and `get_account_snapshot`**
  - Map user profile balance attributes (`cash`, `buying_power`, `equity`) to `AccountRiskSnapshot`.

- [ ] **Step 4: Implement `get_positions`**
  - Parse holdings dictionary, enforcing filtering to keep only stock assets.
  - Map target entries to `BrokerPosition` objects.

- [ ] **Step 5: Implement `place_order`**
  - Guard options placing with `UnsupportedCapabilityError`.
  - Place standard limit stock orders via `r.orders.order_buy_limit` / `order_sell_limit`.
  - Map return dictionaries to `OrderExecutionResult`.

- [ ] **Step 6: Implement order inquiries and cancellation**
  - Implement `get_orders` and `cancel_order` with mapped statuses.

- [ ] **Step 7: Implement robust exception mapping helper**
  - Catch `requests.exceptions.RequestException`, authentication mismatches, API rate limits, and map them to their corresponding `BrokerError` equivalents.

---

## Task 4: Verification and Boundary Auditing

- [ ] **Step 1: Run unit tests**
  Run:
  ```bash
  uv run pytest tests/test_robinhood_adapter.py -v
  ```
  *(Expected: All unit tests pass)*

- [ ] **Step 2: Verify package boundaries**
  Run:
  ```bash
  uv run pytest tests/test_broker_boundaries.py -v
  ```
  *(Expected: Passes, verifying `robinhood.py` introduces no core package leakage)*

- [ ] **Step 3: Run full linting, format, and static analysis checks**
  Run:
  ```bash
  uv run ruff check .
  uv run mypy src tests
  ```

---

## Verification Plan

### Automated Tests
- Run tests for the Robinhood adapter specifically:
  ```bash
  uv run pytest tests/test_robinhood_adapter.py
  ```
- Run complete boundaries tests:
  ```bash
  uv run pytest tests/test_broker_boundaries.py
  ```
- Run full test suite:
  ```bash
  uv run pytest
  ```

### Manual Verification
- Verify registration via the factory by executing an interactive python command:
  ```bash
  uv run python -c "from prescient.broker import get_broker_adapter; print(get_broker_adapter('robinhood', 'live'))"
  ```
  *(Expected: Fails with `BrokerAuthenticationError` if credentials are missing from environment, confirming registration works)*
