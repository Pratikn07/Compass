from __future__ import annotations

import pytest

from prescient.signal.strategy_types import (
    DEFAULT_STRATEGY_TYPE,
    StrategySupportStatus,
    StrategyType,
    coerce_strategy_type,
    get_strategy_metadata,
    is_strategy_active,
)


def test_only_bullish_earnings_readthrough_is_active() -> None:
    active_strategies = [
        strategy_type
        for strategy_type in StrategyType
        if get_strategy_metadata(strategy_type).status == StrategySupportStatus.ACTIVE
    ]

    assert active_strategies == [StrategyType.BULLISH_EARNINGS_READTHROUGH]
    assert DEFAULT_STRATEGY_TYPE == StrategyType.BULLISH_EARNINGS_READTHROUGH


def test_future_prd_strategy_types_exist_as_planned_metadata() -> None:
    planned_strategies = {
        StrategyType.BEARISH_EARNINGS_READTHROUGH,
        StrategyType.POST_EARNINGS_DRIFT,
        StrategyType.ANALYST_UPGRADE_MOMENTUM,
        StrategyType.SECTOR_BASKET,
        StrategyType.MEAN_REVERSION,
    }

    for strategy_type in planned_strategies:
        metadata = get_strategy_metadata(strategy_type)
        assert metadata.strategy_type == strategy_type
        assert metadata.status == StrategySupportStatus.PLANNED
        assert metadata.display_name
        assert metadata.description


def test_coerce_strategy_type_accepts_enum_and_valid_string() -> None:
    assert (
        coerce_strategy_type(StrategyType.BULLISH_EARNINGS_READTHROUGH)
        == StrategyType.BULLISH_EARNINGS_READTHROUGH
    )
    assert (
        coerce_strategy_type("bullish_earnings_readthrough")
        == StrategyType.BULLISH_EARNINGS_READTHROUGH
    )


def test_coerce_strategy_type_rejects_unknown_string() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy type: day_trade_breakout"):
        coerce_strategy_type("day_trade_breakout")


def test_get_strategy_metadata_returns_stable_bullish_metadata() -> None:
    metadata = get_strategy_metadata(StrategyType.BULLISH_EARNINGS_READTHROUGH)

    assert metadata.display_name == "Bullish Earnings Read-Through"
    assert metadata.status == StrategySupportStatus.ACTIVE
    assert metadata.direction == "bullish"
    assert metadata.preferred_expression == "CALL_OPTION"
    assert metadata.description == (
        "Flags upcoming earnings candidates when enough same-theme peers have already "
        "reported positive results and theme-driver evidence."
    )


def test_is_strategy_active_accepts_enum_and_string() -> None:
    assert is_strategy_active(StrategyType.BULLISH_EARNINGS_READTHROUGH) is True
    assert is_strategy_active("bullish_earnings_readthrough") is True
    assert is_strategy_active(StrategyType.POST_EARNINGS_DRIFT) is False
