from __future__ import annotations

from typing import Protocol, Sequence

from prescient.broker.models import (
    BrokerCapabilities,
    BrokerOrder,
    BrokerPosition,
    OrderExecutionResult,
    OrderStatusFilter,
)
from prescient.risk.models import AccountRiskSnapshot, RiskOrderProposal


class BrokerAdapter(Protocol):
    """Protocol defining structural typing interface for swappable broker adapters."""

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        """Fetch real-time account equity, cash, and buying power from the broker API.

        Returns:
            AccountRiskSnapshot: Unified Pydantic model with float values.

        Raises:
            BrokerError: Base broker operation error or platform-specific equivalent.
        """
        ...

    def get_positions(self) -> Sequence[BrokerPosition]:
        """Fetch all open equity and option positions currently held in the account.

        Returns:
            Sequence[BrokerPosition]: List of unified position objects.

        Raises:
            BrokerError: Base broker operation error or platform-specific equivalent.
        """
        ...

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

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        """Fetch recent orders, optionally filtered by status (open, closed, all).

        Args:
            status: Optional status filter.

        Returns:
            Sequence[BrokerOrder]: List of unified order objects.

        Raises:
            BrokerError: Base broker operation error or platform-specific equivalent.
        """
        ...

    def cancel_order(self, order_id: str) -> None:
        """Cancel an active open order by its broker-assigned unique identifier.

        Args:
            order_id: Unique broker identifier.

        Raises:
            BrokerError: Base broker operation error or platform-specific equivalent.
        """
        ...

    def get_capabilities(self) -> BrokerCapabilities:
        """Return static capabilities configuration for this broker instance.

        Returns:
            BrokerCapabilities: Configuration object describing broker features.
        """
        ...
