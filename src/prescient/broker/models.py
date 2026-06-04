from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    SourceCitation,
    legacy_audit_trail,
)

from prescient.risk.models import ExecutionMode, TradeExpression


class BrokerOrderStatus(StrEnum):
    SUBMITTED = "submitted"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderStatusFilter(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class BrokerPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    expression: TradeExpression
    qty: float
    market_value: float
    average_entry_price: float


class BrokerOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    symbol: str
    qty: int
    filled_qty: int
    limit_price: float | None
    status: BrokerOrderStatus
    submitted_at: datetime
    side: str = "buy"
    source_citations: list[SourceCitation] = Field(default_factory=list)
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.BROKER_ORDER,
            decision_layer=DecisionLayer.BROKER,
        )
    )


class BrokerCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supports_options: bool
    supports_paper_trading: bool
    broker_name: str


class OrderExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    broker: str | None = None
    order_id: str
    status: BrokerOrderStatus
    filled_qty: int = 0
    avg_fill_price: float | None = None
    submitted_at: datetime | None = None
    message: str | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.BROKER_ORDER_RESULT,
            decision_layer=DecisionLayer.BROKER,
        )
    )


class BrokerSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = "mock"
    execution_mode: ExecutionMode = ExecutionMode.PROPOSE_ONLY
    slippage_buffer_pct: float = 0.01
    connection_timeout_sec: int = 10


# Exception Hierarchy
class BrokerError(Exception):
    """Base exception for all broker operations."""
    pass


class ConfigurationError(BrokerError):
    """Exception raised when broker configuration is invalid or unsupported."""
    pass


class BrokerConnectionError(BrokerError):
    """Exception raised when connection to the broker API fails."""
    pass


class BrokerAuthenticationError(BrokerError):
    """Exception raised when API authentication/keys are rejected."""
    pass


class BrokerRateLimitError(BrokerError):
    """Exception raised when broker rate limits are hit."""
    pass


class BrokerExecutionError(BrokerError):
    """Exception raised when broker rejects the order placement/modification."""
    pass


class UnsupportedCapabilityError(BrokerError):
    """Exception raised when requesting an execution not supported by the broker capabilities."""
    pass
