from __future__ import annotations

from collections.abc import Callable
from datetime import date
from inspect import signature
from pathlib import Path

import pytest

from prescient.risk import (
    DailyRiskAction,
    ExecutionQualityRejectionReason,
    ExecutionQualitySettings,
    ExecutionQualityStatus,
    ExecutionQualityWarning,
    ExecutionQuoteSnapshot,
    MarketSessionSnapshot,
    MarketSessionStatus,
    RewardRiskProposal,
    TradeExpression,
    evaluate_execution_quality,
)


R3_7_PRD_PATH = Path(
    "docs/prd/03-risk-r3-7-liquid-market-hours-spread-reward-risk-prd.md"
)


def _regular_session(
    *,
    status: MarketSessionStatus = MarketSessionStatus.REGULAR_OPEN,
    is_halted: bool = False,
    minutes_to_close: int | None = 60,
) -> MarketSessionSnapshot:
    return MarketSessionSnapshot(
        market_date=date(2026, 6, 3),
        session_status=status,
        is_halted=is_halted,
        is_early_close=False,
        minutes_to_close=minutes_to_close,
    )


def _stock_quote(
    *,
    bid: float | None = 24.95,
    ask: float | None = 25.05,
    avg_daily_volume: int | None = 2_000_000,
    quote_age_seconds: int | None = 3,
) -> ExecutionQuoteSnapshot:
    return ExecutionQuoteSnapshot(
        target="ntnx",
        expression=TradeExpression.STOCK,
        bid=bid,
        ask=ask,
        last_price=25.0,
        avg_daily_volume=avg_daily_volume,
        quote_age_seconds=quote_age_seconds,
    )


def _option_quote(
    *,
    bid: float | None = 1.00,
    ask: float | None = 1.10,
    option_open_interest: int | None = 250,
    quote_age_seconds: int | None = 3,
) -> ExecutionQuoteSnapshot:
    return ExecutionQuoteSnapshot(
        target="ntnx",
        expression=TradeExpression.CALL_OPTION,
        bid=bid,
        ask=ask,
        last_price=1.05,
        avg_daily_volume=2_000_000,
        quote_age_seconds=quote_age_seconds,
        option_open_interest=option_open_interest,
    )


def _reward_risk(
    *,
    entry_price: float | None = 25.0,
    stop_price: float | None = 23.0,
    target_price: float | None = 29.0,
    expected_reward: float | None = None,
    maximum_loss: float | None = None,
) -> RewardRiskProposal:
    return RewardRiskProposal(
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        expected_reward=expected_reward,
        maximum_loss=maximum_loss,
    )


def test_r3_7_prd_is_saved_with_execution_quality_defaults_and_sources() -> None:
    prd = R3_7_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R3.7 Liquid Names, Market Hours, Spread, and Reward/Risk" in prd
    assert "min_reward_to_risk_ratio = 2.0" in prd
    assert "min_avg_daily_volume = 1_000_000" in prd
    assert "max_stock_bid_ask_spread_pct = 0.50" in prd
    assert "max_option_bid_ask_spread_pct = 15.0" in prd
    assert "https://www.nyse.com/trade/hours-calendars" in prd
    assert "https://www.nasdaq.com/market-activity" in prd
    assert "https://www.cboe.com/about/hours/us-options/" in prd


def test_allows_new_risk_stock_when_market_liquidity_spread_and_reward_risk_pass() -> None:
    decision = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )

    assert decision.status == ExecutionQualityStatus.ALLOWED
    assert decision.target == "NTNX"
    assert decision.expression == TradeExpression.STOCK
    assert decision.spread_pct == 0.4
    assert decision.reward_risk_ratio == 2.0
    assert decision.rejection_reasons == []
    assert decision.broker_execution_allowed_for_new_risk is True


