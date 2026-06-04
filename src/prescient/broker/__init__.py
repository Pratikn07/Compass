from __future__ import annotations

from typing import Any

from prescient.broker.execution_guard import (
    KillSwitchBrokerWrapper,
    ProposeOnlyBrokerWrapper,
    PreflightCheckBrokerWrapper,
    print_execution_mode_banner,
)
from prescient.broker.interfaces import BrokerAdapter
from prescient.broker.models import (
    BrokerCapabilities,
    BrokerOrder,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerSettings,
    BrokerError,
    ConfigurationError,
    BrokerConnectionError,
    BrokerAuthenticationError,
    BrokerRateLimitError,
    BrokerExecutionError,
    UnsupportedCapabilityError,
    OrderExecutionResult,
    OrderStatusFilter,
)
from prescient.risk.models import ExecutionMode

_REGISTRY: dict[str, type[BrokerAdapter]] = {}


def register_broker(name: str, adapter_cls: type[BrokerAdapter]) -> None:
    """Register a broker adapter class under a string identifier."""
    _REGISTRY[name.strip().lower()] = adapter_cls


def get_broker_adapter(
    broker_name: str,
    execution_mode: ExecutionMode | str,
    **kwargs: Any,
) -> BrokerAdapter:
    """Resolve and instantiate a configured broker adapter.

    Args:
        broker_name: The registered name of the broker (e.g. 'alpaca', 'mock').
        execution_mode: Execution mode (paper, live, propose_only).
        **kwargs: Additional parameters passed to the concrete adapter class.

    Returns:
        BrokerAdapter: Resolved and instantiated adapter class.

    Raises:
        ValueError: If the broker_name is not registered.
        ConfigurationError: If execution mode is unsupported by the broker capabilities.
    """
    normalized_name = broker_name.strip().lower()
    if normalized_name not in _REGISTRY:
        raise ValueError(
            f"Unrecognized broker_name '{broker_name}'. Available brokers: {list(_REGISTRY.keys())}"
        )

    if isinstance(execution_mode, str):
        try:
            execution_mode = ExecutionMode(execution_mode)
        except ValueError:
            raise ValueError(f"Invalid execution mode '{execution_mode}'.")

    slippage_buffer_pct = kwargs.pop("slippage_buffer_pct", 0.01)
    kill_switch_provider = kwargs.pop("kill_switch_provider", None)

    cls = _REGISTRY[normalized_name]
    if normalized_name == "mock":
        adapter = cls(execution_mode=execution_mode, slippage_buffer_pct=slippage_buffer_pct, **kwargs)
    else:
        adapter = cls(execution_mode=execution_mode, **kwargs)

    capabilities = adapter.get_capabilities()
    if execution_mode == ExecutionMode.PAPER and not capabilities.supports_paper_trading:
        raise ConfigurationError(
            f"Broker '{capabilities.broker_name}' does not support paper trading."
        )

    print_execution_mode_banner(execution_mode)

    if execution_mode == ExecutionMode.PROPOSE_ONLY:
        guarded_adapter = ProposeOnlyBrokerWrapper(
            adapter,
            slippage_buffer_pct=slippage_buffer_pct,
        )
        return KillSwitchBrokerWrapper(guarded_adapter, provider=kill_switch_provider)

    guarded_adapter = PreflightCheckBrokerWrapper(adapter, slippage_buffer_pct=slippage_buffer_pct)
    return KillSwitchBrokerWrapper(guarded_adapter, provider=kill_switch_provider)


# Expose public API
__all__ = [
    "BrokerAdapter",
    "BrokerCapabilities",
    "BrokerOrder",
    "BrokerOrderStatus",
    "BrokerPosition",
    "BrokerSettings",
    "BrokerError",
    "ConfigurationError",
    "BrokerConnectionError",
    "BrokerAuthenticationError",
    "BrokerRateLimitError",
    "BrokerExecutionError",
    "UnsupportedCapabilityError",
    "OrderExecutionResult",
    "OrderStatusFilter",
    "KillSwitchBrokerWrapper",
    "ProposeOnlyBrokerWrapper",
    "PreflightCheckBrokerWrapper",
    "print_execution_mode_banner",
    "get_broker_adapter",
    "register_broker",
]

# Auto-register concrete adapters on package import
import prescient.broker.mock  # noqa: E402,F401
import prescient.broker.alpaca  # noqa: E402,F401
import prescient.broker.robinhood  # noqa: E402,F401
