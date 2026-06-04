from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    legacy_audit_trail,
)
from prescient.signal.models import StrategyStatus


class RiskGateStatus(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"
    NOT_EVALUABLE = "not_evaluable"


class RiskRejectionReason(StrEnum):
    STRATEGY_NOT_CANDIDATE_READY = "strategy_not_candidate_ready"
    MISSING_ACCOUNT_SNAPSHOT = "missing_account_snapshot"
    MISSING_ORDER_PROPOSAL = "missing_order_proposal"
    CLAUDE_OVERRIDE_ATTEMPTED = "claude_override_attempted"
    RISK_CHECKS_NOT_IMPLEMENTED = "risk_checks_not_implemented"
    ACCOUNT_EQUITY_MISSING = "account_equity_missing"
    ACCOUNT_EQUITY_TOO_SMALL = "account_equity_too_small"
    MAX_TRADE_LOSS_EXCEEDED = "max_trade_loss_exceeded"
    SMALLEST_TRADE_EXCEEDS_CAP = "smallest_trade_exceeds_cap"
    STOP_PRICE_MISSING = "stop_price_missing"
    ENTRY_PRICE_MISSING = "entry_price_missing"
    INVALID_CONTRACT_MULTIPLIER = "invalid_contract_multiplier"
    INVALID_QUANTITY = "invalid_quantity"
    RISK_CAP_ABOVE_ALLOWED_CEILING = "risk_cap_above_allowed_ceiling"
    MAX_LOSS_NOT_COMPUTABLE = "max_loss_not_computable"
    CONCENTRATION_LIMIT_EXCEEDED = "concentration_limit_exceeded"
    AVERAGING_DOWN_BLOCKED = "averaging_down_blocked"
    BROKER_STATE_UNAVAILABLE = "broker_state_unavailable"


class PositionSizingStatus(StrEnum):
    SIZED = "sized"
    BLOCKED = "blocked"
    NOT_EVALUABLE = "not_evaluable"


class PositionSizingRejectionReason(StrEnum):
    STRATEGY_NOT_CANDIDATE_READY = "strategy_not_candidate_ready"
    MISSING_ACCOUNT_SNAPSHOT = "missing_account_snapshot"
    MISSING_ORDER_PROPOSAL = "missing_order_proposal"
    ACCOUNT_EQUITY_MISSING = "account_equity_missing"
    ACCOUNT_EQUITY_TOO_SMALL = "account_equity_too_small"
    RISK_BUDGET_MISSING = "risk_budget_missing"
    ENTRY_PRICE_MISSING = "entry_price_missing"
    STOP_PRICE_MISSING = "stop_price_missing"
    UNIT_MAX_LOSS_MISSING = "unit_max_loss_missing"
    UNIT_MAX_LOSS_INVALID = "unit_max_loss_invalid"
    SMALLEST_TRADE_EXCEEDS_RISK_BUDGET = "smallest_trade_exceeds_risk_budget"
    INSUFFICIENT_CASH_OR_BUYING_POWER = "insufficient_cash_or_buying_power"
    UNSUPPORTED_EXPRESSION = "unsupported_expression"
    INVALID_CONTRACT_MULTIPLIER = "invalid_contract_multiplier"
    QUANTITY_NOT_INTEGER = "quantity_not_integer"
    INVALID_QUANTITY = "invalid_quantity"
    RISK_CAP_ABOVE_ALLOWED_CEILING = "risk_cap_above_allowed_ceiling"
    MAX_LOSS_NOT_COMPUTABLE = "max_loss_not_computable"
    CLAUDE_SIZING_OVERRIDE_ATTEMPTED = "claude_sizing_override_attempted"
    CONCENTRATION_LIMIT_EXCEEDED = "concentration_limit_exceeded"
    AVERAGING_DOWN_BLOCKED = "averaging_down_blocked"
    BROKER_STATE_UNAVAILABLE = "broker_state_unavailable"


class RiskDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"


class RiskReviewFlag(StrEnum):
    THREE_PERCENT_CAP_REQUIRES_REVIEW = "three_percent_cap_requires_review"
    SMALL_ACCOUNT = "small_account"
    OPTIONS_CONTRACT_NEAR_CAP = "options_contract_near_cap"
    PROPOSE_ONLY_RECOMMENDED = "propose_only_recommended"


class AccountSizeTier(StrEnum):
    BELOW_SUPPORTED_TIER = "below_supported_tier"
    SUPPORTED_10K_25K = "supported_10k_25k"
    ABOVE_SUPPORTED_TIER = "above_supported_tier"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    PROPOSE_ONLY = "propose_only"
    LIVE = "live"


class AccountSizePolicyStatus(StrEnum):
    ELIGIBLE = "eligible"
    RESTRICTED = "restricted"
    REVIEW_REQUIRED = "review_required"


class AccountSizePolicyReason(StrEnum):
    ACCOUNT_EQUITY_MISSING = "account_equity_missing"
    ACCOUNT_EQUITY_INVALID = "account_equity_invalid"
    ACCOUNT_BELOW_SUPPORTED_TIER = "account_below_supported_tier"
    ACCOUNT_ABOVE_SUPPORTED_TIER = "account_above_supported_tier"
    RISK_CAP_ABOVE_TIER_DEFAULT = "risk_cap_above_tier_default"
    RISK_CAP_ABOVE_ABSOLUTE_CEILING = "risk_cap_above_absolute_ceiling"
    BROKER_DAY_TRADE_POLICY_UNVERIFIED = "broker_day_trade_policy_unverified"


class TradeExpression(StrEnum):
    CALL_OPTION = "CALL_OPTION"
    PUT_OPTION = "PUT_OPTION"
    STOCK = "STOCK"


class DailyHaltStatus(StrEnum):
    ALLOWED = "allowed"
    HALTED = "halted"


class ExecutionQualityStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    NOT_EVALUABLE = "not_evaluable"


class DailyHaltReason(StrEnum):
    DAILY_LOSS_LIMIT_EXCEEDED = "daily_loss_limit_exceeded"
    TOO_MANY_LOSING_TRADES = "too_many_losing_trades"
    ACCOUNT_EQUITY_MISSING = "account_equity_missing"
    DAILY_PNL_MISSING = "daily_pnl_missing"
    LOSING_TRADE_COUNT_MISSING = "losing_trade_count_missing"
    TRADING_DAY_MISSING = "trading_day_missing"


class DailyRiskAction(StrEnum):
    NEW_ENTRY = "new_entry"
    ADD_TO_POSITION = "add_to_position"
    OPEN_OPTION_CONTRACT = "open_option_contract"
    RISK_INCREASING_REPLACEMENT_ORDER = "risk_increasing_replacement_order"
    EXIT_POSITION = "exit_position"
    REDUCE_POSITION = "reduce_position"
    CANCEL_ORDER = "cancel_order"
    RISK_REDUCING_ORDER = "risk_reducing_order"


class DailyHaltScope(StrEnum):
    NEW_RISK_ONLY = "new_risk_only"


class MarketSessionStatus(StrEnum):
    REGULAR_OPEN = "regular_open"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    HALTED = "halted"
    UNKNOWN = "unknown"


class ExecutionQualityRejectionReason(StrEnum):
    MARKET_SESSION_MISSING = "market_session_missing"
    MARKET_SESSION_UNKNOWN = "market_session_unknown"
    OUTSIDE_REGULAR_MARKET_HOURS = "outside_regular_market_hours"
    SYMBOL_HALTED = "symbol_halted"
    TOO_CLOSE_TO_MARKET_CLOSE = "too_close_to_market_close"
    QUOTE_MISSING = "quote_missing"
    QUOTE_STALE = "quote_stale"
    BID_ASK_MISSING = "bid_ask_missing"
    INVALID_BID_ASK = "invalid_bid_ask"
    STOCK_SPREAD_TOO_WIDE = "stock_spread_too_wide"
    OPTION_SPREAD_TOO_WIDE = "option_spread_too_wide"
    AVERAGE_VOLUME_MISSING = "average_volume_missing"
    AVERAGE_VOLUME_TOO_LOW = "average_volume_too_low"
    OPTION_OPEN_INTEREST_MISSING = "option_open_interest_missing"
    OPTION_OPEN_INTEREST_TOO_LOW = "option_open_interest_too_low"
    REWARD_RISK_MISSING = "reward_risk_missing"
    REWARD_RISK_BELOW_MINIMUM = "reward_risk_below_minimum"
    ENTRY_PRICE_MISSING = "entry_price_missing"
    STOP_OR_MAX_LOSS_MISSING = "stop_or_max_loss_missing"
    TARGET_PRICE_MISSING = "target_price_missing"
    UNSUPPORTED_EXPRESSION = "unsupported_expression"
    RISK_REDUCING_ACTION_NOT_ALLOWED = "risk_reducing_action_not_allowed"


class ExecutionQualityWarning(StrEnum):
    RISK_REDUCING_ACTION_ALLOWED_WITHOUT_NEW_RISK_CHECKS = (
        "risk_reducing_action_allowed_without_new_risk_checks"
    )
    EARLY_CLOSE_SESSION = "early_close_session"


class RiskSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_trade_loss_pct: float = 0.03


class AccountSizePolicySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supported_min_equity: float = 10_000.0
    supported_max_equity: float = 25_000.0
    tier_default_trade_loss_pct: float = 0.01
    absolute_trade_loss_pct_ceiling: float = 0.03
    configured_trade_loss_pct: float | None = None

    @field_validator(
        "supported_min_equity",
        "supported_max_equity",
        "tier_default_trade_loss_pct",
        "absolute_trade_loss_pct_ceiling",
    )
    @classmethod
    def require_positive_settings(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Account-size policy settings must be positive.")
        return value

    @field_validator("configured_trade_loss_pct")
    @classmethod
    def require_positive_configured_cap(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("Configured trade-loss percentage must be positive.")
        return value

    @model_validator(mode="after")
    def validate_account_size_policy_settings(self) -> "AccountSizePolicySettings":
        if self.supported_min_equity > self.supported_max_equity:
            raise ValueError("Supported minimum equity cannot exceed maximum equity.")

        if self.tier_default_trade_loss_pct > self.absolute_trade_loss_pct_ceiling:
            raise ValueError("Tier default cap cannot exceed absolute cap ceiling.")

        return self


class DailyHaltSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_daily_realized_loss_pct: float = 0.05
    max_losing_trades_per_day: int = 2
    halt_scope: DailyHaltScope = DailyHaltScope.NEW_RISK_ONLY
    allow_risk_reducing_actions: bool = True


class ExecutionQualitySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_reward_to_risk_ratio: float = 2.0
    min_avg_daily_volume: int = 1_000_000
    max_stock_bid_ask_spread_pct: float = 0.50
    max_option_bid_ask_spread_pct: float = 15.0
    min_option_open_interest: int = 100
    max_quote_age_seconds: int = 15
    min_minutes_before_close_for_new_risk: int = 5
    allow_risk_reducing_actions: bool = True

    @field_validator(
        "min_reward_to_risk_ratio",
        "max_stock_bid_ask_spread_pct",
        "max_option_bid_ask_spread_pct",
    )
    @classmethod
    def require_positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Execution-quality settings must be positive.")
        return value

    @field_validator(
        "min_avg_daily_volume",
        "min_option_open_interest",
        "max_quote_age_seconds",
    )
    @classmethod
    def require_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Execution-quality settings must be positive.")
        return value

    @field_validator("min_minutes_before_close_for_new_risk")
    @classmethod
    def require_non_negative_minutes(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Market-close buffer cannot be negative.")
        return value


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_equity: float | None


class TradeProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    expression: TradeExpression
    entry_price: float | None
    stop_price: float | None = None
    contract_multiplier: int | None = 100
    minimum_quantity: int | None = 1

    @field_validator("target")
    @classmethod
    def normalize_trade_target(cls, value: str) -> str:
        return value.strip().upper()


class RiskDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RiskDecisionStatus
    target: str | None
    account_equity: float | None
    max_trade_loss_pct: float
    max_allowed_loss: float | None
    proposed_expression: TradeExpression | None
    entry_price: float | None
    stop_price: float | None
    unit_max_loss: float | None
    approved_quantity: int
    projected_max_loss: float | None
    rejection_reasons: list[RiskRejectionReason] = Field(default_factory=list)
    review_flags: list[RiskReviewFlag] = Field(default_factory=list)
    broker_execution_allowed: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.TRADE_RISK,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @field_validator("target")
    @classmethod
    def normalize_decision_target(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_broker_execution(self) -> "RiskDecision":
        if self.status != RiskDecisionStatus.APPROVED and self.broker_execution_allowed:
            raise ValueError("Broker execution is allowed only for approved trade risk decisions.")

        if self.status == RiskDecisionStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("Rejected trade risk decisions must include rejection reasons.")

        return self


class AccountSizePolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: AccountSizePolicyStatus
    account_equity: float | None
    account_size_tier: AccountSizeTier | None
    requested_mode: ExecutionMode
    recommended_max_trade_loss_pct: float
    absolute_max_trade_loss_pct: float
    recommended_max_trade_loss_amount: float | None
    absolute_max_trade_loss_amount: float | None
    recommended_risk_settings: RiskSettings
    effective_risk_settings: RiskSettings
    live_trading_eligible: bool
    paper_trading_allowed: bool
    propose_only_recommended: bool
    reasons: list[AccountSizePolicyReason] = Field(default_factory=list)
    review_flags: list[AccountSizePolicyReason] = Field(default_factory=list)
    warnings: list[AccountSizePolicyReason] = Field(default_factory=list)
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.ACCOUNT_SIZE_POLICY,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @model_validator(mode="after")
    def validate_account_size_decision(self) -> "AccountSizePolicyDecision":
        if self.status != AccountSizePolicyStatus.ELIGIBLE and not self.reasons:
            raise ValueError("Restricted or review-required account policies need reasons.")

        if self.status != AccountSizePolicyStatus.ELIGIBLE and self.live_trading_eligible:
            raise ValueError("Only eligible account policies can allow live trading.")

        if self.status == AccountSizePolicyStatus.ELIGIBLE and self.reasons:
            raise ValueError("Eligible account policies must not include reasons.")

        return self


class DailyRiskState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_equity: float | None
    trading_day: date | None
    realized_pnl: float | None
    losing_trade_count: int | None
    halted_until: date | None = None
    prior_halt_reasons: list[DailyHaltReason] = Field(default_factory=list)


class MarketSessionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_date: date | None
    session_status: MarketSessionStatus
    is_halted: bool = False
    is_early_close: bool = False
    timezone: str = "America/New_York"
    minutes_to_close: int | None = None


class ExecutionQuoteSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    expression: TradeExpression
    bid: float | None
    ask: float | None
    last_price: float | None = None
    avg_daily_volume: int | None = None
    quote_age_seconds: int | None = None
    option_open_interest: int | None = None

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()


class RewardRiskProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    expected_reward: float | None = None
    maximum_loss: float | None = None


class DailyHaltDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DailyHaltStatus
    trading_day: date | None
    account_equity: float | None
    max_daily_loss_pct: float
    max_daily_loss_amount: float | None
    realized_pnl: float | None
    losing_trade_count: int | None
    halted_until: date | None = None
    halt_reasons: list[DailyHaltReason] = Field(default_factory=list)
    allowed_actions: list[DailyRiskAction] = Field(default_factory=list)
    blocked_actions: list[DailyRiskAction] = Field(default_factory=list)
    broker_execution_allowed_for_new_risk: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.DAILY_HALT,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @model_validator(mode="after")
    def validate_halt_contract(self) -> "DailyHaltDecision":
        if self.status == DailyHaltStatus.HALTED and not self.halt_reasons:
            raise ValueError("Halted daily risk decisions must include halt reasons.")

        if (
            self.status == DailyHaltStatus.HALTED
            and self.broker_execution_allowed_for_new_risk
        ):
            raise ValueError("Halted daily risk decisions cannot allow new risk.")

        if self.status == DailyHaltStatus.ALLOWED and self.halt_reasons:
            raise ValueError("Allowed daily risk decisions must not include halt reasons.")

        return self


class ExecutionQualityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExecutionQualityStatus
    target: str | None
    expression: TradeExpression | None
    proposed_action: DailyRiskAction
    market_date: date | None
    session_status: MarketSessionStatus | None
    spread_pct: float | None
    reward_risk_ratio: float | None
    rejection_reasons: list[ExecutionQualityRejectionReason] = Field(default_factory=list)
    warnings: list[ExecutionQualityWarning] = Field(default_factory=list)
    allowed_actions: list[DailyRiskAction] = Field(default_factory=list)
    blocked_actions: list[DailyRiskAction] = Field(default_factory=list)
    broker_execution_allowed_for_new_risk: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.EXECUTION_QUALITY,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_execution_quality_contract(self) -> "ExecutionQualityDecision":
        if (
            self.status == ExecutionQualityStatus.ALLOWED
            and self.rejection_reasons
        ):
            raise ValueError("Allowed execution-quality decisions must not include rejections.")

        if (
            self.status != ExecutionQualityStatus.ALLOWED
            and not self.rejection_reasons
        ):
            raise ValueError("Blocked execution-quality decisions must include rejections.")

        if (
            self.status != ExecutionQualityStatus.ALLOWED
            and self.broker_execution_allowed_for_new_risk
        ):
            raise ValueError("Only allowed execution-quality decisions can allow new risk.")

        return self


class AccountRiskSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equity: float
    cash: float
    buying_power: float


class RiskOrderProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    expression: Literal["CALL_OPTION", "STOCK"]
    estimated_entry_cost: float
    maximum_loss: float

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()


class RiskGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    theme: str | None
    strategy_status: StrategyStatus
    status: RiskGateStatus
    rejection_reasons: list[RiskRejectionReason] = Field(default_factory=list)
    explanation: str
    broker_execution_allowed: bool
    claude_present: bool
    claude_override_attempted: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.RISK_GATE,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_broker_permission(self) -> "RiskGateDecision":
        if self.status != RiskGateStatus.APPROVED and self.broker_execution_allowed:
            raise ValueError("Broker execution is allowed only for approved risk decisions.")

        if self.claude_override_attempted and (
            RiskRejectionReason.CLAUDE_OVERRIDE_ATTEMPTED not in self.rejection_reasons
        ):
            raise ValueError("Claude override attempts must include a rejection reason.")

        return self


class PositionSizingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PositionSizingStatus
    target: str
    theme: str | None
    strategy_status: StrategyStatus
    expression: TradeExpression | None
    account_equity: float | None
    risk_budget: float | None
    unit_max_loss: float | None
    approved_quantity: int
    projected_max_loss: float | None
    entry_cost_required: float | None
    rejection_reasons: list[PositionSizingRejectionReason] = Field(default_factory=list)
    warnings: list[RiskReviewFlag] = Field(default_factory=list)
    explanation: str
    claude_present: bool
    claude_sizing_override_attempted: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.POSITION_SIZING,
            decision_layer=DecisionLayer.RISK,
        )
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_sizing_contract(self) -> "PositionSizingDecision":
        if self.status == PositionSizingStatus.SIZED and self.rejection_reasons:
            raise ValueError("Sized position decisions must not include rejection reasons.")

        if self.status != PositionSizingStatus.SIZED and not self.rejection_reasons:
            raise ValueError("Unsized position decisions must include rejection reasons.")

        if self.status == PositionSizingStatus.SIZED and self.approved_quantity < 1:
            raise ValueError("Sized position decisions must include a positive quantity.")

        if self.approved_quantity < 0:
            raise ValueError("Approved quantity cannot be negative.")

        if self.claude_sizing_override_attempted and (
            PositionSizingRejectionReason.CLAUDE_SIZING_OVERRIDE_ATTEMPTED
            not in self.rejection_reasons
        ):
            raise ValueError("Claude sizing override attempts must include a rejection reason.")

        return self


class RiskPosition(BaseModel):
    """Broker-reported position projected into risk-domain terms.

    This model is defined in the risk domain (not the broker module) so that
    the risk gatekeeper can consume it without importing broker modules.
    The runtime pipeline is responsible for mapping BrokerPosition → RiskPosition.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    expression: TradeExpression
    qty: float
    market_value: float
    average_entry_price: float


class RiskOrder(BaseModel):
    """Broker-reported order projected into risk-domain terms."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    symbol: str
    qty: int
    filled_qty: int
    limit_price: float | None
    status: str  # "open" | "filled" | "cancelled" | "rejected"
    submitted_at: datetime
    side: str = "buy"


class ConcentrationSettings(BaseModel):
    """Settings for portfolio concentration checks."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_open_positions: int = 5
    max_single_ticker_exposure_pct: float = 0.20
