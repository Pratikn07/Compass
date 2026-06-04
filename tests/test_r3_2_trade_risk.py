from __future__ import annotations

from prescient.risk import (
    AccountSnapshot,
    RiskDecisionStatus,
    RiskRejectionReason,
    RiskReviewFlag,
    RiskSettings,
    TradeExpression,
    TradeProposal,
    evaluate_trade_risk,
)


def _account(equity: float | None = 10_000.0) -> AccountSnapshot:
    return AccountSnapshot(account_equity=equity)


def _stock_proposal(
    *,
    entry_price: float | None = 25.0,
    stop_price: float | None = 23.0,
    minimum_quantity: int = 1,
) -> TradeProposal:
    return TradeProposal(
        target="ntnx",
        expression=TradeExpression.STOCK,
        entry_price=entry_price,
        stop_price=stop_price,
        minimum_quantity=minimum_quantity,
    )


def _call_proposal(
    *,
    entry_price: float | None = 1.00,
    stop_price: float | None = None,
    contract_multiplier: int | None = 100,
    minimum_quantity: int = 1,
) -> TradeProposal:
    return TradeProposal(
        target="ntnx",
        expression=TradeExpression.CALL_OPTION,
        entry_price=entry_price,
        stop_price=stop_price,
        contract_multiplier=contract_multiplier,
        minimum_quantity=minimum_quantity,
    )


def test_two_thousand_account_at_three_percent_allows_sixty_dollars_loss() -> None:
    decision = evaluate_trade_risk(
        account=_account(2_000.0),
        proposal=_call_proposal(entry_price=0.50),
    )

    assert decision.status == RiskDecisionStatus.REVIEW_REQUIRED
    assert decision.target == "NTNX"
    assert decision.max_trade_loss_pct == 0.03
    assert decision.max_allowed_loss == 60.0
    assert decision.unit_max_loss == 50.0
    assert decision.approved_quantity == 1
    assert decision.projected_max_loss == 50.0
    assert decision.broker_execution_allowed is False
    assert RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW in decision.review_flags
    assert RiskReviewFlag.SMALL_ACCOUNT in decision.review_flags
    assert RiskReviewFlag.PROPOSE_ONLY_RECOMMENDED in decision.review_flags


def test_five_thousand_account_at_three_percent_allows_one_hundred_fifty_loss() -> None:
    decision = evaluate_trade_risk(
        account=_account(5_000.0),
        proposal=_call_proposal(entry_price=1.50),
    )

    assert decision.status == RiskDecisionStatus.REVIEW_REQUIRED
    assert decision.max_allowed_loss == 150.0
    assert decision.unit_max_loss == 150.0
    assert decision.approved_quantity == 1
    assert decision.projected_max_loss == 150.0
    assert RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW in decision.review_flags
    assert RiskReviewFlag.SMALL_ACCOUNT in decision.review_flags
    assert RiskReviewFlag.PROPOSE_ONLY_RECOMMENDED in decision.review_flags


def test_lower_cap_can_approve_without_three_percent_review_flag() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_stock_proposal(entry_price=25.0, stop_price=23.0),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.max_allowed_loss == 100.0
    assert decision.unit_max_loss == 2.0
    assert decision.approved_quantity == 50
    assert decision.projected_max_loss == 100.0
    assert decision.rejection_reasons == []
    assert RiskReviewFlag.THREE_PERCENT_CAP_REQUIRES_REVIEW not in decision.review_flags
    assert decision.broker_execution_allowed is True


def test_cap_above_three_percent_is_rejected_with_stable_reason() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.031),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert decision.rejection_reasons == [
        RiskRejectionReason.RISK_CAP_ABOVE_ALLOWED_CEILING
    ]
    assert decision.broker_execution_allowed is False


def test_stock_sizing_rounds_down_by_defined_stop_loss() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_stock_proposal(entry_price=25.0, stop_price=22.0),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.max_allowed_loss == 100.0
    assert decision.unit_max_loss == 3.0
    assert decision.approved_quantity == 33
    assert decision.projected_max_loss == 99.0


