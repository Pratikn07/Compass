from __future__ import annotations

from math import isclose

from prescient.journal import DecisionType
from prescient.risk.audit import risk_audit_trail
from prescient.risk.models import (
    AccountSizePolicyDecision,
    AccountSizePolicyReason,
    AccountSizePolicySettings,
    AccountSizePolicyStatus,
    AccountSizeTier,
    AccountSnapshot,
    ExecutionMode,
    RiskSettings,
)


def evaluate_account_size_policy(
    account: AccountSnapshot | None,
    requested_mode: ExecutionMode | str | None = None,
    settings: AccountSizePolicySettings | None = None,
) -> AccountSizePolicyDecision:
    active_settings = settings or AccountSizePolicySettings()
    mode = _coerce_execution_mode(requested_mode)
    account_equity = account.account_equity if account is not None else None
    account_tier = _classify_account_tier(account_equity, active_settings)
    configured_trade_loss_pct = (
        active_settings.configured_trade_loss_pct
        if active_settings.configured_trade_loss_pct is not None
        else active_settings.tier_default_trade_loss_pct
    )
    recommended_risk_settings = RiskSettings(
        max_trade_loss_pct=active_settings.tier_default_trade_loss_pct
    )
    effective_risk_settings = RiskSettings(max_trade_loss_pct=configured_trade_loss_pct)
    recommended_loss_amount = _loss_amount(
        account_equity,
        active_settings.tier_default_trade_loss_pct,
    )
    absolute_loss_amount = _loss_amount(
        account_equity,
        active_settings.absolute_trade_loss_pct_ceiling,
    )
    reasons: list[AccountSizePolicyReason] = []

    if account_equity is None:
        reasons.append(AccountSizePolicyReason.ACCOUNT_EQUITY_MISSING)
    elif account_equity <= 0:
        reasons.append(AccountSizePolicyReason.ACCOUNT_EQUITY_INVALID)
    elif account_tier == AccountSizeTier.BELOW_SUPPORTED_TIER:
        reasons.append(AccountSizePolicyReason.ACCOUNT_BELOW_SUPPORTED_TIER)
    elif account_tier == AccountSizeTier.ABOVE_SUPPORTED_TIER:
        reasons.append(AccountSizePolicyReason.ACCOUNT_ABOVE_SUPPORTED_TIER)

    if _above(configured_trade_loss_pct, active_settings.tier_default_trade_loss_pct):
        reasons.append(AccountSizePolicyReason.RISK_CAP_ABOVE_TIER_DEFAULT)

    if _above(configured_trade_loss_pct, active_settings.absolute_trade_loss_pct_ceiling):
        reasons.append(AccountSizePolicyReason.RISK_CAP_ABOVE_ABSOLUTE_CEILING)

    status = _status_for(reasons)
    live_trading_eligible = status == AccountSizePolicyStatus.ELIGIBLE
    paper_trading_allowed = True
    propose_only_recommended = (
        status == AccountSizePolicyStatus.RESTRICTED
        and account_tier != AccountSizeTier.ABOVE_SUPPORTED_TIER
    )

    return AccountSizePolicyDecision(
        status=status,
        account_equity=account_equity,
        account_size_tier=account_tier,
        requested_mode=mode,
        recommended_max_trade_loss_pct=active_settings.tier_default_trade_loss_pct,
        absolute_max_trade_loss_pct=active_settings.absolute_trade_loss_pct_ceiling,
        recommended_max_trade_loss_amount=recommended_loss_amount,
        absolute_max_trade_loss_amount=absolute_loss_amount,
        recommended_risk_settings=recommended_risk_settings,
        effective_risk_settings=effective_risk_settings,
        live_trading_eligible=live_trading_eligible,
        paper_trading_allowed=paper_trading_allowed,
        propose_only_recommended=propose_only_recommended,
        reasons=reasons,
        review_flags=_review_flags(reasons),
        warnings=[],
        audit_trail=risk_audit_trail(
            decision_type=DecisionType.ACCOUNT_SIZE_POLICY,
            rule_name="account_size_policy",
            passed=status == AccountSizePolicyStatus.ELIGIBLE,
            reason=",".join(reason.value for reason in reasons) or None,
        ),
    )


def _classify_account_tier(
    account_equity: float | None,
    settings: AccountSizePolicySettings,
) -> AccountSizeTier | None:
    if account_equity is None or account_equity <= 0:
        return None

    if account_equity < settings.supported_min_equity:
        return AccountSizeTier.BELOW_SUPPORTED_TIER

    if account_equity > settings.supported_max_equity:
        return AccountSizeTier.ABOVE_SUPPORTED_TIER

    return AccountSizeTier.SUPPORTED_10K_25K


def _coerce_execution_mode(mode: ExecutionMode | str | None) -> ExecutionMode:
    if mode is None:
        return ExecutionMode.PROPOSE_ONLY

    if isinstance(mode, ExecutionMode):
        return mode

    return ExecutionMode(mode)


def _status_for(reasons: list[AccountSizePolicyReason]) -> AccountSizePolicyStatus:
    if any(
        reason
        in {
            AccountSizePolicyReason.ACCOUNT_EQUITY_MISSING,
            AccountSizePolicyReason.ACCOUNT_EQUITY_INVALID,
            AccountSizePolicyReason.ACCOUNT_BELOW_SUPPORTED_TIER,
            AccountSizePolicyReason.RISK_CAP_ABOVE_ABSOLUTE_CEILING,
        }
        for reason in reasons
    ):
        return AccountSizePolicyStatus.RESTRICTED

    if reasons:
        return AccountSizePolicyStatus.REVIEW_REQUIRED

    return AccountSizePolicyStatus.ELIGIBLE


def _review_flags(
    reasons: list[AccountSizePolicyReason],
) -> list[AccountSizePolicyReason]:
    return [
        reason
        for reason in reasons
        if reason
        in {
            AccountSizePolicyReason.ACCOUNT_ABOVE_SUPPORTED_TIER,
            AccountSizePolicyReason.RISK_CAP_ABOVE_TIER_DEFAULT,
            AccountSizePolicyReason.BROKER_DAY_TRADE_POLICY_UNVERIFIED,
        }
    ]


def _loss_amount(account_equity: float | None, pct: float) -> float | None:
    if account_equity is None or account_equity <= 0:
        return None

    return round(account_equity * pct, 2)


def _above(left: float, right: float) -> bool:
    return left > right and not isclose(left, right)
