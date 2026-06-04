# PRD: R5.6 Preflight Check on Buying Power Before Any Order

## Ownership

Owner: Ours

Source note: The execution layer must perform a real-time preflight check on available cash or buying power immediately before submitting any order to the broker. This prevents API rejections, account lockouts, or margin violations caused by price movements, execution lag, or capital overallocation.

---

## Objective

Define the design, integration flow, and validation rules for the preflight buying power verification executed at the broker adapter layer (`BrokerAdapter`) before any order transmission.

R5.6 answers:
```text
How does the system prevent placing orders that exceed the available account resources, accounting for real-time market movements, order costs, and slippage buffers, prior to hitting the broker's API?
```

---

## Background

When the risk gatekeeper evaluates a strategy candidate, it uses an `AccountRiskSnapshot` to verify capital limits and size the trade (R3.2/R3.8). However:
1. **Execution Lag**: There is a non-zero time difference between the risk evaluation step and the actual order submission. Available buying power can fluctuate due to other filled orders, mark-to-market changes on open positions, or manual account changes.
2. **Slippage & Bid-Ask Spreads**: The actual entry price may be slightly higher than the estimated cost calculated during signal generation, especially in fast-moving markets.
3. **Broker Restraints**: Submitting an order that exceeds available resources can result in broker-side rejection, API rate limits, or margin call triggers.

Performing an immediate, real-time preflight query and validation at the broker adapter layer prevents these issues by catching over-limit orders *before* they are sent to the exchange.

---

## Technical Architecture & Requirements

### R5.6.1 Configurable Slippage Buffer
* The check must include a configurable safety margin (slippage buffer) to account for price execution drift.
* The buffer is defined by `slippage_buffer_pct` inside `BrokerSettings` (defaults to `0.01` or 1%).
* The total required funds for the order is calculated as:
  $$\text{Total Required Funds} = \text{estimated\_entry\_cost} \times (1.0 + \text{slippage\_buffer\_pct})$$

### R5.6.2 Preflight Validation Rule
* Prior to transmitting an order inside `place_order()`, the adapter must:
  1. Call `get_account_snapshot()` to fetch the most up-to-date account status.
  2. Read the `buying_power` (or `cash` if `buying_power` is not populated or applicable) from the snapshot.
  3. Validate that:
     $$\text{Available Buying Power} \ge \text{Total Required Funds}$$
* If validation fails, the adapter must halt execution and throw a `BrokerExecutionError` without sending any order to the network.

### R5.6.3 Integration Across Execution Modes
* **LIVE and PAPER modes**: The adapter queries the actual live/paper endpoints for account balance and enforces the rule strictly.
* **PROPOSE_ONLY mode**: 
  - In `PROPOSE_ONLY` mode, the `ProposeOnlyBrokerWrapper` intercepts the `place_order` call.
  - To ensure dry-runs accurately simulate actual feasibility, the wrapper itself can optionally call `get_account_snapshot()` and run the preflight verification. If buying power is insufficient, the wrapper should return an `OrderExecutionResult` with `status=BrokerOrderStatus.REJECTED` and a clear message: `"Order would be rejected: Insufficient buying power."`

---

## Functional Requirements

### R5.6.4 Preflight Query Recency
* The preflight query `get_account_snapshot()` must be performed *immediately* inside the `place_order()` execution path. Using cached snapshots older than 5 seconds is prohibited.

### R5.6.5 Standardized Error Message
* If the preflight check fails, the raised `BrokerExecutionError` must follow a standard structure:
  ```text
  Insufficient buying power: required {total_required_funds} (including {slippage_buffer_pct}% buffer), but only {available_buying_power} available.
  ```

---

## Verification Plan

### Automated Tests
1. **Preflight Failure Test**:
   - Configure a mock broker adapter with $\$10,000$ buying power.
   - Propose an order with `estimated_entry_cost = $10,000` and `slippage_buffer_pct = 0.01` (required funds = $\$10,100$).
   - Verify that `place_order()` raises `BrokerExecutionError` containing the correct failure text.
2. **Preflight Success Test**:
   - Propose an order with `estimated_entry_cost = $9,000` (required funds = $\$9,090$).
   - Verify that the order is successfully placed and the buying power is deducted.
3. **Propose-Only Virtual Rejection Test**:
   - In `propose_only` mode, verify that proposing an order exceeding the current live buying power results in a virtual rejection.

### Manual Verification
* Run the pipeline against a paper broker account with low buying power and verify that order requests are safely blocked on-client with descriptive logging before API requests escape.

---

## Non-Goals

* Performing margin requirement calculations for complex multi-leg option spreads. The check relies solely on the provided `estimated_entry_cost` in the proposal.
* Synchronizing buying power across multiple distinct broker adapters simultaneously.
