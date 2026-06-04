from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    SourceCitation,
    legacy_audit_trail,
)
from prescient.data.models import TranscriptSummary
from prescient.signal.strategy_types import PreferredExpression, StrategyDirection, StrategyType


ReportTime = Literal["BMO", "AMC", "UNKNOWN"]
SignalValue = Literal["positive", "neutral", "negative", "unknown"]
OptionType = Literal["CALL", "PUT"]


class MacdState(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class PriceVsVwapState(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    NEAR = "near"
    UNKNOWN = "unknown"


class IndicatorFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class ThesisStatus(StrEnum):
    VALID = "valid"
    INSUFFICIENT_PEER_CONTEXT = "insufficient_peer_context"
    INVALID_THEME = "invalid_theme"
    MISSING_DRIVER_EVIDENCE = "missing_driver_evidence"
    UNSUPPORTED_STRATEGY = "unsupported_strategy"


class CandidateDetectionStatus(StrEnum):
    CANDIDATE = "candidate"
    CANDIDATE_FOUND = "candidate"
    REJECTED = "rejected"


class CandidateRejectionReason(StrEnum):
    THEME_NOT_CONFIGURED = "theme_not_configured"
    EARNINGS_DATE_MISSING = "earnings_date_missing"
    OUTSIDE_EARNINGS_WINDOW = "outside_earnings_window"
    INSUFFICIENT_REPORTED_PEERS = "insufficient_reported_peers"


class RejectionReason(StrEnum):
    THEME_NOT_CONFIGURED = "theme_not_configured"
    EARNINGS_DATE_UNCERTAIN = "earnings_date_uncertain"
    INSUFFICIENT_PEERS_REPORTED = "insufficient_peers_reported"
    PEER_SIGNAL_TOO_WEAK = "peer_signal_too_weak"
    CONFLICTING_NEWS = "conflicting_news"
    TARGET_ALREADY_OVEREXTENDED = "target_already_overextended"
    TARGET_TOO_ILLIQUID = "target_too_illiquid"
    OPTIONS_TOO_ILLIQUID = "options_too_illiquid"
    MISSING_DATA = "missing_data"
    TARGET_EVENT_INVALIDATES_PEER_COMPARISON = (
        "target_event_invalidates_peer_comparison"
    )


class TargetFilterStatus(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"


class StrategyStatus(StrEnum):
    NO_TRADE = "no_trade"
    CANDIDATE_READY_FOR_ANALYST = "candidate_ready_for_analyst"
    REJECTED_WITH_REASON = "rejected_with_reason"


class RejectionStage(StrEnum):
    CANDIDATE_DETECTION = "candidate_detection"
    PEER_SIGNAL = "peer_signal"
    TARGET_FILTER = "target_filter"
    STRATEGY_OUTPUT = "strategy_output"


class RejectionDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: RejectionReason
    stage: RejectionStage
    message: str


class ThemeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tickers: list[str]
    drivers: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, values: list[str]) -> list[str]:
        normalized = [ticker.strip().upper() for ticker in values]
        if len(normalized) < 2:
            raise ValueError("Theme must contain at least 2 tickers.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Theme tickers must not contain duplicates.")
        return normalized

    @field_validator("drivers")
    @classmethod
    def clean_drivers(cls, values: list[str]) -> list[str]:
        return [driver.strip() for driver in values if driver.strip()]


class StrategyUniverse(BaseModel):
    model_config = ConfigDict(frozen=True)

    themes: list[ThemeConfig]

    @model_validator(mode="after")
    def validate_unique_theme_names(self) -> "StrategyUniverse":
        names = [theme.name for theme in self.themes]
        if len(set(names)) != len(names):
            raise ValueError("Strategy universe theme names must be unique.")
        return self

    def get_theme(self, name: str) -> ThemeConfig:
        normalized_name = name.strip().upper()
        for theme in self.themes:
            if theme.name == normalized_name:
                return theme
        raise KeyError(f"Unknown strategy theme: {normalized_name}")

    def themes_for_ticker(self, ticker: str) -> list[ThemeConfig]:
        normalized_ticker = ticker.strip().upper()
        return [theme for theme in self.themes if normalized_ticker in theme.tickers]

    def all_tickers(self) -> list[str]:
        return sorted({ticker for theme in self.themes for ticker in theme.tickers})

    def contains_ticker(self, ticker: str) -> bool:
        normalized_ticker = ticker.strip().upper()
        return any(normalized_ticker in theme.tickers for theme in self.themes)


class EarningsEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    earnings_date: date
    report_time: ReportTime
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list, exclude=True)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class EarningsCalendarEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    earnings_date: date | None
    report_time: ReportTime
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class EarningsCandidateDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    theme: str | None
    status: CandidateDetectionStatus
    earnings_date: date | None
    report_time: ReportTime
    reported_peers: list[str] = Field(default_factory=list)
    rejection_reasons: list[CandidateRejectionReason] = Field(default_factory=list)
    upcoming_event: EarningsCalendarEvent | None = Field(default=None, exclude=True)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class PeerResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    earnings_event: EarningsEvent
    price_reaction_pct: float | None = None
    guidance_signal: SignalValue = "unknown"
    theme_driver_signal: SignalValue = "unknown"
    source_urls: list[str] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)
    transcript_summary: TranscriptSummary | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class StrategySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    earnings_window_days: int = 1
    peer_result_window_days: int = 21
    min_reported_peers: int = 3
    positive_price_reaction_pct: float = 3.0
    negative_price_reaction_pct: float = -3.0
    min_positive_peer_ratio: float = 0.67
    min_average_peer_score: float = 2.0
    min_avg_daily_volume: int = 1_000_000
    max_target_runup_pct: float = 10.0
    max_options_bid_ask_spread_pct: float = 15.0
    min_option_open_interest: int = 100
    max_option_expiration_days_after_earnings: int = 14
    allow_stock_fallback: bool = True


class PeerScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    score: int
    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    missing_factors: list[str] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list, exclude=True)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class PeerSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    peer_scores: list[PeerScore] = Field(default_factory=list)
    average_peer_score: float
    positive_peer_count: int
    negative_peer_count: int
    positive_peer_ratio: float
    missing_data_count: int
    passes_thresholds: bool


class TechnicalIndicatorSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of: date
    rsi_14: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_histogram: float | None
    macd_state: MacdState
    vwap: float | None
    price_vs_vwap: PriceVsVwapState
    missing_fields: list[str] = Field(default_factory=list)
    source: str
    freshness: IndicatorFreshness
    source_citations: list[SourceCitation] = Field(default_factory=list, exclude=True)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("missing_fields")
    @classmethod
    def normalize_missing_fields(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            field_name = value.strip()
            if not field_name or field_name in seen:
                continue
            seen.add(field_name)
            normalized.append(field_name)
        return normalized

    @field_validator("source")
    @classmethod
    def require_source(cls, value: str) -> str:
        source = value.strip()
        if not source:
            raise ValueError("Indicator snapshot source is required.")
        return source

    @model_validator(mode="after")
    def validate_missing_indicator_values(self) -> "TechnicalIndicatorSnapshot":
        indicator_values = {
            "rsi_14": self.rsi_14,
            "macd_line": self.macd_line,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "vwap": self.vwap,
        }
        missing_fields = set(self.missing_fields)
        unlisted_missing_values = [
            field_name
            for field_name, value in indicator_values.items()
            if value is None and field_name not in missing_fields
        ]
        if unlisted_missing_values:
            fields = ", ".join(unlisted_missing_values)
            raise ValueError(
                f"Missing indicator values must be listed in missing_fields: {fields}"
            )
        return self


class DecisionAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    theme: str | None
    peer_scores: list[PeerScore] = Field(default_factory=list)
    thresholds: dict[str, float | int | bool]
    missing_peer_factor_count: int
    all_peer_data_missing: bool
    target_market_data_present: bool
    option_contract_count: int
    indicator_snapshot_present: bool = False
    indicator_missing_fields: list[str] = Field(default_factory=list)
    indicator_source: str | None = None
    indicator_freshness: IndicatorFreshness | None = None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class TargetMarketData(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    avg_daily_volume: int | None
    pre_earnings_runup_pct: float | None
    has_conflicting_news: bool = False
    has_invalidating_event: bool = False
    is_extremely_illiquid: bool = False
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class OptionContractSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType
    expiration_date: date
    bid: float | None
    ask: float | None
    open_interest: int | None
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("option_type", mode="before")
    @classmethod
    def normalize_option_type(cls, value: str) -> str:
        return value.strip().upper()


class TargetFilterDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    theme: str | None
    status: TargetFilterStatus
    recommended_expression: PreferredExpression
    selected_option: OptionContractSnapshot | None = None
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    warnings: list[RejectionReason] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("theme")
    @classmethod
    def normalize_theme(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class CandidateBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    theme: str
    earnings_date: date
    report_time: ReportTime
    direction: Literal["bullish"]
    peer_signal_score: float
    positive_peer_ratio: float
    reported_peers: list[str]
    peer_scores: list[PeerScore]
    main_thesis: str
    supporting_evidence: list[str]
    contradictions: list[str]
    recommended_expression: PreferredExpression
    technical_indicators: TechnicalIndicatorSnapshot | None = None
    strategy_status: StrategyStatus
    peer_summaries: list[TranscriptSummary] = Field(default_factory=list)
    source_citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("target", "theme")
    @classmethod
    def normalize_uppercase_fields(cls, value: str) -> str:
        return value.strip().upper()


class StrategyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: StrategyStatus
    candidate: CandidateBrief | None = None
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    rejection_details: list[RejectionDetail] = Field(default_factory=list)
    audit: DecisionAudit
    claude_analysis_allowed: bool
    audit_trail: DecisionAuditTrail = Field(
        default_factory=lambda: legacy_audit_trail(
            decision_type=DecisionType.STRATEGY_DECISION,
            decision_layer=DecisionLayer.SIGNAL,
        )
    )

    @model_validator(mode="before")
    @classmethod
    def add_legacy_audit_trail(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("audit_trail") is not None:
            return data

        audit_data = data.get("audit")
        target: str | None = None
        theme: str | None = None
        if isinstance(audit_data, DecisionAudit):
            target = audit_data.target
            theme = audit_data.theme
        elif isinstance(audit_data, dict):
            target = audit_data.get("target")
            theme = audit_data.get("theme")

        return {
            **data,
            "audit_trail": legacy_audit_trail(
                decision_type=DecisionType.STRATEGY_DECISION,
                decision_layer=DecisionLayer.SIGNAL,
                target=target,
                theme=theme,
            ),
        }

    @model_validator(mode="after")
    def validate_strategy_decision_contract(self) -> "StrategyDecision":
        if self.status == StrategyStatus.REJECTED_WITH_REASON:
            if self.candidate is not None:
                raise ValueError("Rejected strategy decisions must not include a candidate brief.")
            if not self.rejection_reasons:
                raise ValueError("Rejected strategy decisions must include rejection reasons.")
            if not self.rejection_details:
                raise ValueError("Rejected strategy decisions must include rejection details.")
            if self.claude_analysis_allowed:
                raise ValueError("Rejected strategy decisions cannot allow Claude analysis.")

        if self.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST:
            if self.candidate is None:
                raise ValueError("Candidate-ready decisions must include a candidate brief.")
            if self.rejection_reasons or self.rejection_details:
                raise ValueError("Candidate-ready decisions must not include rejection reasons.")
            if not self.claude_analysis_allowed:
                raise ValueError("Candidate-ready decisions must allow Claude analysis.")

        if self.status == StrategyStatus.NO_TRADE and self.claude_analysis_allowed:
            raise ValueError("No-trade decisions cannot allow Claude analysis.")

        return self


class StrategyThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    theme: str
    strategy_type: StrategyType
    direction: StrategyDirection
    status: ThesisStatus
    reported_peers: list[str]
    positive_peer_count: int
    minimum_peer_count: int
    shared_drivers: list[str]
    reason: str

    @field_validator("target", "theme")
    @classmethod
    def normalize_uppercase_fields(cls, value: str) -> str:
        return value.strip().upper()
