# PRD: R5.1 Swappable Broker Adapter

## Ownership

Owner: Ours

Source note: Requirement from Ours: the broker adapter must be a swappable interface (using structural Protocols or ABCs). The runtime, risk gatekeeper, and signal modules must be fully decoupled from broker-specific SDKs, allowing providers to be swapped via configuration without modifying core strategy logic.

---

## Objective

Define the unified interface, models, factory pattern, and error-handling framework for swappable broker execution adapters in `prescient.broker`. 

R5.1 answers:
```text
How can the execution layer interact with diverse broker platforms (Alpaca, Robinhood) using a single interface, while ensuring all account state fetching, ordering, and capability checking are completely decoupled from broker-specific SDKs?
```

---

## Background

To execute trades, check buying power, and retrieve positions, the Prescient risk gatekeeper and runtime orchestrators must interact with external brokerages. Currently:
1. `alpaca-py` is installed in `pyproject.toml` as the primary broker library, but no implementation has been committed.
2. Robinhood Agentic is targeted as a secondary adapter (stocks only, real money).
3. Directly importing broker SDKs into core risk engines (e.g., `gatekeeper.py` or `position_sizing.py`) violates the Dependency Inversion Principle, couples the code to specific broker APIs, makes unit testing extremely difficult, and risks accidental live execution during tests.

Decoupling the brokers behind a strict Python `typing.Protocol` (structural typing) or ABC enables us to swap brokers via a single config line, inject mocks for unit testing, enforce capabilities checks (e.g., preventing option orders on stocks-only brokers), and guarantee compile-time safety.

---

## Technical Architecture & Requirements

### R5.1.1 Unified Broker Interface (`BrokerAdapter`)

The broker layer must define a Python Protocol `BrokerAdapter` in `prescient.broker.interfaces` (or `prescient.broker.protocols`). This interface is the sole point of contact between the runtime orchestrator/gatekeeper and the brokers.

The protocol must support the following methods:

#### 1. Account Snapshot
Fetches the broker's real account balances. This is the **single source of truth** for the risk gatekeeper's preflight buying power checks (satisfying R5.5 and R5.6):
```python
from prescient.risk.models import AccountRiskSnapshot

def get_account_snapshot(self) -> AccountRiskSnapshot:
    """Fetch the real-time account equity, cash, and buying power from the broker API.
    
    Returns:
        AccountRiskSnapshot: A unified Pydantic model with float values.
        
    Raises:
        BrokerError: Wrapped exception for connection/API failures.
    """
    ...
```

#### 2. Positions Listing
Retrieves currently open positions:
```python
from typing import Sequence
from prescient.broker.models import BrokerPosition

def get_positions(self) -> Sequence[BrokerPosition]:
    """Fetch all open equity and option positions currently held in the account.
    
    Returns:
        Sequence[BrokerPosition]: List of unified position objects.
    """
    ...
```

#### 3. Order Placement
Submits a trade proposal for execution:
```python
from prescient.risk.models import RiskOrderProposal
from prescient.broker.models import OrderExecutionResult

def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
    """Submit a buy/sell order for execution to the broker.
    
    Args:
        proposal: The validated order proposal containing ticker, expression, limit price, and quantity.
        
    Returns:
        OrderExecutionResult: Detailed state of the submitted order (ID, status, fill details).
        
    Raises:
        UnsupportedCapabilityError: If the order type is unsupported by the broker.
        BrokerError: If execution fails.
    """
    ...
```

#### 4. Order Inquiries and Cancellation
Monitors and cancels outstanding orders:
```python
from typing import Sequence
from prescient.broker.models import BrokerOrder, OrderStatusFilter

def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
    """Fetch recent orders, optionally filtered by status (open, filled, cancelled)."""
    ...

def cancel_order(self, order_id: str) -> None:
    """Cancel an active open order by its broker-assigned unique identifier."""
    ...
```

#### 5. Broker Capabilities
Exposes structural capabilities of the broker instance:
```python
from prescient.broker.models import BrokerCapabilities

def get_capabilities(self) -> BrokerCapabilities:
    """Return static capabilities configuration for this broker instance (e.g. supports options)."""
    ...
```

---

### R5.1.2 Unified Broker Models

The broker package must define standard models inside `prescient.broker.models` using Pydantic (or frozen dataclasses) to serialize and structure data returned from the broker APIs.

* **`BrokerPosition`**:
  * `symbol`: Normalized ticker symbol (e.g., `"AAPL"`, or option OCC format `"AAPL  260619C00150000"`).
  * `expression`: `TradeExpression` (`STOCK` or `CALL_OPTION`).
  * `qty`: `float` (supports fractional shares if the broker does).
  * `market_value`: `float`.
  * `average_entry_price`: `float`.
