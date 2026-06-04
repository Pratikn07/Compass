# Broker Adapter Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Prescient's Alpaca and Robinhood broker adapter tests so real-money-adjacent order paths are covered with mocks only.

**Architecture:** This is a test-only hardening pass. The implementation adds broker-specific characterization tests around request shape, status mapping, exception mapping, and concrete factory/wrapper safety behavior while preserving the existing `risk -> broker` execution rails unchanged. If any new test fails, the executor reports a product finding and stops before editing broker, risk, or signal source code.

**Tech Stack:** Python 3.11+, pytest, unittest.mock, alpaca-py request/enum models, robin-stocks mocked API surface, Prescient Pydantic models.

---

## File Structure

- Modify: `tests/test_alpaca_adapter.py`
  - Add Alpaca broker helper builders.
  - Add order request shape and status mapping tests.
  - Add order-path exception mapping tests.
  - Add concrete `get_broker_adapter("alpaca", "propose_only")` no-submit safety test.
- Modify: `tests/test_robinhood_adapter.py`
  - Add Robinhood HTTP-error helper.
  - Add stock order request shape and status mapping tests.
  - Add option rejection no-call test.
  - Add order-path exception mapping tests.
  - Add concrete Robinhood kill-switch no-profile/no-order safety test.
- Read-only reference: `src/prescient/broker/alpaca.py`
- Read-only reference: `src/prescient/broker/robinhood.py`
- Read-only reference: `src/prescient/broker/execution_guard.py`
- Read-only reference: `src/prescient/risk/models.py`

## Guardrails

- Do not call live Alpaca, Robinhood, or paper broker services.
- Do not use real credentials or environment credentials.
- Do not edit `src/prescient/risk/` or `src/prescient/signal/`.
- Do not weaken `CLAUDE.md`, execution-mode defaults, risk caps, kill-switch behavior, or preflight behavior.
- If a test exposes wrong behavior, record the actual vs. expected result and stop for human triage.
- Use mocks for every broker client call.

### Task 1: Baseline Broker Test State

**Files:**
- Read: `tests/test_alpaca_adapter.py`
- Read: `tests/test_robinhood_adapter.py`
- Read: `tests/test_r5_6_preflight_check.py`
- Read: `tests/test_r8_3_broker_kill_switch.py`

- [ ] **Step 1: Run the current broker-focused tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  tests/test_r5_6_preflight_check.py \
  tests/test_r8_3_broker_kill_switch.py \
  -q
```

Expected: all selected tests pass before new coverage is added.

- [ ] **Step 2: Capture current broker coverage**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  --cov=prescient.broker.alpaca \
  --cov=prescient.broker.robinhood \
  --cov-report=term-missing \
  -q
```

Expected: coverage command prints uncovered lines for both concrete adapters. If `pytest-cov` is unavailable, run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
uv pip install pytest-cov
python -m pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  --cov=prescient.broker.alpaca \
  --cov=prescient.broker.robinhood \
  --cov-report=term-missing \
  -q
```

Expected: coverage command succeeds after installing the test-only coverage plugin into the virtualenv.

### Task 2: Alpaca Order Request Shape And Status Mapping

**Files:**
- Modify: `tests/test_alpaca_adapter.py`
- Read-only reference: `src/prescient/broker/alpaca.py`

- [ ] **Step 1: Extend imports in `tests/test_alpaca_adapter.py`**

Add `pytest` already exists. Modify the Alpaca enum import and broker model import blocks to include these names:

```python
from alpaca.trading.enums import OrderSide, TimeInForce

from prescient.broker.models import (
    BrokerAuthenticationError,
    BrokerCapabilities,
    BrokerConnectionError,
    BrokerExecutionError,
    BrokerOrderStatus,
    BrokerRateLimitError,
    UnsupportedCapabilityError,
)
from prescient.risk.models import (
    AccountRiskSnapshot,
    ExecutionMode,
    RiskOrderProposal,
    TradeExpression,
)
```

- [ ] **Step 2: Add Alpaca test helpers below the imports**

```python
def _alpaca_order(
    *,
    order_id: str = "alpaca-order-1",
    status: str = "accepted",
    filled_qty: str | None = "0.0",
    filled_avg_price: str | None = None,
) -> Mock:
    order = Mock()
    order.id = order_id
    order.status = Mock()
    order.status.value = status
    order.filled_qty = filled_qty
    order.filled_avg_price = filled_avg_price
    return order


def _proposal(
    target: str = " AAPL ",
    *,
    expression: str = "STOCK",
    estimated_entry_cost: float = 150.0,
) -> RiskOrderProposal:
    return RiskOrderProposal(
        target=target,
        expression=expression,
        estimated_entry_cost=estimated_entry_cost,
        maximum_loss=30.0,
    )


