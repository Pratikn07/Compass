from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from prescient.broker import register_broker
from prescient.broker.models import (
    BrokerCapabilities,
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
    OrderExecutionResult,
    OrderStatusFilter,
    UnsupportedCapabilityError,
    BrokerExecutionError,
)
from prescient.risk.models import (
    AccountRiskSnapshot,
    RiskOrderProposal,
    TradeExpression,
)


class MockBrokerAdapter:
    """Mock implementation of the BrokerAdapter protocol for testing and local proposes."""

    def __init__(
        self,
        execution_mode: str = "paper",
        supports_options: bool = True,
        supports_paper_trading: bool = True,
        broker_name: str = "mock",
        account_equity: float = 25000.0,
        account_cash: float = 25000.0,
        account_buying_power: float = 25000.0,
        positions: list[BrokerPosition] | None = None,
        orders: list[BrokerOrder] | None = None,
        slippage_buffer_pct: float = 0.01,
    ) -> None:
        self.execution_mode = execution_mode
        self.supports_options = supports_options
        self.supports_paper_trading = supports_paper_trading
        self.broker_name = broker_name
        self.account_equity = account_equity
        self.account_cash = account_cash
        self.account_buying_power = account_buying_power
        self.positions_list = list(positions) if positions is not None else []
        self.orders_list = list(orders) if orders is not None else []
        self.slippage_buffer_pct = slippage_buffer_pct

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        return AccountRiskSnapshot(
            equity=self.account_equity,
            cash=self.account_cash,
            buying_power=self.account_buying_power,
        )

    def get_positions(self) -> Sequence[BrokerPosition]:
        return list(self.positions_list)

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        # Defense-in-depth: block orders if mode is propose_only
        if self.execution_mode == "propose_only":
            raise BrokerExecutionError(
                "Cannot place orders in propose-only mode. "
                "This adapter was initialized with execution_mode='propose_only'."
            )

        # Preflight buying power check (defense-in-depth)
        total_required_funds = proposal.estimated_entry_cost * (1.0 + self.slippage_buffer_pct)
        if total_required_funds > self.account_buying_power:
            raise BrokerExecutionError(
                f"Insufficient buying power: required {total_required_funds:.2f} "
                f"(including {self.slippage_buffer_pct * 100:.1f}% buffer), "
                f"but only {self.account_buying_power:.2f} available."
            )

        # Capabilities Check
        if proposal.expression in {"CALL_OPTION", "PUT_OPTION"} and not self.supports_options:
            raise UnsupportedCapabilityError(
                f"Broker '{self.broker_name}' does not support options trading."
            )

        order_id = str(uuid.uuid4())
        expr = TradeExpression(proposal.expression)

        # Deduct cost from cash and buying power
        self.account_cash -= proposal.estimated_entry_cost
        self.account_buying_power -= proposal.estimated_entry_cost

        # Create simulated position
        position = BrokerPosition(
            symbol=proposal.target,
            expression=expr,
            qty=1.0,
            market_value=proposal.estimated_entry_cost,
            average_entry_price=proposal.estimated_entry_cost,
        )
        self.positions_list.append(position)

        # Create simulated order
        order = BrokerOrder(
            order_id=order_id,
            symbol=proposal.target,
            qty=1,
            filled_qty=1,
            limit_price=proposal.estimated_entry_cost,
            status=BrokerOrderStatus.FILLED,
            submitted_at=datetime.now(timezone.utc),
        )
        self.orders_list.append(order)

        return OrderExecutionResult(
            order_id=order_id,
            status=BrokerOrderStatus.FILLED,
            filled_qty=1,
            avg_fill_price=proposal.estimated_entry_cost,
            message="Order executed successfully via mock adapter.",
        )

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        if status is None or status == OrderStatusFilter.ALL:
            return list(self.orders_list)
        if status == OrderStatusFilter.OPEN:
            return [o for o in self.orders_list if o.status == BrokerOrderStatus.OPEN]
        if status == OrderStatusFilter.CLOSED:
            return [
                o
                for o in self.orders_list
                if o.status in {BrokerOrderStatus.FILLED, BrokerOrderStatus.CANCELLED, BrokerOrderStatus.REJECTED}
            ]
        return []

    def cancel_order(self, order_id: str) -> None:
        for order in self.orders_list:
            if order.order_id == order_id:
                if order.status == BrokerOrderStatus.OPEN:
                    # Update status in the mock database
                    idx = self.orders_list.index(order)
                    self.orders_list[idx] = BrokerOrder(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        qty=order.qty,
                        filled_qty=order.filled_qty,
                        limit_price=order.limit_price,
                        status=BrokerOrderStatus.CANCELLED,
                        submitted_at=order.submitted_at,
                        side=order.side,
                    )
                    return
                else:
                    raise BrokerExecutionError(f"Cannot cancel order {order_id} in status {order.status}.")
        raise BrokerExecutionError(f"Order {order_id} not found.")

    def get_capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_options=self.supports_options,
            supports_paper_trading=self.supports_paper_trading,
            broker_name=self.broker_name,
        )


# Automatically register the mock adapter
register_broker("mock", MockBrokerAdapter)
