# PRD: R5.3 Robinhood Secondary Broker Adapter

## Ownership

Owner: Ours

Source note: Robinhood is the secondary adapter for agentic trading. It is strictly limited to **stocks only** (no options) and **real money** (no paper trading) for the MVP.

---

## Objective

Define the integration design, credential management, capabilities, and error mapping for the `RobinhoodAdapter` in `prescient.broker.robinhood`. This adapter must implement the standardized `BrokerAdapter` Protocol established in R5.1.

R5.3 answers:
```text
How does the system securely execute real-money stock trades via Robinhood while firmly rejecting paper trading and options requests, ensuring adherence to the unified BrokerAdapter Protocol?
```

---

## Background

While Alpaca (R5.2) serves as the primary broker providing a robust paper sandbox and options support, the system also supports executing live equity trades on Robinhood. Since Robinhood lacks an official public developer API for individuals, the community-supported `robin_stocks` library is typically used.

Unlike Alpaca, Robinhood:
1. Has **no paper trading** environment.
2. Uses distinct authentication (Username/Password/TOTP) rather than API Keys.
3. Often holds mixed portfolios (Crypto, Options, Stocks). The adapter must filter out unsupported assets to prevent downstream parser failures.

---

## Functional Requirements

### R5.3.1 Capabilities & Mode Guardrails

The Robinhood adapter must statically declare its limitations and enforce them during instantiation and execution.

1. **Capabilities Specification**:
   When queried via `get_capabilities()`, the adapter must return:
   * `supports_options = False`
   * `supports_paper_trading = False`
   * `broker_name = "robinhood"`

2. **Mode Guarding on Init**:
   If the adapter is instantiated with `ExecutionMode.PAPER`, it must instantly raise a `ConfigurationError`. Robinhood cannot safely simulate trades.

3. **Execution Guarding**:
   If a `place_order` proposal requests `TradeExpression.CALL_OPTION`, the adapter must immediately raise an `UnsupportedCapabilityError` without hitting the broker network.

---

### R5.3.2 Credentials & Authentication

Authentication relies on user credentials rather than standard API keys.

1. **Environment Variables**:
   * `ROBINHOOD_USERNAME`
   * `ROBINHOOD_PASSWORD`
   * `ROBINHOOD_TOTP` (Optional, for accounts with Two-Factor Authentication enabled)

2. **Login Encapsulation**:
   The adapter will use `robin_stocks.robinhood.login()`.
   If credentials are missing, or if the login attempt fails (e.g., due to an invalid TOTP token or changed password), the adapter must raise a `BrokerAuthenticationError`.

---

### R5.3.3 SDK Encapsulation & Model Mapping

All requests and responses must be translated into the standardized Pydantic models from `prescient.broker.models`.

#### 1. Account Snapshot Mapping
Query `robin_stocks.robinhood.profiles.build_user_profile()` and map:
- `cash` -> `AccountRiskSnapshot.cash`
- `buying_power` -> `AccountRiskSnapshot.buying_power`
- `equity` -> `AccountRiskSnapshot.equity`

#### 2. Position Filtering and Mapping
Query `robin_stocks.robinhood.account.build_holdings()`.
* **Filtering**: The adapter must **silently discard** any Crypto or Options positions returned by Robinhood. Only standard equity positions should be processed.
* **Mapping**:
  - `symbol` -> `BrokerPosition.symbol`
  - `TradeExpression.STOCK` -> `BrokerPosition.expression`
  - `quantity` -> `BrokerPosition.qty`
  - `price` -> `BrokerPosition.market_value`
  - `average_buy_price` -> `BrokerPosition.average_entry_price`

#### 3. Order Placement (`place_order`)
Submit the order using `robin_stocks.robinhood.orders.order_buy_limit()` or `order_sell_limit()`.
* Map the returned Robinhood receipt dictionary to `OrderExecutionResult`:
  - `id` -> `OrderExecutionResult.order_id`
  - `state` -> Map Robinhood state (`filled`, `unconfirmed`, `queued`) to `BrokerOrderStatus`.
  - `cumulative_quantity` -> `OrderExecutionResult.filled_qty`
  - `average_price` -> `OrderExecutionResult.avg_fill_price`

---

### R5.3.4 Standardized Exception Handling

API calls must be wrapped in `try-except` blocks. Because `robin_stocks` often surfaces raw `requests.exceptions.HTTPError` or generic exceptions, the adapter must catch and standardize them:

| Robinhood Error Context | Unified Exception |
| :--- | :--- |
| Login fails / HTTP 401 / Invalid TOTP | `BrokerAuthenticationError` |
| HTTP 429 Too Many Requests | `BrokerRateLimitError` |
| Order rejected / Insufficient buying power | `BrokerExecutionError` |
| `requests.exceptions.ConnectionError`, timeouts | `BrokerConnectionError` |
| Attempting an options trade | `UnsupportedCapabilityError` |

---

## Acceptance Criteria

1. **Protocol Compliance**: `RobinhoodAdapter` fully implements the `BrokerAdapter` Protocol.
2. **Paper Mode Prevention**: Instantiating `RobinhoodAdapter` with `ExecutionMode.PAPER` raises a `ConfigurationError`.
3. **Options Prevention**: Submitting a `TradeExpression.CALL_OPTION` proposal raises an `UnsupportedCapabilityError`.
4. **Position Filtering**: If a Robinhood account holds Dogecoin (Crypto) and AAPL (Stock), `get_positions()` returns only the AAPL position mapped to a `BrokerPosition`.
5. **Unified Error Catching**: Mocked `robin_stocks` login failures successfully bubble up as a `BrokerAuthenticationError`.

---

## Non-Goals

* **Options Implementation**: Robinhood does support options, but parsing the complex option chain and order structures via `robin_stocks` is explicitly out of scope for MVP.
* **Crypto Integration**: Prescient does not trade Crypto; crypto holdings are ignored.
* **Session Persistence**: Managing a long-lived Robinhood session token file to avoid repeated logins is not required for the MVP, though it may be added as an internal optimization later.

---

## Open Questions

> [!IMPORTANT]
> The following details should be aligned upon before finalize code construction:

1. **Dependency Addition**: `robin_stocks` is not currently listed in `pyproject.toml`. We assume it will be added when this feature is implemented.
2. **MFA Workflows**: If an account requires an SMS code rather than a TOTP app, automated login will block. We assume `ROBINHOOD_TOTP` using an authenticator app secret is the only supported MFA flow for headless execution.