def _make_alpaca_api_error(status_code: int, message: str) -> APIError:
    mock_http_err = Mock()
    mock_http_err.response = Mock()
    mock_http_err.response.status_code = status_code
    return APIError(
        error=json.dumps({"code": status_code, "message": message}),
        http_error=mock_http_err,
    )
```

- [ ] **Step 3: Add the status mapping and request shape test**

Append this test in the `# Order placement` area:

```python
@pytest.mark.parametrize(
    (
        "alpaca_status",
        "expected_status",
        "filled_qty",
        "filled_avg_price",
        "expected_filled_qty",
        "expected_avg_fill_price",
    ),
    [
        ("filled", BrokerOrderStatus.FILLED, "1.0", "151.25", 1, 151.25),
        ("canceled", BrokerOrderStatus.CANCELLED, "0.0", None, 0, None),
        ("rejected", BrokerOrderStatus.REJECTED, "0.0", None, 0, None),
        ("accepted", BrokerOrderStatus.OPEN, "0.0", None, 0, None),
    ],
)
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_status_and_request_shape(
    mock_trading_client_cls,
    alpaca_status: str,
    expected_status: BrokerOrderStatus,
    filled_qty: str | None,
    filled_avg_price: str | None,
    expected_filled_qty: int,
    expected_avg_fill_price: float | None,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.return_value = _alpaca_order(
        status=alpaca_status,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
    )

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    result = adapter.place_order(_proposal(target=" msft "))

    assert result.order_id == "alpaca-order-1"
    assert result.status == expected_status
    assert result.filled_qty == expected_filled_qty
    assert result.avg_fill_price == expected_avg_fill_price
    assert f"Status: {alpaca_status}" in result.message

    mock_client.submit_order.assert_called_once()
    order_request = mock_client.submit_order.call_args.args[0]
    assert order_request.symbol == "MSFT"
    assert float(order_request.qty) == 1.0
    assert order_request.side == OrderSide.BUY
    assert order_request.time_in_force == TimeInForce.DAY
```

- [ ] **Step 4: Run the Alpaca order mapping test**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest tests/test_alpaca_adapter.py::test_alpaca_place_order_maps_status_and_request_shape -q
```

Expected: pass. If this fails, capture the failure as a broker adapter finding and stop before editing source code.

- [ ] **Step 5: Commit or record the test-only change**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add tests/test_alpaca_adapter.py
  git commit -m "test: harden alpaca order status mapping"
else
  echo "No git root detected; test-only Alpaca status mapping change remains uncommitted."
fi
```

Expected: either a commit is created, or the shell prints that no git root is present.

### Task 3: Alpaca Order Rejection And No-Submit Paths

**Files:**
- Modify: `tests/test_alpaca_adapter.py`
- Read-only reference: `src/prescient/broker/alpaca.py`

- [ ] **Step 1: Add Alpaca API-error mapping tests for `submit_order`**

Append this test after the existing Alpaca exception mapping tests:

```python
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, BrokerAuthenticationError),
        (403, BrokerAuthenticationError),
        (429, BrokerRateLimitError),
        (400, BrokerExecutionError),
        (422, BrokerExecutionError),
        (404, BrokerExecutionError),
    ],
)
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_submit_order_api_errors(
    mock_trading_client_cls,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.side_effect = _make_alpaca_api_error(status_code, "order failed")

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with pytest.raises(expected_error):
        adapter.place_order(_proposal())
```

- [ ] **Step 2: Add Alpaca connection-error mapping test for `submit_order`**

Append this test after `test_alpaca_place_order_maps_submit_order_api_errors`:

```python
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_submit_order_connection_error(
    mock_trading_client_cls,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.side_effect = ConnectionError("timeout connection dns lookup")

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with pytest.raises(BrokerConnectionError):
        adapter.place_order(_proposal())
```

- [ ] **Step 3: Add Alpaca unsupported options no-submit test**

Append this test after the connection-error test:

```python
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_rejects_options_when_capability_disabled_before_submit(
    mock_trading_client_cls,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with patch.object(
        adapter,
        "get_capabilities",
        return_value=BrokerCapabilities(
            supports_options=False,
            supports_paper_trading=True,
            broker_name="alpaca",
        ),
    ):
        with pytest.raises(UnsupportedCapabilityError, match="options capability disabled"):
            adapter.place_order(
                _proposal(
                    target="AAPL260619C00150000",
                    expression="CALL_OPTION",
                    estimated_entry_cost=1.50,
                )
            )

    mock_client.submit_order.assert_not_called()
```

