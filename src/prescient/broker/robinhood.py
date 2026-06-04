from __future__ import annotations

import os
from typing import Sequence

import requests
import robin_stocks.robinhood as r  # type: ignore[import-untyped]

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
    ConfigurationError,
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


class RobinhoodAdapter:
    """Concrete implementation of BrokerAdapter Protocol using the robin_stocks SDK."""

    def __init__(
        self,
        execution_mode: ExecutionMode | str,
        username: str | None = None,
        password: str | None = None,
        totp: str | None = None,
    ) -> None:
        if isinstance(execution_mode, str):
            execution_mode = ExecutionMode(execution_mode)

        if execution_mode == ExecutionMode.PAPER:
            raise ConfigurationError(
                "Robinhood does not support paper trading. Use Alpaca for paper mode."
            )

        self.execution_mode = execution_mode

        # Resolve credentials
        self.username = username or os.environ.get("ROBINHOOD_USERNAME")
        self.password = password or os.environ.get("ROBINHOOD_PASSWORD")
        self.totp = totp or os.environ.get("ROBINHOOD_TOTP")

        if not self.username or not self.password:
            raise BrokerAuthenticationError(
                "Robinhood credentials missing. Set ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD."
            )

        try:
            r.login(
                username=self.username,
                password=self.password,
                mfa_code=self.totp,
                store_session=False,
            )
        except Exception as e:
            self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> None:
        """Helper to translate robin_stocks / requests exceptions to standardized BrokerError."""
        if isinstance(e, requests.exceptions.HTTPError):
            status_code = e.response.status_code if e.response is not None else None
            msg = str(e)
            if status_code in {401, 403}:
                raise BrokerAuthenticationError(f"Robinhood authentication failed: {msg}") from e
            elif status_code == 429:
                raise BrokerRateLimitError(f"Robinhood rate limit exceeded: {msg}") from e
            elif status_code in {400, 422}:
                raise BrokerExecutionError(f"Robinhood order execution rejected: {msg}") from e
            else:
                raise BrokerError(f"Robinhood API error (status {status_code}): {msg}") from e

        if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            raise BrokerConnectionError(f"Robinhood broker connection failure: {str(e)}") from e

        raise BrokerError(f"Robinhood operation failed: {str(e)}") from e

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        try:
            profile = r.profiles.load_account_profile()
            return AccountRiskSnapshot(
                equity=float(profile.get("equity") or profile.get("portfolio_value", 0)),
                cash=float(profile.get("cash", 0)),
                buying_power=float(profile.get("buying_power") or profile.get("portfolio_cash", 0)),
            )
        except Exception as e:
            self._handle_exception(e)
            raise  # Keep compiler/type checkers happy

    @staticmethod
    def _is_option_symbol(symbol: str) -> bool:
        """Return True if *symbol* looks like an OCC option symbol.

        OCC symbols are typically >10 characters and contain digits mixed
        with letters in a specific pattern (e.g. ``AAPL  250620C00200000``).
        """
        if len(symbol) > 10:
            return True
        has_alpha = any(c.isalpha() for c in symbol)
        has_digit = any(c.isdigit() for c in symbol)
        return has_alpha and has_digit and len(symbol) > 5

    def get_positions(self) -> Sequence[BrokerPosition]:
        try:
            holdings = r.account.build_holdings()
            broker_positions = []
            for ticker, data in holdings.items():
                # Skip cryptocurrency positions
                if data.get("type", "").lower() == "cryptocurrency":
                    continue

                # Skip OCC option symbols
                if self._is_option_symbol(ticker):
                    continue

                broker_positions.append(
                    BrokerPosition(
                        symbol=ticker,
                        expression=TradeExpression.STOCK,
                        qty=float(data["quantity"]),
                        market_value=float(data["equity"]),
                        average_entry_price=float(data["average_buy_price"]),
                    )
                )
            return broker_positions
        except Exception as e:
            self._handle_exception(e)
            raise

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        # Check option capability
        if proposal.expression in {"CALL_OPTION", "PUT_OPTION"}:
            raise UnsupportedCapabilityError("Robinhood adapter does not support options trading.")

        # Strip/normalize symbol
        symbol = proposal.target.strip().upper()

        try:
            result = r.orders.order_buy_limit(
                symbol=symbol,
                quantity=1,
                limitPrice=proposal.estimated_entry_cost,
                timeInForce="gfd",
            )

            # Map status
            state = (result.get("state") or "").lower()
            status_map = {
                "filled": BrokerOrderStatus.FILLED,
                "cancelled": BrokerOrderStatus.CANCELLED,
                "canceled": BrokerOrderStatus.CANCELLED,
                "rejected": BrokerOrderStatus.REJECTED,
            }
            mapped_status = status_map.get(state, BrokerOrderStatus.OPEN)

            filled_qty = int(float(result.get("cumulative_quantity", 0)))
            avg_price_raw = result.get("average_price")
            avg_price = float(avg_price_raw) if avg_price_raw else None

            return OrderExecutionResult(
                order_id=result["id"],
                status=mapped_status,
                filled_qty=filled_qty,
                avg_fill_price=avg_price,
                message=f"Order submitted to Robinhood successfully. Status: {state}.",
            )
        except UnsupportedCapabilityError:
            raise
        except Exception as e:
            self._handle_exception(e)
            raise

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        try:
            raw_orders = r.orders.get_all_stock_orders()
            broker_orders = []
            for order in raw_orders:
                state = (order.get("state") or "").lower()

                # Filter by status if specified
                if status == OrderStatusFilter.OPEN and state not in {"queued", "confirmed"}:
                    continue
                if status == OrderStatusFilter.CLOSED and state not in {
                    "filled",
                    "cancelled",
                    "canceled",
                    "rejected",
                    "failed",
                }:
                    continue

                status_map = {
                    "filled": BrokerOrderStatus.FILLED,
                    "cancelled": BrokerOrderStatus.CANCELLED,
                    "canceled": BrokerOrderStatus.CANCELLED,
                    "rejected": BrokerOrderStatus.REJECTED,
                }
                mapped_status = status_map.get(state, BrokerOrderStatus.OPEN)

                qty = int(float(order.get("quantity", 0)))
                filled_qty = int(float(order.get("cumulative_quantity", 0)))
                limit_price_raw = order.get("price")
                limit_price = float(limit_price_raw) if limit_price_raw else None

                side_str = (order.get("side") or "buy").lower()
                broker_orders.append(
                    BrokerOrder(
                        order_id=order["id"],
                        symbol=order.get("symbol", order.get("instrument", "")),
                        qty=qty,
                        filled_qty=filled_qty,
                        limit_price=limit_price,
                        status=mapped_status,
                        submitted_at=order.get("created_at"),
                        side=side_str,
                    )
                )
            return broker_orders
        except Exception as e:
            self._handle_exception(e)
            raise

    def cancel_order(self, order_id: str) -> None:
        try:
            r.orders.cancel_stock_order(order_id)
        except Exception as e:
            self._handle_exception(e)

    def get_capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_options=False,
            supports_paper_trading=False,
            broker_name="robinhood",
        )


# Automatically register the Robinhood adapter
register_broker("robinhood", RobinhoodAdapter)