def test_stock_without_stop_is_rejected() -> None:
    decision = evaluate_trade_risk(
        account=_account(),
        proposal=_stock_proposal(stop_price=None),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert decision.rejection_reasons == [RiskRejectionReason.STOP_PRICE_MISSING]
    assert decision.unit_max_loss is None
    assert decision.approved_quantity == 0


def test_stock_with_stop_at_or_above_entry_is_not_computable() -> None:
    decision = evaluate_trade_risk(
        account=_account(),
        proposal=_stock_proposal(entry_price=25.0, stop_price=25.0),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert decision.rejection_reasons == [RiskRejectionReason.MAX_LOSS_NOT_COMPUTABLE]
    assert decision.unit_max_loss is None


def test_option_without_stop_uses_full_premium_risk() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_call_proposal(entry_price=0.75, stop_price=None),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.max_allowed_loss == 100.0
    assert decision.unit_max_loss == 75.0
    assert decision.approved_quantity == 1
    assert decision.projected_max_loss == 75.0


def test_option_with_stop_uses_premium_to_stop_risk() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_call_proposal(entry_price=1.20, stop_price=0.70),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.max_allowed_loss == 100.0
    assert decision.unit_max_loss == 50.0
    assert decision.approved_quantity == 2
    assert decision.projected_max_loss == 100.0


def test_one_option_contract_exceeding_cap_is_rejected() -> None:
    decision = evaluate_trade_risk(
        account=_account(2_000.0),
        proposal=_call_proposal(entry_price=1.00),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert decision.max_allowed_loss == 60.0
    assert decision.unit_max_loss == 100.0
    assert decision.approved_quantity == 0
    assert decision.rejection_reasons == [
        RiskRejectionReason.SMALLEST_TRADE_EXCEEDS_CAP,
        RiskRejectionReason.MAX_TRADE_LOSS_EXCEEDED,
    ]


def test_option_contract_near_cap_is_review_required() -> None:
    decision = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_call_proposal(entry_price=0.85),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert decision.status == RiskDecisionStatus.REVIEW_REQUIRED
    assert decision.max_allowed_loss == 100.0
    assert decision.unit_max_loss == 85.0
    assert decision.approved_quantity == 1
    assert RiskReviewFlag.OPTIONS_CONTRACT_NEAR_CAP in decision.review_flags
    assert decision.broker_execution_allowed is False


def test_invalid_or_missing_account_data_returns_required_reason() -> None:
    missing_account = evaluate_trade_risk(
        account=None,
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )
    missing_equity = evaluate_trade_risk(
        account=_account(None),
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )
    too_small = evaluate_trade_risk(
        account=_account(0.0),
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert missing_account.rejection_reasons == [
        RiskRejectionReason.ACCOUNT_EQUITY_MISSING
    ]
    assert missing_equity.rejection_reasons == [
        RiskRejectionReason.ACCOUNT_EQUITY_MISSING
    ]
    assert too_small.rejection_reasons == [RiskRejectionReason.ACCOUNT_EQUITY_TOO_SMALL]


def test_invalid_trade_inputs_return_required_reasons() -> None:
    missing_entry = evaluate_trade_risk(
        account=_account(),
        proposal=_stock_proposal(entry_price=None),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )
    invalid_quantity = evaluate_trade_risk(
        account=_account(),
        proposal=_stock_proposal(minimum_quantity=0),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )
    invalid_multiplier = evaluate_trade_risk(
        account=_account(),
        proposal=_call_proposal(contract_multiplier=0),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert missing_entry.rejection_reasons == [RiskRejectionReason.ENTRY_PRICE_MISSING]
    assert invalid_quantity.rejection_reasons == [RiskRejectionReason.INVALID_QUANTITY]
    assert invalid_multiplier.rejection_reasons == [
        RiskRejectionReason.INVALID_CONTRACT_MULTIPLIER
    ]


def test_identical_input_produces_identical_serialized_output() -> None:
    first = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )
    second = evaluate_trade_risk(
        account=_account(10_000.0),
        proposal=_stock_proposal(),
        settings=RiskSettings(max_trade_loss_pct=0.01),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
