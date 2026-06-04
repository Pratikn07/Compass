from __future__ import annotations

import os
from typing import Sequence

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from prescient.broker import register_broker
from prescient.broker.models import (
    BrokerAuthenticationError,
    BrokerCapabilities,
    BrokerConnectionError,
    BrokerError,
    BrokerExecutionError,
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerRateLimitError,
    OrderExecutionResult,
    OrderStatusFilter,
    UnsupportedCapabilityError,
)
from prescient.risk.models import (
    AccountRiskSnapshot,
    ExecutionMode,
    RiskOrderProposal,
    TradeExpression,
)


class AlpacaAdapter:
    """Concrete implementation of BrokerAdapter Protocol using the alpaca-py SDK."""

    def __init__(
        self,
        execution_mode: ExecutionMode | str,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        if isinstance(execution_mode, str):
            execution_mode = ExecutionMode(execution_mode)
        self.execution_mode = execution_mode
        self.paper = (execution_mode == ExecutionMode.PAPER)

        # Resolve credentials
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY_ID")
        self.api_secret = api_secret or os.environ.get("ALPACA_API_SECRET_KEY")

        if not self.api_key or not self.api_secret:
            raise BrokerAuthenticationError("Alpaca API credentials missing.")

        try:
            self.client = TradingClient(
                api_key=self.api_key,
                secret_key=self.api_secret,
                paper=self.paper,
            )
        except Exception as e:
            self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> None:
        """Helper to translate Alpaca SDK exceptions to standardized BrokerError."""
        if isinstance(e, APIError):
            status_code = e.status_code
            msg = str(e)
            if status_code in {401, 403}:
                raise BrokerAuthenticationError(f"Alpaca authentication failed: {msg}") from e
            elif status_code == 429:
                raise BrokerRateLimitError(f"Alpaca rate limit exceeded: {msg}") from e
            elif status_code in {400, 422, 404}:
                raise BrokerExecutionError(f"Alpaca order execution rejected: {msg}") from e
            else:
                raise BrokerError(f"Alpaca API error (status {status_code}): {msg}") from e

        # Handle network or connection issues
        err_msg = str(e).lower()
        if any(term in err_msg for term in ("connection", "timeout", "dns", "unreachable", "host")):
            raise BrokerConnectionError(f"Alpaca broker connection failure: {str(e)}") from e

        raise BrokerError(f"Alpaca operation failed: {str(e)}") from e

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        try:
            account = self.client.get_account()
            return AccountRiskSnapshot(
                equity=float(account.equity),
                cash=float(account.cash),
                buying_power=float(account.buying_power),
            )
        except Exception as e:
            self._handle_exception(e)
            raise  # Keep compiler/type checkers happy

    def get_positions(self) -> Sequence[BrokerPosition]:
        try:
            positions = self.client.get_all_positions()
            broker_positions = []
            for pos in positions:
                # Map asset class
                asset_class = pos.asset_class.value if hasattr(pos.asset_class, "value") else str(pos.asset_class)
                expr = (
                    TradeExpression.CALL_OPTION
                    if "option" in asset_class.lower()
                    else TradeExpression.STOCK
                )
                broker_positions.append(
                    BrokerPosition(
                        symbol=pos.symbol,
                        expression=expr,
                        qty=float(pos.qty),
                        market_value=float(pos.market_value),
                        average_entry_price=float(pos.avg_entry_price),
                    )
                )
            return broker_positions
        except Exception as e:
            self._handle_exception(e)
            raise

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        # Check option capability
        is_option = proposal.expression in {"CALL_OPTION", "PUT_OPTION"}
        if is_option and not self.get_capabilities().supports_options:
            raise UnsupportedCapabilityError("Alpaca options capability disabled.")

        # Strip/normalize symbol
        symbol = proposal.target.strip().upper()

        try:
            order_req = MarketOrderRequest(
                symbol=symbol,
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(order_req)

            # Map status
            status_str = order.status.value if hasattr(order.status, "value") else str(order.status)
            status_map = {
                "filled": BrokerOrderStatus.FILLED,
                "canceled": BrokerOrderStatus.CANCELLED,
                "rejected": BrokerOrderStatus.REJECTED,
            }
            mapped_status = status_map.get(status_str.lower(), BrokerOrderStatus.OPEN)

            filled_qty = int(float(order.filled_qty)) if order.filled_qty else 0
            avg_price = float(order.filled_avg_price) if order.filled_avg_price else None

            return OrderExecutionResult(
                order_id=str(order.id),
                status=mapped_status,
                filled_qty=filled_qty,
                avg_fill_price=avg_price,
                message=f"Order submitted to Alpaca successfully. Status: {status_str}.",
            )
        except Exception as e:
            self._handle_exception(e)
            raise

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        try:
            alpaca_status = QueryOrderStatus.OPEN
            if status == OrderStatusFilter.CLOSED:
                alpaca_status = QueryOrderStatus.CLOSED
            elif status == OrderStatusFilter.ALL:
                alpaca_status = QueryOrderStatus.ALL

            req = GetOrdersRequest(status=alpaca_status)
            orders = self.client.get_orders(req)
            broker_orders = []
            for order in orders:
                status_str = order.status.value if hasattr(order.status, "value") else str(order.status)
                status_map = {
                    "filled": BrokerOrderStatus.FILLED,
                    "canceled": BrokerOrderStatus.CANCELLED,
                    "rejected": BrokerOrderStatus.REJECTED,
                }
                mapped_status = status_map.get(status_str.lower(), BrokerOrderStatus.OPEN)

                qty = int(float(order.qty)) if order.qty else 0
                filled_qty = int(float(order.filled_qty)) if order.filled_qty else 0
                limit_price = float(order.limit_price) if order.limit_price else None

                side_str = order.side.value if hasattr(order.side, "value") else str(order.side)
                broker_orders.append(
                    BrokerOrder(
                        order_id=str(order.id),
                        symbol=order.symbol,
                        qty=qty,
                        filled_qty=filled_qty,
                        limit_price=limit_price,
                        status=mapped_status,
                        submitted_at=order.submitted_at,
                        side=side_str.lower(),
                    )
                )
            return broker_orders
        except Exception as e:
            self._handle_exception(e)
            raise

    def cancel_order(self, order_id: str) -> None:
        try:
            self.client.cancel_order_by_id(order_id)
        except Exception as e:
            self._handle_exception(e)

    def get_capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_options=True,
            supports_paper_trading=True,
            broker_name="alpaca",
        )


# Automatically register the Alpaca adapter
register_broker("alpaca", AlpacaAdapter)
