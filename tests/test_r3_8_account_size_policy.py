from __future__ import annotations

from prescient.risk import (
    AccountSizePolicyReason,
    AccountSizePolicySettings,
    AccountSizePolicyStatus,
    AccountSizeTier,
    AccountSnapshot,
    ExecutionMode,
    RiskSettings,
    evaluate_account_size_policy,
)


def _account(equity: float | None) -> AccountSnapshot:
    return AccountSnapshot(account_equity=equity)


def test_ten_thousand_account_is_supported_tier_with_one_percent_default() -> None:
    decision = evaluate_account_size_policy(_account(10_000.0))

    assert decision.status == AccountSizePolicyStatus.ELIGIBLE
    assert decision.account_size_tier == AccountSizeTier.SUPPORTED_10K_25K
    assert decision.account_equity == 10_000.0
    assert decision.recommended_max_trade_loss_pct == 0.01
    assert decision.recommended_max_trade_loss_amount == 100.0
    assert decision.absolute_max_trade_loss_pct == 0.03
    assert decision.absolute_max_trade_loss_amount == 300.0
    assert decision.live_trading_eligible is True
    assert decision.paper_trading_allowed is True
    assert decision.propose_only_recommended is False
    assert decision.reasons == []


def test_twenty_five_thousand_account_is_supported_tier_boundary() -> None:
    decision = evaluate_account_size_policy(_account(25_000.0))

    assert decision.status == AccountSizePolicyStatus.ELIGIBLE
    assert decision.account_size_tier == AccountSizeTier.SUPPORTED_10K_25K
    assert decision.recommended_max_trade_loss_amount == 250.0
    assert decision.absolute_max_trade_loss_amount == 750.0
    assert decision.live_trading_eligible is True


def test_account_below_supported_tier_is_restricted_from_live_but_allows_paper() -> None:
    decision = evaluate_account_size_policy(
        _account(9_999.99),
        requested_mode=ExecutionMode.LIVE,
    )

    assert decision.status == AccountSizePolicyStatus.RESTRICTED
    assert decision.account_size_tier == AccountSizeTier.BELOW_SUPPORTED_TIER
    assert decision.live_trading_eligible is False
    assert decision.paper_trading_allowed is True
    assert decision.propose_only_recommended is True
    assert decision.reasons == [
        AccountSizePolicyReason.ACCOUNT_BELOW_SUPPORTED_TIER
    ]


def test_account_above_supported_tier_requires_review_without_higher_limits() -> None:
    decision = evaluate_account_size_policy(_account(25_000.01))

    assert decision.status == AccountSizePolicyStatus.REVIEW_REQUIRED
    assert decision.account_size_tier == AccountSizeTier.ABOVE_SUPPORTED_TIER
    assert decision.live_trading_eligible is False
    assert decision.paper_trading_allowed is True
    assert decision.propose_only_recommended is False
    assert decision.recommended_max_trade_loss_pct == 0.01
    assert decision.absolute_max_trade_loss_pct == 0.03
    assert decision.reasons == [
        AccountSizePolicyReason.ACCOUNT_ABOVE_SUPPORTED_TIER
    ]


def test_three_percent_cap_is_allowed_only_with_review_reason() -> None:
    decision = evaluate_account_size_policy(
        _account(10_000.0),
        settings=AccountSizePolicySettings(configured_trade_loss_pct=0.03),
    )

    assert decision.status == AccountSizePolicyStatus.REVIEW_REQUIRED
    assert decision.account_size_tier == AccountSizeTier.SUPPORTED_10K_25K
    assert decision.live_trading_eligible is False
    assert decision.recommended_risk_settings == RiskSettings(max_trade_loss_pct=0.01)
    assert decision.effective_risk_settings == RiskSettings(max_trade_loss_pct=0.03)
    assert decision.reasons == [
        AccountSizePolicyReason.RISK_CAP_ABOVE_TIER_DEFAULT
    ]


def test_cap_above_three_percent_is_restricted() -> None:
    decision = evaluate_account_size_policy(
        _account(10_000.0),
        settings=AccountSizePolicySettings(configured_trade_loss_pct=0.031),
    )

    assert decision.status == AccountSizePolicyStatus.RESTRICTED
    assert decision.live_trading_eligible is False
    assert decision.reasons == [
        AccountSizePolicyReason.RISK_CAP_ABOVE_TIER_DEFAULT,
        AccountSizePolicyReason.RISK_CAP_ABOVE_ABSOLUTE_CEILING,
    ]


def test_missing_zero_and_negative_equity_fail_closed() -> None:
    missing_account = evaluate_account_size_policy(None)
    missing_equity = evaluate_account_size_policy(_account(None))
    zero_equity = evaluate_account_size_policy(_account(0.0))
    negative_equity = evaluate_account_size_policy(_account(-1.0))

    assert missing_account.status == AccountSizePolicyStatus.RESTRICTED
    assert missing_account.reasons == [AccountSizePolicyReason.ACCOUNT_EQUITY_MISSING]
    assert missing_equity.status == AccountSizePolicyStatus.RESTRICTED
    assert missing_equity.reasons == [AccountSizePolicyReason.ACCOUNT_EQUITY_MISSING]
    assert zero_equity.status == AccountSizePolicyStatus.RESTRICTED
    assert zero_equity.reasons == [AccountSizePolicyReason.ACCOUNT_EQUITY_INVALID]
    assert negative_equity.status == AccountSizePolicyStatus.RESTRICTED
    assert negative_equity.reasons == [AccountSizePolicyReason.ACCOUNT_EQUITY_INVALID]

    for decision in [missing_account, missing_equity, zero_equity, negative_equity]:
        assert decision.live_trading_eligible is False
        assert decision.paper_trading_allowed is True
        assert decision.propose_only_recommended is True


def test_requested_modes_are_respected_for_below_tier_accounts() -> None:
    paper = evaluate_account_size_policy(_account(9_000.0), requested_mode="paper")
    propose_only = evaluate_account_size_policy(
        _account(9_000.0),
        requested_mode=ExecutionMode.PROPOSE_ONLY,
    )

    assert paper.requested_mode == ExecutionMode.PAPER
    assert paper.status == AccountSizePolicyStatus.RESTRICTED
    assert paper.paper_trading_allowed is True
    assert paper.live_trading_eligible is False
    assert propose_only.requested_mode == ExecutionMode.PROPOSE_ONLY
    assert propose_only.propose_only_recommended is True
    assert propose_only.paper_trading_allowed is True


def test_custom_supported_tier_settings_are_deterministic() -> None:
    settings = AccountSizePolicySettings(
        supported_min_equity=15_000.0,
        supported_max_equity=30_000.0,
        tier_default_trade_loss_pct=0.005,
        absolute_trade_loss_pct_ceiling=0.02,
    )

    decision = evaluate_account_size_policy(
        _account(15_000.0),
        settings=settings,
    )

    assert decision.status == AccountSizePolicyStatus.ELIGIBLE
    assert decision.account_size_tier == AccountSizeTier.SUPPORTED_10K_25K
    assert decision.recommended_max_trade_loss_pct == 0.005
    assert decision.recommended_max_trade_loss_amount == 75.0
    assert decision.absolute_max_trade_loss_pct == 0.02
    assert decision.absolute_max_trade_loss_amount == 300.0


def test_identical_input_produces_identical_serialized_output() -> None:
    first = evaluate_account_size_policy(
        _account(10_000.0),
        requested_mode=ExecutionMode.LIVE,
    )
    second = evaluate_account_size_policy(
        _account(10_000.0),
        requested_mode=ExecutionMode.LIVE,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
