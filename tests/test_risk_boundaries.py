from __future__ import annotations

import ast
import inspect
from pathlib import Path

from prescient.risk import (
    AccountSizePolicyReason,
    AccountSizePolicyStatus,
    AccountSnapshot,
    RiskDecisionStatus,
    RiskRejectionReason,
    RiskSettings,
    TradeExpression,
    TradeProposal,
    evaluate_account_size_policy,
    evaluate_trade_risk,
)


def test_risk_package_has_no_cold_path_broker_network_or_polling_imports() -> None:
    forbidden_roots = {
        "anthropic",
        "alpaca",
        "httpx",
        "requests",
        "prescient.analyst",
        "prescient.broker",
        "prescient.events",
        "prescient.runtime",
        "prescient.scheduler",
    }

    for path in Path("src/prescient/risk").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        imports.extend(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )

        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports a forbidden risk dependency: {imports}"


def test_risk_package_has_no_hidden_clock_sleep_or_polling_loop() -> None:
    forbidden_calls = {
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.sleep",
        "asyncio.sleep",
    }

    for path in Path("src/prescient/risk").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert "while True" not in source
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                assert call_name not in forbidden_calls, (
                    f"{path} uses hidden clock/sleep call {call_name}"
                )


def test_evaluate_trade_risk_accepts_no_claude_or_analyst_parameter() -> None:
    signature = inspect.signature(evaluate_trade_risk)

    assert list(signature.parameters) == ["account", "proposal", "settings"]
    assert not any(
        "claude" in parameter_name or "analyst" in parameter_name
        for parameter_name in signature.parameters
    )


def test_evaluate_account_size_policy_accepts_no_claude_or_broker_parameter() -> None:
    signature = inspect.signature(evaluate_account_size_policy)

    assert list(signature.parameters) == ["account", "requested_mode", "settings"]
    assert not any(
        unsafe in parameter_name
        for parameter_name in signature.parameters
        for unsafe in [
            "claude",
            "analyst",
            "broker",
            "runtime",
            "scheduler",
            "event",
            "http",
        ]
    )


def test_claude_like_unsafe_fields_cannot_override_rejected_risk_decision() -> None:
    rejected = evaluate_trade_risk(
        account=AccountSnapshot(account_equity=2_000.0),
        proposal=TradeProposal(
            target="NTNX",
            expression=TradeExpression.CALL_OPTION,
            entry_price=1.00,
            stop_price=None,
            contract_multiplier=100,
            minimum_quantity=1,
        ),
        settings=RiskSettings(max_trade_loss_pct=0.03),
    )
    claude_like_payload = {
        "recommendation": "go",
        "conviction_score": 100,
        "position_size": "25%",
        "order_quantity": 5,
        "broker_action": "buy",
        "risk_override": True,
        "execute_trade": True,
    }

    assert claude_like_payload["risk_override"] is True
    assert rejected.status == RiskDecisionStatus.REJECTED
    assert rejected.rejection_reasons == [
        RiskRejectionReason.SMALLEST_TRADE_EXCEEDS_CAP,
        RiskRejectionReason.MAX_TRADE_LOSS_EXCEEDED,
    ]
    assert rejected.broker_execution_allowed is False


def test_claude_like_unsafe_fields_cannot_override_account_policy() -> None:
    restricted = evaluate_account_size_policy(
        AccountSnapshot(account_equity=9_999.99),
        requested_mode="live",
    )
    claude_like_payload = {
        "recommendation": "go",
        "conviction_score": 100,
        "position_size": "25%",
        "order_quantity": 5,
        "broker_action": "buy",
        "risk_override": True,
        "execute_trade": True,
    }

    assert claude_like_payload["risk_override"] is True
    assert restricted.status == AccountSizePolicyStatus.RESTRICTED
    assert restricted.reasons == [
        AccountSizePolicyReason.ACCOUNT_BELOW_SUPPORTED_TIER
    ]
    assert restricted.live_trading_eligible is False


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
