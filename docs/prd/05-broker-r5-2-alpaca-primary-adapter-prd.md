# PRD: R5.2 Alpaca Primary Broker Adapter

## Ownership

Owner: Ours, GPT, Gem

Source note: Alpaca is the primary broker (supports options + free unlimited paper trading) [Ours, GPT, Gem]. The adapter must implement the standard `BrokerAdapter` Protocol and interface with Alpaca's REST services using the official `alpaca-py` SDK.

---

## Objective

Define the integration design, credential management, endpoints routing, position/order translation, option symbol parsing, and error-mapping rules for the concrete `AlpacaAdapter` in `prescient.broker.alpaca`.

R5.2 answers:
```text
How does the system translate the unified BrokerAdapter Protocol requests and responses to and from the official Alpaca Trading API, supporting both Stock and Call Option transactions across Paper and Live environments?
```

---

## Background

Alpaca is the primary brokerage target for Prescient because:
1. It offers a fully functional, free sandbox environment (Paper Trading) with virtual buying power.
2. It supports options trading programmatically.
3. The official `alpaca-py` Python SDK is pre-installed.

This adapter will wrap the Alpaca SDK, handling authentication, mode switching, format translation, and mapping Alpaca's exceptions to the standardized `BrokerError` classes.

---

## Technical Architecture & Requirements

### R5.2.1 Credentials & Base URL Routing

The adapter must initialize its underlying Alpaca clients based on system configuration and environment variables.

1. **Authentication Keys**:
   - `ALPACA_API_KEY_ID`: API key ID.
   - `ALPACA_API_SECRET_KEY`: API secret key.
   - These keys must be loaded securely from the environment. If either key is missing or empty when instantiating the adapter, the adapter must raise a `BrokerAuthenticationError`.

2. **Base URL Resolution**:
   Depending on the `ExecutionMode` requested at instantiation:
   - `ExecutionMode.PAPER`: Resolve to `https://paper-api.alpaca.markets`. Set `paper=True` on client initialization.
   - `ExecutionMode.LIVE` / `ExecutionMode.PROPOSE_ONLY`: Resolve to `https://api.alpaca.markets`. Set `paper=False` on client initialization.

---

### R5.2.2 SDK Clients Initialization

The adapter should encapsulate the following official SDK classes from `alpaca.trading.client`:
* `TradingClient`: For account state, order execution, position queries, and cancellations.

```python
from alpaca.trading.client import TradingClient

class AlpacaAdapter:
    def __init__(self, execution_mode: ExecutionMode, api_key: str, api_secret: str):
        self.execution_mode = execution_mode
        self.paper = (execution_mode == ExecutionMode.PAPER)
        
        # Instantiate trading client
        self.client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=self.paper
        )
```

---

### R5.2.3 Model & Data Mapping

All requests and responses must be mapped to and from Alpaca models to ensure the core application remains isolated from `alpaca-py` types.

#### 1. Account Snapshot Mapping
Query `TradingClient.get_account()` and map:
- `cash` -> `AccountRiskSnapshot.cash` (converted to float)
- `buying_power` -> `AccountRiskSnapshot.buying_power` (converted to float)
- `portfolio_value` / `equity` -> `AccountRiskSnapshot.equity` (converted to float)

#### 2. Position Mapping
Query `TradingClient.get_all_positions()`. Map each `Position` to `BrokerPosition`:
- `symbol` -> `BrokerPosition.symbol`
- `asset_class` -> Determine `TradeExpression` (`AssetClass.US_OPTION` -> `TradeExpression.CALL_OPTION`, `AssetClass.US_EQUITY` -> `TradeExpression.STOCK`)
- `qty` -> `BrokerPosition.qty` (cast to float)
- `market_value` -> `BrokerPosition.market_value` (cast to float)
- `avg_entry_price` -> `BrokerPosition.average_entry_price` (cast to float)

#### 3. Option Symbol Translation
Alpaca uses the standard OCC format for options contract symbols (e.g. `AAPL260619C00150000`).
* Internal option symbols in Prescient must be normalized by the Alpaca adapter when placing orders or parsing position lists.
* Ensure leading/trailing whitespace is stripped and formatting aligns with the Alpaca API specifications.

#### 4. Order Placing (`place_order`)
Submit the order proposal via `TradingClient.submit_order()` using the correct sub-request model:
* **For Stock (`TradeExpression.STOCK`)**: Use `MarketOrderRequest` or `LimitOrderRequest` from `alpaca.trading.requests` with `symbol`, `qty`, `side=OrderSide.BUY` (or sell), `time_in_force=TimeInForce.DAY`.
* **For Option (`TradeExpression.CALL_OPTION`)**: Use the corresponding order request with options contracts asset specifications.
* Map the returned Alpaca `Order` object to `OrderExecutionResult`:
  - `id` -> `OrderExecutionResult.order_id`
  - `status` -> Map Alpaca order status (`OrderStatus.FILLED` -> `BrokerOrderStatus.FILLED`, `OrderStatus.NEW`/`ACCEPTED` -> `BrokerOrderStatus.OPEN`, etc.)
  - `filled_qty` -> `OrderExecutionResult.filled_qty`
  - `avg_fill_price` -> `OrderExecutionResult.avg_fill_price` (if available, otherwise limit price)

---

### R5.2.4 Standardized Exception Handling

All API calls to Alpaca must wrap errors in try-except blocks, catching exceptions from `alpaca.common.exceptions` (or general network errors) and mapping them:

| Alpaca / HTTP Error | Unified Exception |
| :--- | :--- |
| `APIError` with code `401` / `403` (Unauthorized) | `BrokerAuthenticationError` |
| `APIError` with code `429` (Rate limit exceeded) | `BrokerRateLimitError` |
| `APIError` with code `400` / `422` (Invalid qty, insufficient buying power) | `BrokerExecutionError` |
| `APIError` with code `404` (Asset not found) | `BrokerExecutionError` |
| Connection timeouts, host unreachable, DNS failures | `BrokerConnectionError` |
| Any other unhandled Alpaca exceptions | `BrokerError` |

---

### R5.2.5 Capabilities Specification

The Alpaca adapter must report the following capabilities when queried via `get_capabilities()`:
* `supports_options = True`
* `supports_paper_trading = True`
* `broker_name = "alpaca"`

---

## Acceptance Criteria

1. **Protocol Compliance**: `AlpacaAdapter` fully implements all structural requirements of the `BrokerAdapter` Protocol.
2. **Environment Routing**: Confirm that instantiating the adapter in `PAPER` mode directs requests to the Alpaca paper API (`paper-api.alpaca.markets`), and `LIVE` mode targets the live API (`api.alpaca.markets`).
3. **Pydantic Serialization**: Queries for positions, account state, and order submissions return correct, fully populated Pydantic models.
4. **Symbol Normalization**: OCC options symbols are translated accurately and accepted by the Alpaca API.
5. **Error Mapping Verified**: Mocked tests simulating Alpaca API rate limits, timeouts, and authentication failures raise their respective unified `BrokerError` subclasses.
6. **No Leaked Dependencies**: The `alpaca-py` library is imported strictly inside the adapter file (`prescient/broker/alpaca.py`), keeping core strategy and risk engines clear of Alpaca SDK references.

---

## Non-Goals

* No support for cryptocurrency, futures, or fixed-income assets.
* No streaming websocket client implementation for execution monitoring in this adapter (streaming event listeners are handled by events or runtime scheduler wrappers).