def test_blocks_sessions_that_are_not_open_for_new_risk() -> None:
    decisions = [
        evaluate_execution_quality(
            action=DailyRiskAction.NEW_ENTRY,
            session=_regular_session(status=status),
            quote=_stock_quote(),
            reward_risk=_reward_risk(),
        )
        for status in [
            MarketSessionStatus.CLOSED,
            MarketSessionStatus.PRE_MARKET,
            MarketSessionStatus.AFTER_HOURS,
        ]
    ]
    unknown = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(status=MarketSessionStatus.UNKNOWN),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    halted_status = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(status=MarketSessionStatus.HALTED),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    halted_flag = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(is_halted=True),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    too_close_to_close = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(minutes_to_close=4),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )

    assert [decision.status for decision in decisions] == [
        ExecutionQualityStatus.BLOCKED,
        ExecutionQualityStatus.BLOCKED,
        ExecutionQualityStatus.BLOCKED,
    ]
    assert all(
        ExecutionQualityRejectionReason.OUTSIDE_REGULAR_MARKET_HOURS
        in decision.rejection_reasons
        for decision in decisions
    )
    assert unknown.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert unknown.rejection_reasons == [
        ExecutionQualityRejectionReason.MARKET_SESSION_UNKNOWN
    ]
    assert halted_status.status == ExecutionQualityStatus.BLOCKED
    assert halted_status.rejection_reasons == [
        ExecutionQualityRejectionReason.SYMBOL_HALTED
    ]
    assert halted_flag.status == ExecutionQualityStatus.BLOCKED
    assert halted_flag.rejection_reasons == [
        ExecutionQualityRejectionReason.SYMBOL_HALTED
    ]
    assert too_close_to_close.status == ExecutionQualityStatus.BLOCKED
    assert too_close_to_close.rejection_reasons == [
        ExecutionQualityRejectionReason.TOO_CLOSE_TO_MARKET_CLOSE
    ]


def test_missing_required_execution_inputs_are_not_evaluable() -> None:
    missing_session = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=None,
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    missing_quote = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=None,
        reward_risk=_reward_risk(),
    )
    missing_bid_ask = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(bid=None, ask=None),
        reward_risk=_reward_risk(),
    )
    stale_quote = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(quote_age_seconds=16),
        reward_risk=_reward_risk(),
    )
    missing_reward_risk = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=None,
    )

    assert missing_session.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert missing_session.rejection_reasons == [
        ExecutionQualityRejectionReason.MARKET_SESSION_MISSING
    ]
    assert missing_quote.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert missing_quote.rejection_reasons == [
        ExecutionQualityRejectionReason.QUOTE_MISSING
    ]
    assert missing_bid_ask.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert missing_bid_ask.rejection_reasons == [
        ExecutionQualityRejectionReason.BID_ASK_MISSING
    ]
    assert stale_quote.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert stale_quote.rejection_reasons == [
        ExecutionQualityRejectionReason.QUOTE_STALE
    ]
    assert missing_reward_risk.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert missing_reward_risk.rejection_reasons == [
        ExecutionQualityRejectionReason.REWARD_RISK_MISSING
    ]


def test_blocks_stock_when_spread_volume_or_reward_risk_fails() -> None:
    wide_spread = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(bid=24.00, ask=25.00),
        reward_risk=_reward_risk(),
    )
    low_volume = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(avg_daily_volume=999_999),
        reward_risk=_reward_risk(),
    )
    weak_reward_risk = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=_reward_risk(target_price=28.99),
    )

    assert wide_spread.status == ExecutionQualityStatus.BLOCKED
    assert wide_spread.rejection_reasons == [
        ExecutionQualityRejectionReason.STOCK_SPREAD_TOO_WIDE
    ]
    assert low_volume.status == ExecutionQualityStatus.BLOCKED
    assert low_volume.rejection_reasons == [
        ExecutionQualityRejectionReason.AVERAGE_VOLUME_TOO_LOW
    ]
    assert weak_reward_risk.status == ExecutionQualityStatus.BLOCKED
    assert weak_reward_risk.reward_risk_ratio == 1.99
    assert weak_reward_risk.rejection_reasons == [
        ExecutionQualityRejectionReason.REWARD_RISK_BELOW_MINIMUM
    ]