- [ ] **Step 4: Run the new Alpaca rejection-path tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_alpaca_adapter.py::test_alpaca_place_order_maps_submit_order_api_errors \
  tests/test_alpaca_adapter.py::test_alpaca_place_order_maps_submit_order_connection_error \
  tests/test_alpaca_adapter.py::test_alpaca_place_order_rejects_options_when_capability_disabled_before_submit \
  -q
```

Expected: pass. If any test fails, record actual vs. expected behavior and stop before editing source code.

- [ ] **Step 5: Commit or record the test-only change**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add tests/test_alpaca_adapter.py
  git commit -m "test: cover alpaca order rejection paths"
else
  echo "No git root detected; test-only Alpaca rejection-path change remains uncommitted."
fi
```

Expected: either a commit is created, or the shell prints that no git root is present.

### Task 4: Robinhood Order Request Shape And Status Mapping

**Files:**
- Modify: `tests/test_robinhood_adapter.py`
- Read-only reference: `src/prescient/broker/robinhood.py`

- [ ] **Step 1: Extend imports in `tests/test_robinhood_adapter.py`**

Modify the broker model import block and risk model import block to include these names:

```python
from prescient.broker.models import (
    BrokerAuthenticationError,
    BrokerConnectionError,
    BrokerExecutionError,
    BrokerOrderStatus,
    BrokerRateLimitError,
    ConfigurationError,
    UnsupportedCapabilityError,
)
from prescient.risk.models import (
    ExecutionMode,
    RiskOrderProposal,
)
```

- [ ] **Step 2: Add Robinhood test helpers below the adapter fixture**

```python
def _proposal(
    target: str = " AAPL ",
    *,
    expression: str = "STOCK",
    estimated_entry_cost: float = 150.0,
) -> RiskOrderProposal:
    return RiskOrderProposal(
        target=target,
        expression=expression,
        estimated_entry_cost=estimated_entry_cost,
        maximum_loss=30.0,
    )


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(f"HTTP {status_code}")
    error.response = response
    return error
```

- [ ] **Step 3: Add Robinhood order status and request shape test**

Append this test in the `# Order placement` section:

```python
@pytest.mark.parametrize(
    (
        "state",
        "expected_status",
        "cumulative_quantity",
        "average_price",
        "expected_filled_qty",
        "expected_avg_fill_price",
    ),
    [
        ("filled", BrokerOrderStatus.FILLED, "1.0000", "150.00", 1, 150.0),
        ("cancelled", BrokerOrderStatus.CANCELLED, "0.0000", None, 0, None),
        ("canceled", BrokerOrderStatus.CANCELLED, "0.0000", None, 0, None),
        ("rejected", BrokerOrderStatus.REJECTED, "0.0000", None, 0, None),
        ("confirmed", BrokerOrderStatus.OPEN, "0.0000", None, 0, None),
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_stock_maps_status_and_request_shape(
    mock_order: MagicMock,
    adapter,
    state: str,
    expected_status: BrokerOrderStatus,
    cumulative_quantity: str,
    average_price: str | None,
    expected_filled_qty: int,
    expected_avg_fill_price: float | None,
) -> None:
    mock_order.return_value = {
        "id": "rh-order-123",
        "state": state,
        "cumulative_quantity": cumulative_quantity,
        "average_price": average_price,
    }

    result = adapter.place_order(_proposal(target=" msft "))

    assert result.order_id == "rh-order-123"
    assert result.status == expected_status
    assert result.filled_qty == expected_filled_qty
    assert result.avg_fill_price == expected_avg_fill_price
    assert f"Status: {state}" in result.message
    mock_order.assert_called_once_with(
        symbol="MSFT",
        quantity=1,
        limitPrice=150.0,
        timeInForce="gfd",
    )
```

- [ ] **Step 4: Add Robinhood option rejection no-call test**

Append this test after `test_place_order_stock_maps_status_and_request_shape`:

```python
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_rejects_options_before_order_api(
    mock_order: MagicMock,
    adapter,
) -> None:
    with pytest.raises(UnsupportedCapabilityError, match="options trading"):
        adapter.place_order(
            _proposal(
                target="AAPL260619C00150000",
                expression="CALL_OPTION",
                estimated_entry_cost=1.50,
            )
        )

    mock_order.assert_not_called()
```

- [ ] **Step 5: Run the Robinhood order mapping tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_robinhood_adapter.py::test_place_order_stock_maps_status_and_request_shape \
  tests/test_robinhood_adapter.py::test_place_order_rejects_options_before_order_api \
  -q
