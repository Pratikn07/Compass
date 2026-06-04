from __future__ import annotations

import uuid
from typing import Protocol, Sequence

from rich.console import Console

from prescient.broker.models import (
    BrokerCapabilities,
    BrokerExecutionError,
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
    OrderExecutionResult,
    OrderStatusFilter,
)
from prescient.risk.models import (
    AccountRiskSnapshot,
    ExecutionMode,
    RiskOrderProposal,
)
from prescient.safety import FileKillSwitchProvider, KillSwitchState, KillSwitchStatus


_console = Console()


class ProposeOnlyBrokerWrapper:
    """Transparent wrapper that intercepts order placement while delegating all read-only operations.

    This wrapper is applied automatically by ``get_broker_adapter()`` when the
    execution mode is ``ExecutionMode.PROPOSE_ONLY``.  All read-only broker
    queries (account snapshots, positions, orders, capabilities) are delegated
    to the inner adapter unchanged.  ``place_order()`` is intercepted and
    returns a virtual result without transmitting any request over the network.
    """

    def __init__(self, inner: object, slippage_buffer_pct: float = 0.01) -> None:
        self._inner = inner
        self.slippage_buffer_pct = slippage_buffer_pct

    # -- Read-only delegations -----------------------------------------------

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        return self._inner.get_account_snapshot()  # type: ignore[union-attr]

    def get_positions(self) -> Sequence[BrokerPosition]:
        return self._inner.get_positions()  # type: ignore[union-attr]

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        return self._inner.get_orders(status)  # type: ignore[union-attr]

    def cancel_order(self, order_id: str) -> None:
        return self._inner.cancel_order(order_id)  # type: ignore[union-attr]

    def get_capabilities(self) -> BrokerCapabilities:
        return self._inner.get_capabilities()  # type: ignore[union-attr]

    # -- Order intercept -----------------------------------------------------

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        """Intercept order placement and return a virtual propose-only result.

        No network request is made.  A preflight buying power check is run to
        simulate order feasibility. If insufficient, a virtual rejection result
        is returned.
        """
        try:
            snapshot = self._inner.get_account_snapshot()  # type: ignore[union-attr]
            available_funds = snapshot.buying_power
            total_required_funds = proposal.estimated_entry_cost * (1.0 + self.slippage_buffer_pct)

            if total_required_funds > available_funds:
                return OrderExecutionResult(
                    order_id=f"propose-only-{uuid.uuid4()}",
                    status=BrokerOrderStatus.REJECTED,
                    filled_qty=0,
                    avg_fill_price=None,
                    message=(
                        f"Insufficient buying power: required {total_required_funds:.2f} "
                        f"(including {self.slippage_buffer_pct * 100:.1f}% buffer), "
                        f"but only {available_funds:.2f} available."
                    ),
                )
        except Exception as e:
            if isinstance(e, BrokerExecutionError):
                raise
            raise BrokerExecutionError(f"Preflight check failed: Unable to fetch account snapshot. Error: {e}") from e

        return OrderExecutionResult(
            order_id=f"propose-only-{uuid.uuid4()}",
            status=BrokerOrderStatus.OPEN,
            filled_qty=0,
            avg_fill_price=None,
            message=f"Order intercepted: propose-only mode active. Proposal: {proposal.target} {proposal.expression}",
        )


class PreflightCheckBrokerWrapper:
    """Transparent wrapper that performs preflight buying power verification before placing an order.

    All methods except ``place_order()`` are delegated directly to the inner adapter.
    ``place_order()`` queries the real-time account snapshot to verify that the
    available buying power/cash is sufficient to cover the estimated order cost
    plus a slippage buffer. If insufficient, a ``BrokerExecutionError`` is raised.
    """

    def __init__(self, inner: object, slippage_buffer_pct: float = 0.01) -> None:
        self._inner = inner
        self.slippage_buffer_pct = slippage_buffer_pct

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        return self._inner.get_account_snapshot()  # type: ignore[union-attr]

    def get_positions(self) -> Sequence[BrokerPosition]:
        return self._inner.get_positions()  # type: ignore[union-attr]

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        return self._inner.get_orders(status)  # type: ignore[union-attr]

    def cancel_order(self, order_id: str) -> None:
        return self._inner.cancel_order(order_id)  # type: ignore[union-attr]

    def get_capabilities(self) -> BrokerCapabilities:
        return self._inner.get_capabilities()  # type: ignore[union-attr]

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        """Query real-time buying power, verify order sufficiency, then delegate placement."""
        snapshot = self._inner.get_account_snapshot()  # type: ignore[union-attr]
        available_funds = snapshot.buying_power
        total_required_funds = proposal.estimated_entry_cost * (1.0 + self.slippage_buffer_pct)

        if total_required_funds > available_funds:
            raise BrokerExecutionError(
                f"Insufficient buying power: required {total_required_funds:.2f} "
                f"(including {self.slippage_buffer_pct * 100:.1f}% buffer), "
                f"but only {available_funds:.2f} available."
            )

        return self._inner.place_order(proposal)  # type: ignore[union-attr]


class KillSwitchProvider(Protocol):
    def read_state(self) -> KillSwitchState:
        ...


class KillSwitchBrokerWrapper:
    """Transparent wrapper that blocks order placement while the kill switch is active.

    Read-only methods and order cancellation stay delegated so operators can inspect
    state and cancel open orders during an emergency. ``place_order()`` checks the
    provider immediately before delegating and fails closed if state cannot be read.
    """

    def __init__(
        self,
        inner: object,
        provider: KillSwitchProvider | None = None,
    ) -> None:
        self._inner = inner
        self.provider = provider or FileKillSwitchProvider()

    def get_account_snapshot(self) -> AccountRiskSnapshot:
        return self._inner.get_account_snapshot()  # type: ignore[union-attr]

    def get_positions(self) -> Sequence[BrokerPosition]:
        return self._inner.get_positions()  # type: ignore[union-attr]

    def get_orders(self, status: OrderStatusFilter | None = None) -> Sequence[BrokerOrder]:
        return self._inner.get_orders(status)  # type: ignore[union-attr]

    def cancel_order(self, order_id: str) -> None:
        return self._inner.cancel_order(order_id)  # type: ignore[union-attr]

    def get_capabilities(self) -> BrokerCapabilities:
        return self._inner.get_capabilities()  # type: ignore[union-attr]

    def place_order(self, proposal: RiskOrderProposal) -> OrderExecutionResult:
        try:
            state = self.provider.read_state()
        except Exception as exc:
            raise BrokerExecutionError(
                "Kill switch state unavailable: order placement blocked."
            ) from exc

        if state.status == KillSwitchStatus.ACTIVE:
            raise BrokerExecutionError("Kill switch active: order placement blocked.")

        return self._inner.place_order(proposal)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------


def print_execution_mode_banner(mode: ExecutionMode) -> None:
    """Print a highly visible terminal banner indicating the active execution mode."""
    if mode == ExecutionMode.LIVE:
        _console.print(
            "\n[bold red on white]"
            "============================================================\n"
            "!! WARNING: LIVE REAL-MONEY TRADING MODE IS ACTIVE !!\n"
            "============================================================"
            "[/]\n"
        )
    elif mode == ExecutionMode.PAPER:
        _console.print(
            "\n[bold green]"
            "============================================================\n"
            "  PAPER TRADING MODE — virtual sandbox, no real money\n"
            "============================================================"
            "[/]\n"
        )
    else:
        _console.print(
            "\n[bold cyan]"
            "============================================================\n"
            "  PROPOSE-ONLY MODE — no orders will be placed\n"
            "============================================================"
            "[/]\n"
        )