* **`BrokerOrder`**:
  * `order_id`: String identifier assigned by the broker.
  * `symbol`: String.
  * `qty`: `int`.
  * `filled_qty`: `int`.
  * `limit_price`: `float | None`.
  * `status`: `BrokerOrderStatus` (`OPEN`, `FILLED`, `CANCELLED`, `REJECTED`).
  * `submitted_at`: `datetime`.
* **`BrokerCapabilities`**:
  * `supports_options`: `bool` (Alpaca = `True`, Robinhood = `False` today).
  * `supports_paper_trading`: `bool` (Alpaca = `True`, Robinhood = `False` today).
  * `broker_name`: `str`.

---

### R5.1.3 Broker Registry and Factory Pattern

To build broker adapters dynamically, the broker package must implement a registry and factory resolver:

```python
from prescient.broker.interfaces import BrokerAdapter
from prescient.risk.models import ExecutionMode

def get_broker_adapter(
    broker_name: str,
    execution_mode: ExecutionMode,
    **kwargs: Any
) -> BrokerAdapter:
    """Resolve and instantiate a configured broker adapter.
    
    Args:
        broker_name: Registered name (e.g. "alpaca", "robinhood", "mock").
        execution_mode: Mode (paper, live, propose-only).
        
    Raises:
        ValueError: If broker_name is not registered.
        ConfigurationError: If paper mode is requested for a broker with no paper support.
    """
    ...
```

* Dynamic configurations should map environment secrets (`ALPACA_API_KEY_ID`, `ROBINHOOD_CREDENTIALS`) into the broker constructor keyword arguments.
* The factory must validate that a broker adapter supports the requested execution mode (e.g. throwing an error if Robinhood is constructed with `execution_mode="paper"`).

---

### R5.1.4 Standardized Configuration Schema

The broker choice is configured in `config/config.yaml` or equivalent environment structures:

```yaml
broker:
  name: "alpaca"                 # Options: "alpaca", "robinhood", "mock"
  execution_mode: "paper"       # Options: "paper", "propose_only", "live"
  slippage_buffer_pct: 0.01      # Slippage protection buffer
  connection_timeout_sec: 10
```

---

### R5.1.5 Unified Broker Exceptions

Swapping adapters must never leak implementation details or SDK exceptions to the runtime layer. The package must define a unified exception hierarchy:

* **`BrokerError`**: Base exception class for all execution failures.
  * **`BrokerConnectionError`**: Network timeout, connection refused, dns failures.
  * **`BrokerAuthenticationError`**: Stale keys, invalid API credentials, rejected tokens.
  * **`BrokerRateLimitError`**: Exceeding rate limits.
  * **`BrokerExecutionError`**: Order rejected by the broker risk department, invalid ticker, market closed.
  * **`UnsupportedCapabilityError`**: Fired when trying to place options trades on stocks-only brokers.

Concrete adapters must catch their respective SDK errors (e.g., `AlpacaAPIError` or raw HTTP errors) and raise a matching unified `BrokerError`.

---

### R5.1.6 Safety Safeguards & Capabilities Check

Before executing `place_order`, the adapter wrapper (or the runtime orchestrator utilizing capabilities) must run a capabilities preflight check:

1. Compare `proposal.expression` with `capabilities.supports_options`. If an option trade is proposed to a broker with `supports_options=False`, reject the trade immediately with `UnsupportedCapabilityError`.
2. Compare `execution_mode` with `capabilities.supports_paper_trading`. If `ExecutionMode.PAPER` is configured but the broker has `supports_paper_trading=False`, crash during startup rather than allowing accidental live trades.

---

## Acceptance Criteria

1. **Protocol Specifications Exist**: A formal structural type `BrokerAdapter` Protocol is declared.
2. **Zero Concrete Imports in Core**: The boundary tests (`tests/test_risk_boundaries.py` and `tests/test_data_boundaries.py`) pass, ensuring that no files in `prescient.signal`, `prescient.risk`, or `prescient.runtime` import code from concrete adapters directly.
3. **Execution Mode Guard**: Constructing a Robinhood adapter under `ExecutionMode.PAPER` raises a clear `ConfigurationError`.
4. **Adapter Capability Rejections**: Submitting a `CALL_OPTION` proposal to an adapter with `supports_options=False` raises an `UnsupportedCapabilityError` without hitting the broker network.
5. **Unified Error Catching**: Mocking a network failure on Alpaca/Robinhood bubbled as a standardized `BrokerConnectionError` to the caller.
6. **Factory Resolution**: Requesting an unregistered broker name raises a clear `ValueError` specifying the valid registry options.

---

## Non-Goals

* No handling of OAuth web auth redirection loops within this package.
* No internal caching of market positions (positions must always be queried fresh from the broker API as the single source of truth).
* No multi-broker order split/routing (a single broker adapter handles all executions for a run).