```

Expected: pass. If this fails, capture the failure as a broker adapter finding and stop before editing source code.

- [ ] **Step 6: Commit or record the test-only change**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add tests/test_robinhood_adapter.py
  git commit -m "test: harden robinhood order status mapping"
else
  echo "No git root detected; test-only Robinhood status mapping change remains uncommitted."
fi
```

Expected: either a commit is created, or the shell prints that no git root is present.

### Task 5: Robinhood Order Failure Mapping

**Files:**
- Modify: `tests/test_robinhood_adapter.py`
- Read-only reference: `src/prescient/broker/robinhood.py`

- [ ] **Step 1: Add Robinhood HTTP-error mapping tests for `order_buy_limit`**

Append this test after the Robinhood order placement tests:

```python
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, BrokerAuthenticationError),
        (403, BrokerAuthenticationError),
        (429, BrokerRateLimitError),
        (400, BrokerExecutionError),
        (422, BrokerExecutionError),
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_maps_order_api_http_errors(
    mock_order: MagicMock,
    adapter,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    mock_order.side_effect = _http_error(status_code)

    with pytest.raises(expected_error):
        adapter.place_order(_proposal())
```

- [ ] **Step 2: Add Robinhood connection and timeout mapping tests for `order_buy_limit`**

Append this test after `test_place_order_maps_order_api_http_errors`:

```python
@pytest.mark.parametrize(
    "side_effect",
    [
        requests.exceptions.ConnectionError("Network unreachable"),
        requests.exceptions.Timeout("Request timed out"),
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_maps_order_api_connection_failures(
    mock_order: MagicMock,
    adapter,
    side_effect: Exception,
) -> None:
    mock_order.side_effect = side_effect

    with pytest.raises(BrokerConnectionError):
        adapter.place_order(_proposal())
```

- [ ] **Step 3: Run the Robinhood failure mapping tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_robinhood_adapter.py::test_place_order_maps_order_api_http_errors \
  tests/test_robinhood_adapter.py::test_place_order_maps_order_api_connection_failures \
  -q
```

Expected: pass. If this fails, record actual vs. expected behavior and stop before editing source code.

- [ ] **Step 4: Commit or record the test-only change**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add tests/test_robinhood_adapter.py
  git commit -m "test: cover robinhood order failure mapping"
else
  echo "No git root detected; test-only Robinhood failure-mapping change remains uncommitted."
fi
```

Expected: either a commit is created, or the shell prints that no git root is present.

### Task 6: Concrete Broker Factory Safety Tests

**Files:**
- Modify: `tests/test_alpaca_adapter.py`
- Modify: `tests/test_robinhood_adapter.py`
- Read-only reference: `src/prescient/broker/__init__.py`
- Read-only reference: `src/prescient/broker/execution_guard.py`

- [ ] **Step 1: Add Alpaca propose-only factory no-submit test**

Append this test to `tests/test_alpaca_adapter.py`:

```python
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_factory_propose_only_never_submits_order(
    mock_trading_client_cls,
) -> None:
    from prescient.broker import get_broker_adapter

    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    mock_account = Mock()
    mock_account.equity = "20000.0"
    mock_account.cash = "20000.0"
    mock_account.buying_power = "20000.0"
    mock_client.get_account.return_value = mock_account

    adapter = get_broker_adapter(
        "alpaca",
        "propose_only",
        api_key="k",
        api_secret="s",
    )

    result = adapter.place_order(_proposal(target="AAPL", estimated_entry_cost=100.0))

    assert result.status == BrokerOrderStatus.OPEN
    assert result.order_id.startswith("propose-only-")
    assert "propose-only mode active" in result.message
    mock_client.get_account.assert_called_once()
    mock_client.submit_order.assert_not_called()
```

- [ ] **Step 2: Extend Robinhood imports for kill-switch factory test**

Add these imports near the other imports in `tests/test_robinhood_adapter.py`:

```python
from prescient.broker import get_broker_adapter
from prescient.safety import KillSwitchState, KillSwitchStatus
```

- [ ] **Step 3: Add Robinhood kill-switch factory no-profile/no-order test**

Append this test to `tests/test_robinhood_adapter.py`:

```python
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
@patch("prescient.broker.robinhood.r.profiles.load_account_profile")
@patch("prescient.broker.robinhood.r.login")
def test_robinhood_factory_kill_switch_blocks_before_profile_or_order(
    mock_login: MagicMock,
    mock_profile: MagicMock,
    mock_order: MagicMock,
) -> None:
    provider = MagicMock()
    provider.read_state.return_value = KillSwitchState(status=KillSwitchStatus.ACTIVE)

    adapter = get_broker_adapter(
        "robinhood",
        "live",
        username="test",
        password="test",
        kill_switch_provider=provider,
    )

    with pytest.raises(BrokerExecutionError, match="Kill switch active"):
        adapter.place_order(_proposal(target="AAPL", estimated_entry_cost=100.0))

    mock_login.assert_called_once()
    provider.read_state.assert_called_once()
    mock_profile.assert_not_called()
    mock_order.assert_not_called()
```

- [ ] **Step 4: Run the concrete broker safety tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_alpaca_adapter.py::test_alpaca_factory_propose_only_never_submits_order \
  tests/test_robinhood_adapter.py::test_robinhood_factory_kill_switch_blocks_before_profile_or_order \
  -q
```

Expected: pass. If this fails, record the exact unsafe call that happened and stop before editing source code.

- [ ] **Step 5: Commit or record the test-only change**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git add tests/test_alpaca_adapter.py tests/test_robinhood_adapter.py
  git commit -m "test: assert concrete broker factory safety"
else
  echo "No git root detected; concrete broker factory safety tests remain uncommitted."
fi
```

Expected: either a commit is created, or the shell prints that no git root is present.

### Task 7: Full Verification And Findings Report

**Files:**
- Read: `tests/test_alpaca_adapter.py`
- Read: `tests/test_robinhood_adapter.py`
- Read: `src/prescient/broker/alpaca.py`
- Read: `src/prescient/broker/robinhood.py`

- [ ] **Step 1: Run the full broker adapter test files**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest tests/test_alpaca_adapter.py tests/test_robinhood_adapter.py -q
```

Expected: all Alpaca and Robinhood tests pass.

- [ ] **Step 2: Run broker-adjacent wrapper tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_broker_adapter.py \
  tests/test_r5_4_execution_mode_flag.py \
  tests/test_r5_6_preflight_check.py \
  tests/test_r8_3_broker_kill_switch.py \
  -q
```

Expected: all broker factory, execution mode, preflight, and kill-switch tests pass.

- [ ] **Step 3: Run the full repository test suite**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Run adapter coverage report**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
source .venv/bin/activate 2>/dev/null || true
python -m pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  --cov=prescient.broker.alpaca \
  --cov=prescient.broker.robinhood \
  --cov-report=term-missing \
  -q
```

Expected: report shows improved line coverage for `prescient.broker.alpaca` and `prescient.broker.robinhood`; remaining uncovered lines are reviewed as either low-risk branches or candidates for a later PRD.

- [ ] **Step 5: Produce the execution summary**

Write the final summary in this format:

```markdown
Broker adapter test hardening complete.

Tests added:
- Alpaca request shape and status mapping
- Alpaca submit_order exception mapping
- Alpaca unsupported options no-submit path
- Robinhood request shape and status mapping
- Robinhood option rejection no-call path
- Robinhood order API exception mapping
- Concrete broker factory safety tests

Verification:
- `python -m pytest tests/test_alpaca_adapter.py tests/test_robinhood_adapter.py -q`: include the exact terminal summary from Step 1.
- `python -m pytest tests/test_broker_adapter.py tests/test_r5_4_execution_mode_flag.py tests/test_r5_6_preflight_check.py tests/test_r8_3_broker_kill_switch.py -q`: include the exact terminal summary from Step 2.
- `python -m pytest -q`: include the exact terminal summary from Step 3.
- Adapter coverage: include the exact Alpaca and Robinhood coverage lines from Step 4.

Findings:
- Real product bugs: list concrete failures, or write `none`.
- Wrong test assumptions: list concrete assumptions, or write `none`.
- Remaining uncovered risky lines: list concrete lines, or write `none`.
```

Use actual command output in the verification section.

## Self-Review

- Spec coverage:
  - Alpaca order placement: Task 2.
  - Alpaca rejection/failure modes: Task 3.
  - Robinhood order placement: Task 4.
  - Robinhood rejection/failure modes: Task 5.
  - Mock-only/no-live safety: Tasks 2 through 6 use patched broker clients; Task 6 proves concrete factory wrappers block unsafe execution.
  - Full verification and coverage reporting: Task 7.
- Placeholder scan:
  - This plan contains no deferred implementation steps.
  - The final report template tells the executor exactly which command output to include.
- Type consistency:
  - `RiskOrderProposal` uses valid `expression` values: `"STOCK"` and `"CALL_OPTION"`.
  - Error classes and status enums match `prescient.broker.models`.
  - Safety tests use `KillSwitchState(status=KillSwitchStatus.ACTIVE)` from `prescient.safety`.
