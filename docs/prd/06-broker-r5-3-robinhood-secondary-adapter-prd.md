# PRD: R5.3 Robinhood Secondary Broker Adapter

## Ownership

Owner: Ours

Source note: Robinhood is the secondary adapter (⚠️ stocks only today, no options yet; real money, no paper) [Ours]. The adapter must implement the standard `BrokerAdapter` Protocol and interface with Robinhood's unofficial API using the `robin-stocks` library.

---

## Objective

Define the integration design, credential management, position/order translation, and error-mapping rules for the concrete `RobinhoodAdapter` in `prescient.broker.robinhood`.

R5.3 answers:
```text
How does the system translate the unified BrokerAdapter Protocol requests and responses to and from the robin-stocks API, supporting only Stock transactions in a Live environment?
```

---

## Background

Robinhood is the secondary brokerage target for Prescient because:
1. It offers commission-free trading.
2. The `robin-stocks` Python SDK allows programmatic interaction.

However, unlike Alpaca, Robinhood does not offer a paper trading environment and this adapter will only support equities initially.

This adapter will wrap the `robin-stocks` SDK, handling authentication via username/password, and mapping exceptions to the standardized `BrokerError` classes.

---

## Technical Architecture & Requirements

### R5.3.1 Credentials & Initialization

The adapter must initialize its underlying Robinhood session based on system configuration and environment variables.

1. **Authentication Keys**:
   - `ROBINHOOD_USERNAME`: Robinhood login email.
   - `ROBINHOOD_PASSWORD`: Robinhood login password.
   - `ROBINHOOD_MFA_CODE` (Optional): Multi-factor authentication code.
   - These credentials must be loaded securely from the environment. If either username or password is missing when instantiating the adapter, it must raise a `BrokerAuthenticationError`.

2. **Execution Mode Validation**:
   - `ExecutionMode.PAPER` is NOT supported. If requested, raise a `ConfigurationError`.

### R5.3.2 SDK Clients Initialization

The adapter uses the module-level functions provided by `robin_stocks.robinhood`. To avoid global state conflicts if multiple instances were possible (though unlikely), authentication can be managed via the standard `login` method.

### R5.3.3 Model & Data Mapping

All requests and responses must be mapped to and from `robin-stocks` dictionary models.

#### 1. Account Snapshot Mapping
Query `rh.profiles.load_account_profile()` or `rh.profiles.build_user_profile()` and map:
- `cash` -> `AccountRiskSnapshot.cash`
- `buying_power` -> `AccountRiskSnapshot.buying_power`
- `portfolio_value` / `equity` -> `AccountRiskSnapshot.equity`

#### 2. Position Mapping
Query `rh.account.build_holdings()`. Map each holding to `BrokerPosition`:
- `symbol` -> `BrokerPosition.symbol`
- `asset_class` -> `TradeExpression.STOCK`
- `qty` -> `BrokerPosition.qty` (cast to float)
- `market_value` -> `BrokerPosition.market_value` (cast to float)
- `avg_entry_price` -> `BrokerPosition.average_entry_price` (cast to float)

#### 3. Order Placing (`place_order`)
Submit the order proposal via `rh.orders.order_buy_limit()` or `rh.orders.order_sell_limit()`.
* **For Option (`TradeExpression.CALL_OPTION`)**: Raise `UnsupportedCapabilityError`.
* Map the returned dict to `OrderExecutionResult`.

### R5.3.4 Standardized Exception Handling

API calls must wrap errors and exceptions raised by `robin_stocks` (or `requests`) and map them to unified exceptions:
- Authentication failures -> `BrokerAuthenticationError`
- Connection errors -> `BrokerConnectionError`
- Invalid parameters / HTTP 400s -> `BrokerExecutionError`
- Other unhandled -> `BrokerError`

### R5.3.5 Capabilities Specification

The Robinhood adapter must report the following capabilities:
* `supports_options = False`
* `supports_paper_trading = False`
* `broker_name = "robinhood"`

---

## Acceptance Criteria

1. **Protocol Compliance**: `RobinhoodAdapter` fully implements the `BrokerAdapter` Protocol.
2. **Environment Restriction**: Instantiating the adapter in `PAPER` mode raises a `ConfigurationError`. Option orders raise `UnsupportedCapabilityError`.
3. **Pydantic Serialization**: Queries return correct, fully populated Pydantic models.
4. **Error Mapping Verified**: Mocked tests simulating Robinhood API rate limits, timeouts, and authentication failures raise their respective unified `BrokerError` subclasses.