def test_allows_and_blocks_call_options_by_spread_and_open_interest() -> None:
    allowed = evaluate_execution_quality(
        action=DailyRiskAction.OPEN_OPTION_CONTRACT,
        session=_regular_session(),
        quote=_option_quote(),
        reward_risk=_reward_risk(expected_reward=300.0, maximum_loss=150.0),
    )
    wide_spread = evaluate_execution_quality(
        action=DailyRiskAction.OPEN_OPTION_CONTRACT,
        session=_regular_session(),
        quote=_option_quote(bid=1.00, ask=1.40),
        reward_risk=_reward_risk(expected_reward=300.0, maximum_loss=150.0),
    )
    missing_open_interest = evaluate_execution_quality(
        action=DailyRiskAction.OPEN_OPTION_CONTRACT,
        session=_regular_session(),
        quote=_option_quote(option_open_interest=None),
        reward_risk=_reward_risk(expected_reward=300.0, maximum_loss=150.0),
    )
    low_open_interest = evaluate_execution_quality(
        action=DailyRiskAction.OPEN_OPTION_CONTRACT,
        session=_regular_session(),
        quote=_option_quote(option_open_interest=99),
        reward_risk=_reward_risk(expected_reward=300.0, maximum_loss=150.0),
    )

    assert allowed.status == ExecutionQualityStatus.ALLOWED
    assert allowed.spread_pct == 9.52
    assert allowed.reward_risk_ratio == 2.0
    assert wide_spread.status == ExecutionQualityStatus.BLOCKED
    assert wide_spread.rejection_reasons == [
        ExecutionQualityRejectionReason.OPTION_SPREAD_TOO_WIDE
    ]
    assert missing_open_interest.status == ExecutionQualityStatus.NOT_EVALUABLE
    assert missing_open_interest.rejection_reasons == [
        ExecutionQualityRejectionReason.OPTION_OPEN_INTEREST_MISSING
    ]
    assert low_open_interest.status == ExecutionQualityStatus.BLOCKED
    assert low_open_interest.rejection_reasons == [
        ExecutionQualityRejectionReason.OPTION_OPEN_INTEREST_TOO_LOW
    ]


def test_risk_reducing_action_is_allowed_without_new_risk_checks() -> None:
    decision = evaluate_execution_quality(
        action=DailyRiskAction.EXIT_POSITION,
        session=None,
        quote=None,
        reward_risk=None,
    )

    assert decision.status == ExecutionQualityStatus.ALLOWED
    assert decision.allowed_actions == [
        DailyRiskAction.EXIT_POSITION,
        DailyRiskAction.REDUCE_POSITION,
        DailyRiskAction.CANCEL_ORDER,
        DailyRiskAction.RISK_REDUCING_ORDER,
    ]
    assert decision.blocked_actions == []
    assert decision.warnings == [
        ExecutionQualityWarning.RISK_REDUCING_ACTION_ALLOWED_WITHOUT_NEW_RISK_CHECKS
    ]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_identical_execution_quality_input_serializes_deterministically() -> None:
    first = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    second = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_execution_quality_output_is_journal_safe() -> None:
    decision = evaluate_execution_quality(
        action=DailyRiskAction.NEW_ENTRY,
        session=_regular_session(),
        quote=_stock_quote(),
        reward_risk=_reward_risk(),
    )
    serialized = decision.model_dump(mode="json")
    rendered = repr(serialized).lower()

    assert serialized["target"] == "NTNX"
    assert serialized["market_date"] == "2026-06-03"
    assert serialized["session_status"] == "regular_open"
    assert "credential" not in rendered
    assert "prompt" not in rendered
    assert "account_id" not in rendered
    assert "broker_order" not in rendered
    assert "broker_adapter" not in rendered
    assert "raw_payload" not in rendered


def test_execution_quality_accepts_no_claude_analyst_or_broker_parameter() -> None:
    quality_signature = signature(evaluate_execution_quality)

    assert list(quality_signature.parameters) == [
        "action",
        "session",
        "quote",
        "reward_risk",
        "settings",
    ]
    assert not any(
        unsafe_name in parameter_name
        for parameter_name in quality_signature.parameters
        for unsafe_name in ["claude", "analyst", "broker"]
    )


def test_invalid_execution_quality_settings_are_rejected() -> None:
    invalid_settings: list[Callable[[], ExecutionQualitySettings]] = [
        lambda: ExecutionQualitySettings(min_reward_to_risk_ratio=0),
        lambda: ExecutionQualitySettings(max_stock_bid_ask_spread_pct=0),
        lambda: ExecutionQualitySettings(max_option_bid_ask_spread_pct=0),
        lambda: ExecutionQualitySettings(min_avg_daily_volume=0),
        lambda: ExecutionQualitySettings(min_option_open_interest=0),
        lambda: ExecutionQualitySettings(max_quote_age_seconds=0),
        lambda: ExecutionQualitySettings(min_minutes_before_close_for_new_risk=-1),
    ]

    for build_settings in invalid_settings:
        with pytest.raises(ValueError):
            build_settings()
