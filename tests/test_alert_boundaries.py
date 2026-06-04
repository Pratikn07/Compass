from __future__ import annotations

import ast
from datetime import UTC, date, datetime
from pathlib import Path

from prescient.alerts import (
    InMemoryNotificationAdapter,
    NotificationChannel,
    TradeNotificationSettings,
    build_trade_notification_request,
    dispatch_trade_notification,
)
from prescient.broker import BrokerOrderStatus, OrderExecutionResult
from prescient.risk import RiskOrderProposal
from prescient.runtime.decision_journal import build_trade_notification_record
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    PeerScore,
    StrategyDecision,
    StrategyStatus,
)


def _imports_for(path: Path) -> list[str]:
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
    return imports


def _candidate_decision() -> StrategyDecision:
    candidate = CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 10),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=4.2,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP", "PSTG", "WDC"],
        peer_scores=[PeerScore(ticker="NTAP", score=5)],
        main_thesis="Bullish AI_STORAGE read-through for NTNX.",
        supporting_evidence=["Peers are strong."],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
    )
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=candidate,
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
            target="NTNX",
            theme="AI_STORAGE",
            peer_scores=[],
            thresholds={},
            missing_peer_factor_count=0,
            all_peer_data_missing=False,
            target_market_data_present=True,
            option_contract_count=1,
        ),
        claude_analysis_allowed=True,
    )


def _notification_result():
    request = build_trade_notification_request(
        decision=_candidate_decision(),
        order_proposal=RiskOrderProposal(
            target="NTNX",
            expression="CALL_OPTION",
            estimated_entry_cost=515.0,
            maximum_loss=515.0,
        ),
        order_result=OrderExecutionResult(
            broker="alpaca",
            order_id="order-123",
            status=BrokerOrderStatus.FILLED,
            filled_qty=1,
            avg_fill_price=5.15,
            submitted_at=datetime(2026, 6, 3, 14, 30, tzinfo=UTC),
            message="filled",
        ),
        run_id="scheduled:2026-06-03",
        decision_id="decision-001",
        decision_index=0,
        broker="alpaca",
        execution_mode="paper",
    )
    return dispatch_trade_notification(
        request,
        adapter=InMemoryNotificationAdapter(),
        settings=TradeNotificationSettings(channel=NotificationChannel.IN_MEMORY),
    )


def test_r8_2_notification_path_has_no_forbidden_dependencies() -> None:
    forbidden_roots = {
        "anthropic",
        "openai",
        "httpx",
        "requests",
        "aiohttp",
        "urllib",
        "time",
        "asyncio",
        "os",
        "dotenv",
        "prescient.analyst",
        "prescient.data",
        "prescient.broker.alpaca",
        "prescient.broker.robinhood",
        "prescient.runtime",
        "prescient.scheduler",
        "prescient.events",
    }

    alert_files = [
        Path("src/prescient/alerts/models.py"),
        Path("src/prescient/alerts/formatter.py"),
        Path("src/prescient/alerts/interfaces.py"),
        Path("src/prescient/alerts/dispatcher.py"),
    ]
    for path in alert_files:
        imports = _imports_for(path)
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_roots
        ), f"{path} imports forbidden dependency: {imports}"
        source = path.read_text(encoding="utf-8")
        assert "while True" not in source
        assert "time.sleep" not in source
        assert "asyncio.sleep" not in source


def test_core_layers_do_not_import_alerts() -> None:
    forbidden_dirs = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/analyst"),
    ]

    for directory in forbidden_dirs:
        for path in directory.glob("*.py"):
            imports = _imports_for(path)
            assert not any(
                imported == "prescient.alerts" or imported.startswith("prescient.alerts.")
                for imported in imports
            ), f"{path} imports prescient.alerts"


def test_notification_record_serialization_is_journal_safe() -> None:
    result = _notification_result()
    record = build_trade_notification_record(
        notification_result=result,
        trading_date=date(2026, 6, 3),
    )

    dumped = record.model_dump_json()
    assert "api_key" not in dumped
    assert "authorization" not in dumped.lower()
    assert "account_id" not in dumped
    assert "account_number" not in dumped
    assert "balance" not in dumped.lower()
    assert "buying_power" not in dumped
    assert "raw_prompt" not in dumped
    assert "raw_payload" not in dumped
    assert "webhook" not in dumped.lower()
    assert "bot_token" not in dumped
    assert result.request is not None
    assert result.request.target == "NTNX"
