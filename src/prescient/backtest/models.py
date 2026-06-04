from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from statistics import mean, median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.analytics import (
    MetricsEvaluationStatus,
    PerformanceAnalyticsRequest,
    PerformanceObservation,
    compare_to_buy_hold,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategySettings,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
)


class BacktestOutcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    FLAT = "flat"
    NOT_EVALUABLE = "not_evaluable"


class BacktestTradeExpression(StrEnum):
    STOCK = "STOCK"
    CALL_OPTION = "CALL_OPTION"

    @classmethod
    def normalize(cls, value: Any) -> "BacktestTradeExpression":
        if isinstance(value, cls):
            return value

        normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "CALL": cls.CALL_OPTION,
            "CALL_OPTION": cls.CALL_OPTION,
            "OPTION": cls.CALL_OPTION,
            "STOCK": cls.STOCK,
            "EQUITY": cls.STOCK,
            "SHARES": cls.STOCK,
        }
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError(f"Unsupported backtest trade expression: {value}")


class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    start_date: date
    end_date: date
    max_events: int | None = None
    strategy_type: str = "bullish_earnings_readthrough"
    evaluation_horizon_days: int = 1
    include_rejected_candidates: bool = True
    include_trade_pnl: bool = True
    positive_followthrough_threshold_pct: float = 1.0
    negative_followthrough_threshold_pct: float = -1.0
    starting_equity: float = 10_000.0
    annual_risk_free_rate: float = 0.0

    @field_validator("run_id")
    @classmethod
    def require_run_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Backtest run ID must not be empty.")
        return cleaned

    @field_validator("strategy_type")
    @classmethod
    def normalize_strategy_type(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Backtest strategy type must not be empty.")
        return cleaned

    @field_validator("evaluation_horizon_days")
    @classmethod
    def require_positive_horizon(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Backtest evaluation horizon must be positive.")
        return value

    @field_validator("max_events")
    @classmethod
    def require_positive_max_events(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Backtest max_events must be positive when provided.")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "BacktestRunRequest":
        if self.start_date > self.end_date:
            raise ValueError("Backtest start_date cannot be after end_date.")
        if self.positive_followthrough_threshold_pct <= self.negative_followthrough_threshold_pct:
            raise ValueError(
                "Backtest positive threshold must be greater than negative threshold."
            )
        return self


class HistoricalPricePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    trading_date: date
    close: float | None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)


class HistoricalOptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    option_type: BacktestTradeExpression
    expiration_date: date
    trading_date: date
    bid: float | None
    ask: float | None
    open_interest: int | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @field_validator("option_type", mode="before")
    @classmethod
    def normalize_option_type(cls, value: Any) -> BacktestTradeExpression:
        return BacktestTradeExpression.normalize(value)


class UnderlyingFollowThroughOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    evaluation_start: date
    evaluation_end: date
    entry_reference_price: float | None = None
    exit_reference_price: float | None = None
    return_pct: float | None = None
    expected_direction: str = "bullish"
    outcome: BacktestOutcome
    reason: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @property
    def entry_price(self) -> float | None:
        return self.entry_reference_price

    @property
    def exit_price(self) -> float | None:
        return self.exit_reference_price


class TradePnlOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    expression: BacktestTradeExpression
    quantity: float
    entry_price: float | None = None
    exit_price: float | None = None
    gross_pnl: float | None = None
    fees: float = 0.0
    net_pnl: float | None = None
    return_on_risk_pct: float | None = None
    outcome: BacktestOutcome
    reason: str | None = None
    not_evaluable_reason: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @field_validator("expression", mode="before")
    @classmethod
    def normalize_expression(cls, value: Any) -> BacktestTradeExpression:
        return BacktestTradeExpression.normalize(value)

    @model_validator(mode="before")
    @classmethod
    def mirror_not_evaluable_reason(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        reason = data.get("reason") or data.get("not_evaluable_reason")
        if reason is None:
            return data
        return {**data, "reason": reason, "not_evaluable_reason": reason}


class BacktestSetupResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_id: str
    target: str
    ticker: str
    theme: str | None = None
    earnings_date: date | None = None
    entry_date: date
    exit_date: date
    strategy_status: StrategyStatus
    recommended_expression: BacktestTradeExpression | None = None
    expression: BacktestTradeExpression = BacktestTradeExpression.STOCK
    allocated_capital: float = 0.0
    underlying_entry_price: float | None = None
    underlying_exit_price: float | None = None
    underlying_outcome: UnderlyingFollowThroughOutcome | None = None
    trade_pnl: TradePnlOutcome | None = None
    reported_peers: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_compatibility_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        target = data.get("target") or data.get("ticker")
        ticker = data.get("ticker") or target
        earnings_date = data.get("earnings_date") or data.get("entry_date")
        entry_date = data.get("entry_date") or earnings_date
        exit_date = data.get("exit_date") or entry_date
        expression = data.get("expression") or data.get("recommended_expression")
        recommended = data.get("recommended_expression") or expression
        setup_id = data.get("setup_id") or f"{ticker}:{earnings_date}"
        underlying = data.get("underlying_outcome")

        if isinstance(underlying, UnderlyingFollowThroughOutcome):
            underlying_entry = underlying.entry_reference_price
            underlying_exit = underlying.exit_reference_price
        elif isinstance(underlying, dict):
            underlying_entry = underlying.get("entry_reference_price")
            underlying_exit = underlying.get("exit_reference_price")
        else:
            underlying_entry = None
            underlying_exit = None

        return {
            **data,
            "setup_id": setup_id,
            "target": target,
            "ticker": ticker,
            "earnings_date": earnings_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "expression": expression or BacktestTradeExpression.STOCK,
            "recommended_expression": recommended,
            "underlying_entry_price": data.get(
                "underlying_entry_price",
                underlying_entry,
            ),
            "underlying_exit_price": data.get(
                "underlying_exit_price",
                underlying_exit,
            ),
        }

    @field_validator("target", "ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None and value.strip() else None

    @field_validator("reported_peers")
    @classmethod
    def normalize_reported_peers(cls, values: list[str]) -> list[str]:
        return [_normalize_ticker(value) for value in values]

    @field_validator("expression", "recommended_expression", mode="before")
    @classmethod
    def normalize_expression(cls, value: Any) -> BacktestTradeExpression | None:
        if value is None:
            return None
        return BacktestTradeExpression.normalize(value)


class BacktestSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_setups: int = 0
    candidate_ready_count: int = 0
    rejected_count: int = 0
    not_evaluable_count: int = 0
    underlying_win_count: int = 0
    underlying_loss_count: int = 0
    underlying_flat_count: int = 0
    underlying_not_evaluable_count: int = 0
    trade_win_count: int = 0
    trade_loss_count: int = 0
    trade_flat_count: int = 0
    trade_not_evaluable_count: int = 0
    average_underlying_return_pct: float | None = None
    median_underlying_return_pct: float | None = None
    average_net_pnl: float | None = None
    median_net_pnl: float | None = None
    by_theme: dict[str, int] = Field(default_factory=dict)
    by_ticker: dict[str, int] = Field(default_factory=dict)
    by_expression: dict[str, int] = Field(default_factory=dict)
    top_rejection_reasons: dict[str, int] = Field(default_factory=dict)
    win_rate: float | None = None
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    total_return_pct: float | None = None
    buy_hold_total_return_pct: float | None = None
    beats_buy_and_hold: bool | None = None
    excess_return_pct: float | None = None
    benchmark_status: MetricsEvaluationStatus = MetricsEvaluationStatus.NOT_EVALUABLE
    metrics_status: MetricsEvaluationStatus = MetricsEvaluationStatus.NOT_EVALUABLE
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_setups(
        cls,
        setups: list[BacktestSetupResult],
        request: BacktestRunRequest | None = None,
        warnings: list[str] | None = None,
    ) -> "BacktestSummary":
        underlying_returns = [
            outcome.return_pct
            for setup in setups
            for outcome in [setup.underlying_outcome]
            if outcome is not None and outcome.return_pct is not None
        ]
        net_pnls = [
            pnl.net_pnl
            for setup in setups
            for pnl in [setup.trade_pnl]
            if pnl is not None and pnl.net_pnl is not None
        ]
        comparison = compare_to_buy_hold(
            PerformanceAnalyticsRequest(
                observations=_performance_observations(setups),
                starting_equity=request.starting_equity if request is not None else 10_000.0,
                annual_risk_free_rate=(
                    request.annual_risk_free_rate if request is not None else 0.0
                ),
            )
        )
        metrics = comparison.strategy_metrics

        return cls(
            total_setups=len(setups),
            candidate_ready_count=sum(
                setup.strategy_status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
                for setup in setups
            ),
            rejected_count=sum(
                setup.strategy_status == StrategyStatus.REJECTED_WITH_REASON
                for setup in setups
            ),
            not_evaluable_count=sum(
                _setup_has_not_evaluable_outcome(setup) for setup in setups
            ),
            underlying_win_count=_underlying_count(setups, BacktestOutcome.WIN),
            underlying_loss_count=_underlying_count(setups, BacktestOutcome.LOSS),
            underlying_flat_count=_underlying_count(setups, BacktestOutcome.FLAT),
            underlying_not_evaluable_count=_underlying_count(
                setups,
                BacktestOutcome.NOT_EVALUABLE,
            ),
            trade_win_count=_trade_count(setups, BacktestOutcome.WIN),
            trade_loss_count=_trade_count(setups, BacktestOutcome.LOSS),
            trade_flat_count=_trade_count(setups, BacktestOutcome.FLAT),
            trade_not_evaluable_count=_trade_count(
                setups,
                BacktestOutcome.NOT_EVALUABLE,
            ),
            average_underlying_return_pct=_average_or_none(underlying_returns),
            median_underlying_return_pct=_median_or_none(underlying_returns),
            average_net_pnl=_average_or_none(net_pnls),
            median_net_pnl=_median_or_none(net_pnls),
            by_theme=_bucket(setup.theme for setup in setups if setup.theme is not None),
            by_ticker=_bucket(setup.target for setup in setups),
            by_expression=_bucket(
                setup.recommended_expression.value
                for setup in setups
                if setup.recommended_expression is not None
            ),
            top_rejection_reasons=_bucket(
                reason for setup in setups for reason in setup.rejection_reasons
            ),
            win_rate=metrics.win_rate,
            max_drawdown_pct=metrics.max_drawdown_pct,
            sharpe_ratio=metrics.sharpe_ratio,
            total_return_pct=metrics.total_return_pct,
            buy_hold_total_return_pct=comparison.buy_hold_total_return_pct,
            beats_buy_and_hold=comparison.beats_buy_and_hold,
            excess_return_pct=comparison.excess_return_pct,
            benchmark_status=comparison.benchmark_status,
            metrics_status=metrics.status,
            excluded_counts=_merge_counts(metrics.excluded_counts, comparison.excluded_counts),
            warnings=warnings or [],
        )


class BacktestRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    request: BacktestRunRequest | None = None
    setups: list[BacktestSetupResult] = Field(default_factory=list)
    summary: BacktestSummary = Field(default_factory=BacktestSummary)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_run_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        request = data.get("request")
        if data.get("run_id") is None and isinstance(request, BacktestRunRequest):
            return {**data, "run_id": request.run_id}
        if data.get("run_id") is None and isinstance(request, dict):
            return {**data, "run_id": request.get("run_id")}
        return data


class BacktestDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_results: list[BacktestSetupResult] = Field(default_factory=list)
    prices: list[HistoricalPricePoint] = Field(default_factory=list)
    option_quotes: list[HistoricalOptionQuote] = Field(default_factory=list)
    universe: StrategyUniverse | None = None
    upcoming_events: list[EarningsCalendarEvent] = Field(default_factory=list)
    peer_results: list[PeerResult] = Field(default_factory=list)
    target_market_data: dict[str, TargetMarketData] = Field(default_factory=dict)
    options_chains: dict[str, list[OptionContractSnapshot]] = Field(default_factory=dict)
    settings: StrategySettings = Field(default_factory=StrategySettings)

    @field_validator("target_market_data", mode="before")
    @classmethod
    def normalize_market_data_keys(
        cls,
        value: dict[str, TargetMarketData],
    ) -> dict[str, TargetMarketData]:
        return {_normalize_ticker(ticker): data for ticker, data in value.items()}

    @field_validator("options_chains", mode="before")
    @classmethod
    def normalize_options_chain_keys(
        cls,
        value: dict[str, list[OptionContractSnapshot]],
    ) -> dict[str, list[OptionContractSnapshot]]:
        return {_normalize_ticker(ticker): chain for ticker, chain in value.items()}


def _normalize_ticker(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("Ticker must not be empty.")
    return cleaned


def _setup_has_not_evaluable_outcome(setup: BacktestSetupResult) -> bool:
    return (
        setup.underlying_outcome is not None
        and setup.underlying_outcome.outcome == BacktestOutcome.NOT_EVALUABLE
    ) or (
        setup.trade_pnl is not None
        and setup.trade_pnl.outcome == BacktestOutcome.NOT_EVALUABLE
    )


def _underlying_count(
    setups: list[BacktestSetupResult],
    outcome: BacktestOutcome,
) -> int:
    return sum(
        setup.underlying_outcome is not None
        and setup.underlying_outcome.outcome == outcome
        for setup in setups
    )


def _trade_count(setups: list[BacktestSetupResult], outcome: BacktestOutcome) -> int:
    return sum(
        setup.trade_pnl is not None and setup.trade_pnl.outcome == outcome
        for setup in setups
    )


def _average_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def _bucket(values: Iterable[str]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for value in values:
        buckets[value] = buckets.get(value, 0) + 1
    return buckets


def _merge_counts(*items: dict[str, int]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in items:
        counter.update(item)
    return dict(counter)


def _performance_observations(
    setups: list[BacktestSetupResult],
) -> list[PerformanceObservation]:
    observations: list[PerformanceObservation] = []
    for setup in setups:
        if setup.trade_pnl is None:
            continue
        observations.append(
            PerformanceObservation(
                observation_id=setup.setup_id,
                ticker=setup.target,
                entry_date=setup.entry_date,
                exit_date=setup.exit_date,
                allocated_capital=setup.allocated_capital,
                strategy_net_pnl=setup.trade_pnl.net_pnl,
                benchmark_entry_price=setup.underlying_entry_price,
                benchmark_exit_price=setup.underlying_exit_price,
            )
        )
    return observations
