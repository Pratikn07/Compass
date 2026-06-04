from __future__ import annotations

from datetime import date
from inspect import signature
from pathlib import Path

from prescient.risk import (
    DailyHaltReason,
    DailyHaltSettings,
    DailyHaltStatus,
    DailyRiskAction,
    DailyRiskState,
    evaluate_daily_halt,
)


R3_4_PRD_PATH = Path(
    "docs/prd/03-risk-r3-4-daily-loss-stop-halt-after-too-many-losses-prd.md"
)


def _state(
    *,
    account_equity: float | None = 5_000.0,
    trading_day: date | None = date(2026, 6, 3),
    realized_pnl: float | None = 0.0,
    losing_trade_count: int | None = 0,
) -> DailyRiskState:
    return DailyRiskState(
        account_equity=account_equity,
        trading_day=trading_day,
        realized_pnl=realized_pnl,
        losing_trade_count=losing_trade_count,
    )


def test_r3_4_prd_is_saved_with_daily_halt_defaults() -> None:
    prd = R3_4_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R3.4 Daily Loss Stop / Halt After Too Many Losses" in prd
    assert "Daily realized-loss cap: `5%` of account equity." in prd
    assert "Max losing trades per day: `2`." in prd
    assert "PnL basis: realized closed-trade P&L only." in prd


def test_five_thousand_account_halts_at_five_percent_realized_loss() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=-250.0, losing_trade_count=1)
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.account_equity == 5_000.0
    assert decision.max_daily_loss_pct == 0.05
    assert decision.max_daily_loss_amount == 250.0
    assert decision.realized_pnl == -250.0
    assert decision.halt_reasons == [DailyHaltReason.DAILY_LOSS_LIMIT_EXCEEDED]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_two_thousand_account_halts_at_five_percent_realized_loss() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=2_000.0, realized_pnl=-100.0, losing_trade_count=1)
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.max_daily_loss_amount == 100.0
    assert decision.halt_reasons == [DailyHaltReason.DAILY_LOSS_LIMIT_EXCEEDED]


def test_second_losing_trade_halts_even_below_loss_cap() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=-50.0, losing_trade_count=2)
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.max_daily_loss_amount == 250.0
    assert decision.halt_reasons == [DailyHaltReason.TOO_MANY_LOSING_TRADES]


def test_positive_or_flat_pnl_with_fewer_than_two_losses_allows_new_risk() -> None:
    positive = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=25.0, losing_trade_count=1)
    )
    flat = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=0.0, losing_trade_count=0)
    )

    assert positive.status == DailyHaltStatus.ALLOWED
    assert positive.halt_reasons == []
    assert positive.blocked_actions == []
    assert positive.broker_execution_allowed_for_new_risk is True
    assert flat.status == DailyHaltStatus.ALLOWED
    assert flat.broker_execution_allowed_for_new_risk is True


def test_missing_required_daily_state_fails_closed() -> None:
    decision = evaluate_daily_halt(
        _state(
            account_equity=None,
            trading_day=None,
            realized_pnl=None,
            losing_trade_count=None,
        )
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.max_daily_loss_amount is None
    assert decision.halt_reasons == [
        DailyHaltReason.ACCOUNT_EQUITY_MISSING,
        DailyHaltReason.TRADING_DAY_MISSING,
        DailyHaltReason.DAILY_PNL_MISSING,
        DailyHaltReason.LOSING_TRADE_COUNT_MISSING,
    ]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_halted_decision_blocks_new_risk_but_allows_defensive_actions() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=-250.0, losing_trade_count=1)
    )

    assert decision.blocked_actions == [
        DailyRiskAction.NEW_ENTRY,
        DailyRiskAction.ADD_TO_POSITION,
        DailyRiskAction.OPEN_OPTION_CONTRACT,
        DailyRiskAction.RISK_INCREASING_REPLACEMENT_ORDER,
    ]
    assert decision.allowed_actions == [
        DailyRiskAction.EXIT_POSITION,
        DailyRiskAction.REDUCE_POSITION,
        DailyRiskAction.CANCEL_ORDER,
        DailyRiskAction.RISK_REDUCING_ORDER,
    ]


def test_custom_daily_halt_settings_are_applied() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=-150.0, losing_trade_count=1),
        settings=DailyHaltSettings(
            max_daily_realized_loss_pct=0.03,
            max_losing_trades_per_day=3,
        ),
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.max_daily_loss_pct == 0.03
    assert decision.max_daily_loss_amount == 150.0
    assert decision.halt_reasons == [DailyHaltReason.DAILY_LOSS_LIMIT_EXCEEDED]


def test_prior_halt_reasons_are_preserved_and_keep_account_halted() -> None:
    decision = evaluate_daily_halt(
        DailyRiskState(
            account_equity=5_000.0,
            trading_day=date(2026, 6, 3),
            realized_pnl=25.0,
            losing_trade_count=0,
            prior_halt_reasons=[DailyHaltReason.TOO_MANY_LOSING_TRADES],
        )
    )

    assert decision.status == DailyHaltStatus.HALTED
    assert decision.halt_reasons == [DailyHaltReason.TOO_MANY_LOSING_TRADES]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_claude_output_cannot_remove_halt_or_approve_new_risk() -> None:
    decision = evaluate_daily_halt(
        _state(account_equity=5_000.0, realized_pnl=-250.0, losing_trade_count=1)
    )
    claude_like_payload = {
        "recommendation": "go",
        "conviction_score": 100,
        "risk_override": True,
        "execute_trade": True,
    }

    assert claude_like_payload["risk_override"] is True
    assert decision.status == DailyHaltStatus.HALTED
    assert decision.halt_reasons == [DailyHaltReason.DAILY_LOSS_LIMIT_EXCEEDED]
    assert decision.broker_execution_allowed_for_new_risk is False


def test_evaluate_daily_halt_accepts_no_claude_or_broker_parameter() -> None:
    daily_signature = signature(evaluate_daily_halt)

    assert list(daily_signature.parameters) == ["state", "settings"]
    assert not any(
        unsafe_name in parameter_name
        for parameter_name in daily_signature.parameters
        for unsafe_name in ["claude", "analyst", "broker"]
    )


def test_identical_daily_halt_input_serializes_deterministically() -> None:
    state = _state(account_equity=5_000.0, realized_pnl=-50.0, losing_trade_count=2)

    first = evaluate_daily_halt(state)
    second = evaluate_daily_halt(state)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
