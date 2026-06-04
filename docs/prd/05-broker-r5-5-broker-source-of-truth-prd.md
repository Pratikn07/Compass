# PRD: R5.5 Broker as the Single Source of Account State

## Ownership

Owner: Ours

Source note: Requirement from Ours: the broker must be the absolute single source of truth for the real account state (buying power, positions, orders, and fills) used by the risk gatekeeper and position sizer. The core system must never rely on local cached state, databases, or simulated account states for execution decisions.

---

## Objective

Define the architecture, integration flow, and validation rules to ensure the risk gatekeeper (`prescient.risk`) and position sizer evaluate risk using real-time data fetched directly from the broker adapter (`BrokerAdapter`).

R5.5 answers:
```text
How does the risk gatekeeper enforce trade sizing, concentration limits, and daily halts using real-time broker states without violating import boundaries or introducing local state divergence?
```

---

## Background

To execute trades safely, the risk gatekeeper needs access to:
1. **Account Equity & Buying Power**: For maximum-loss sizing (R3.2) and cash checks.
2. **Current Positions**: To enforce concentration caps (R3.5) and prevent averaging down (R3.6).
3. **Open Orders & Fills**: To verify daily trade count stops and daily realized-loss halts (R3.4).

Currently, these checks accept structured inputs (e.g., `AccountRiskSnapshot`), but there is no explicit system policy requiring that these inputs come *directly and fresh* from the broker. Relying on local cached databases or simulation files introduces the risk of state drift (e.g., manual orders placed on the broker UI, or undetected order fills/rejections), which could lead to overallocating capital, violating risk caps, or failing to halt trading.

---

## Architectural Principles & Decoupling

The system must satisfy two competing constraints:
1. **Source of Truth**: The broker adapter is the sole source of account state.
2. **Deterministic & Isolated Risk Boundary**: The `prescient.risk` package must remain pure-code and is strictly forbidden from importing the `prescient.broker` package, reading environment variables, or executing network IO directly.

To solve this, the orchestrator/runtime pipeline (`prescient.runtime`) is responsible for querying the broker adapter before calling the risk gatekeeper and injecting the fresh broker state as parameters.

```text
               +---------------------------+
               |  Runtime Orchestrator     |
               +-------------+-------------+
                             |
         1. Query Fresh State| 2. Inject States
                             v
  +--------------------------+--------------------------+
  |                                                     |
  v                                                     v
+------------------+                                  +-------------------+
|  Broker Adapter  |                                  |  Risk Gatekeeper  |
|  (get_account,   |                                  |  (evaluate_risk,  |
|   get_positions, |                                  |   evaluate_halt)  |
|   get_orders)    |                                  +-------------------+
+------------------+
```

---

## Functional Requirements

### R5.5.1 The Single Source of Truth Principle
* No risk evaluation or order sizing check may utilize a local database, disk cache, or simulated account tracker to resolve buying power, cash, open positions, active orders, or fills.
* Every preflight run must fetch fresh data from the configured `BrokerAdapter` via the pipeline orchestrator.

### R5.5.2 Account Snapshot Integration (Buying Power & Cash)
* The orchestrator must call `get_account_snapshot()` on the active `BrokerAdapter` to obtain the current `AccountRiskSnapshot`.
* The gatekeeper must reject or block the trade with `RiskRejectionReason.ACCOUNT_EQUITY_MISSING` if the snapshot is missing, or if cash/buying power fails to cover the estimated order entry cost.
* The position sizer must calculate maximum-loss sizes based strictly on the `equity` field returned by the broker.

### R5.5.3 Position Limits & Concentration Integration
* The orchestrator must call `get_positions()` on the `BrokerAdapter` before passing the position list to the gatekeeper's concentration checks.
* The risk gatekeeper must count active positions and aggregate exposure solely from the list of `BrokerPosition` items returned by the broker.
* **No Averaging Down Gate**: If a `BrokerPosition` exists for the target ticker, the gatekeeper must reject any order proposal that increases the position's average entry cost or size if it violates the "no averaging down" policy (R3.6).

### R5.5.4 Active Orders & Fills Integration (Daily halts)
* The orchestrator must call `get_orders(status=OrderStatusFilter.ALL)` on the `BrokerAdapter` to retrieve recent fills and pending orders.
* **Realized Loss / Trade Count Calculation**: The gatekeeper's daily halt checker (`evaluate_daily_halt`) must compute the current day's realized PnL and losing trade count using the broker-reported order history and fill details.
* **Pending Exposure Checks**: Any active open order returned by the broker must be factored into the buying power and concentration headroom checks as pending exposure, preventing double-allocation of cash.

### R5.5.5 Failure Isolation & Fail-Closed Behavior
* If any broker call (account, positions, or orders) fails or throws a `BrokerError` (e.g. timeout, rate limit, API offline), the orchestrator must fail closed.
* The pipeline must not fall back to stale cached records or simulated states. The risk gatekeeper decision must return `RiskGateStatus.NOT_EVALUABLE` with reason `missing_account_snapshot` or similar, blocking all execution.

---

## Verification Plan

### Automated Tests
1. **Broker Boundary Verification**:
   * Enforce boundary checks proving `prescient.risk` does not import `prescient.broker` or call network methods.
2. **State Injection Verification**:
   * Test pipelines using `MockBrokerAdapter` configured with different states (e.g., zero buying power, maximum position limits reached, high daily realized loss) to verify that `evaluate_risk_gate` and sizers block/halt trades correctly based solely on the mock adapter's output.
3. **Downtime Rejections**:
   * Verify that when the broker adapter raises a `BrokerConnectionError` or returns empty fields, the pipeline halts immediately and rejects the strategy candidate.

### Manual Verification
* Deploy the scheduled pipeline in a staging environment connected to Alpaca Paper Trading.
* Manually place an order on the Alpaca web dashboard. Run the Prescient pipeline and verify that the risk gate immediately detects the new position and adjusts concentration limits accordingly without relying on a local database.

---

## Non-Goals

* This PRD does not define order routing optimization or execution logic (which are handled in R5.1/R5.2).
* No persistent database caching of broker states is planned.
