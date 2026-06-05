from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OptionType = Literal["CALL", "PUT"]


def _norm_ticker(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("Ticker must not be empty.")
    return cleaned


class PredictionDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


class Prediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    direction: PredictionDirection
    predicted_move_pct: float
    confidence: float = Field(ge=0.0, le=1.0)
    source: str

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class OptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    option_type: OptionType
    strike: float
    expiration_date: date
    quote_date: date
    bid: float | None
    ask: float | None
    open_interest: int | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0


class ImpliedMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    underlying_price: float
    straddle_price: float
    implied_move_pct: float  # always positive (+/-)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class RealizedMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    pre_report_close: float
    post_report_close: float
    realized_move_pct: float  # signed


class OptionPnl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_premium: float
    exit_value: float
    cost_haircut: float
    net_pnl: float
    return_pct: float


class EventContext(BaseModel):
    """Everything knowable the day BEFORE a target reports, plus the realized
    outcome looked up from history. The scorer treats the realized fields as
    ground truth; strategies must only read the as-of fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    earnings_date: date
    as_of_date: date  # last trading day strictly before earnings_date
    underlying_price: float
    atm_call: OptionQuote | None = None
    atm_put: OptionQuote | None = None
    peer_eps_surprises: dict[str, float] = Field(default_factory=dict)
    peer_stock_reactions: dict[str, float] = Field(default_factory=dict)
    realized_move: RealizedMove | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class EventScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    source: str
    evaluable: bool
    not_evaluable_reason: str | None = None
    direction_correct: bool | None = None
    beat_implied: bool | None = None
    implied_move_pct: float | None = None
    realized_move_pct: float | None = None
    option_pnl: OptionPnl | None = None
    confidence: float | None = None


class SampleSizeVerdict(StrEnum):
    TOO_FEW = "too_few"          # < 30 evaluable events
    SUGGESTIVE = "suggestive"    # 30-149
    MODERATE = "moderate"        # 150-499
    STRONG = "strong"            # >= 500


class StrategyScorecard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    events_total: int
    events_evaluable: int
    directional_hit_rate: float | None = None
    beat_implied_rate: float | None = None
    average_option_return_pct: float | None = None
    high_confidence_hit_rate: float | None = None
    sample_size_verdict: SampleSizeVerdict
    survived: bool | None = None  # set by the runner after baseline comparison
    notes: list[str] = Field(default_factory=list)
