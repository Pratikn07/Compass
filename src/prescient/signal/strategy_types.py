from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


StrategyDirection = Literal["bullish", "bearish", "neutral"]
PreferredExpression = Literal["CALL_OPTION", "PUT_OPTION", "STOCK", "BASKET", "NONE"]


class StrategyType(StrEnum):
    BULLISH_EARNINGS_READTHROUGH = "bullish_earnings_readthrough"
    BEARISH_EARNINGS_READTHROUGH = "bearish_earnings_readthrough"
    POST_EARNINGS_DRIFT = "post_earnings_drift"
    ANALYST_UPGRADE_MOMENTUM = "analyst_upgrade_momentum"
    SECTOR_BASKET = "sector_basket"
    MEAN_REVERSION = "mean_reversion"


class StrategySupportStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"


class StrategyMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_type: StrategyType
    display_name: str
    status: StrategySupportStatus
    direction: StrategyDirection
    preferred_expression: PreferredExpression
    description: str


DEFAULT_STRATEGY_TYPE = StrategyType.BULLISH_EARNINGS_READTHROUGH


_STRATEGY_METADATA: dict[StrategyType, StrategyMetadata] = {
    StrategyType.BULLISH_EARNINGS_READTHROUGH: StrategyMetadata(
        strategy_type=StrategyType.BULLISH_EARNINGS_READTHROUGH,
        display_name="Bullish Earnings Read-Through",
        status=StrategySupportStatus.ACTIVE,
        direction="bullish",
        preferred_expression="CALL_OPTION",
        description=(
            "Flags upcoming earnings candidates when enough same-theme peers have already "
            "reported positive results and theme-driver evidence."
        ),
    ),
    StrategyType.BEARISH_EARNINGS_READTHROUGH: StrategyMetadata(
        strategy_type=StrategyType.BEARISH_EARNINGS_READTHROUGH,
        display_name="Bearish Earnings Read-Through",
        status=StrategySupportStatus.PLANNED,
        direction="bearish",
        preferred_expression="PUT_OPTION",
        description=(
            "Flags upcoming earnings candidates when enough same-theme peers have already "
            "reported negative results or negative guidance."
        ),
    ),
    StrategyType.POST_EARNINGS_DRIFT: StrategyMetadata(
        strategy_type=StrategyType.POST_EARNINGS_DRIFT,
        display_name="Post-Earnings Drift",
        status=StrategySupportStatus.PLANNED,
        direction="neutral",
        preferred_expression="STOCK",
        description=(
            "Tracks continuation setups after earnings when price and volume confirm a "
            "persistent post-report move."
        ),
    ),
    StrategyType.ANALYST_UPGRADE_MOMENTUM: StrategyMetadata(
        strategy_type=StrategyType.ANALYST_UPGRADE_MOMENTUM,
        display_name="Analyst Upgrade Momentum",
        status=StrategySupportStatus.PLANNED,
        direction="bullish",
        preferred_expression="CALL_OPTION",
        description=(
            "Tracks setups where analyst upgrades or target-price revisions reinforce an "
            "earnings or sector momentum thesis."
        ),
    ),
    StrategyType.SECTOR_BASKET: StrategyMetadata(
        strategy_type=StrategyType.SECTOR_BASKET,
        display_name="Sector Basket",
        status=StrategySupportStatus.PLANNED,
        direction="neutral",
        preferred_expression="BASKET",
        description=(
            "Builds a diversified expression across multiple tickers in a theme instead of "
            "a single-name earnings trade."
        ),
    ),
    StrategyType.MEAN_REVERSION: StrategyMetadata(
        strategy_type=StrategyType.MEAN_REVERSION,
        display_name="Mean Reversion",
        status=StrategySupportStatus.PLANNED,
        direction="neutral",
        preferred_expression="STOCK",
        description=(
            "Tracks reversal setups after overextended price moves when trend and liquidity "
            "filters support a mean-reversion thesis."
        ),
    ),
}


def coerce_strategy_type(strategy_type: StrategyType | str) -> StrategyType:
    if isinstance(strategy_type, StrategyType):
        return strategy_type

    try:
        return StrategyType(strategy_type)
    except ValueError as exc:
        raise ValueError(f"Unsupported strategy type: {strategy_type}") from exc


def get_strategy_metadata(strategy_type: StrategyType | str) -> StrategyMetadata:
    return _STRATEGY_METADATA[coerce_strategy_type(strategy_type)]


def is_strategy_active(strategy_type: StrategyType | str) -> bool:
    return get_strategy_metadata(strategy_type).status == StrategySupportStatus.ACTIVE
