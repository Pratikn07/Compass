from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

from prescient.analyst import ClaudeAnalystSettings, SubAgentName, SubAgentStatus
from prescient.broker.mock import MockBrokerAdapter
from prescient.runtime import (
    DecisionJournalRecordType,
    DecisionOutcomeType,
    PipelineJournalEventType,
    build_decision_id,
    classify_decision_outcome,
    read_decision_journal_records,
    run_hot_cold_strategy_pipeline,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    RejectionReason,
    SignalValue,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)


class FakeClaudeClient:
    def __init__(self, response: str, *, journal_path_to_check: Path | None = None) -> None:
        self.response = response
        self.journal_path_to_check = journal_path_to_check
        self.calls: list[tuple[str, ClaudeAnalystSettings]] = []

    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        if self.journal_path_to_check is not None:
            journal_lines = self.journal_path_to_check.read_text().splitlines()
            assert json.loads(journal_lines[0])["record_type"] == "strategy_decision"

        self.calls.append((prompt, settings))
        return self.response


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC"],
                drivers=["AI data center demand"],
            )
        ]
    )


def _upcoming_target() -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker="NTNX",
        earnings_date=date(2026, 6, 2),
        report_time="AMC",
    )


def _peer_result(
    ticker: str,
    *,
    eps_estimate: float | None = 1.0,
    eps_actual: float | None = 1.2,
    revenue_estimate: float | None = 1_000.0,
    revenue_actual: float | None = 1_100.0,
    price_reaction_pct: float | None = 4.0,
    guidance_signal: SignalValue = "positive",
    theme_driver_signal: SignalValue = "positive",
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2026, 5, 20),
            report_time="AMC",
            eps_estimate=eps_estimate,
            eps_actual=eps_actual,
            revenue_estimate=revenue_estimate,
            revenue_actual=revenue_actual,
        ),
        price_reaction_pct=price_reaction_pct,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )


def _positive_peer_results() -> list[PeerResult]:
    return [_peer_result("NTAP"), _peer_result("PSTG"), _peer_result("WDC")]


def _target_data() -> TargetMarketData:
    return TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=4.0,
    )


def _call_option() -> OptionContractSnapshot:
    return OptionContractSnapshot(
        ticker="NTNX",
        option_type="CALL",
        expiration_date=date(2026, 6, 12),
        bid=4.85,
        ask=5.15,
        open_interest=250,
    )


def _valid_claude_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from strong peer earnings.",
      "reasoning": "Peer read-through is strong.",
      "conviction_score": 82,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """


def _valid_sub_agent_response(agent_name: SubAgentName) -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "status": "analyzed",
            "summary": f"{agent_name.value} review supports the candidate.",
            "supports_thesis": True,
            "risks": [],
            "missing_context": [],
            "confidence": 78,
        }
    )


def _run_pipeline(
    *,
    journal_path: Path | None = None,
    run_id: str = "scheduled:2026-06-01",
    peer_results: list[PeerResult] | None = None,
    enable_claude_analysis: bool = False,
    enable_sub_agent_analysis: bool = False,
    claude_client: FakeClaudeClient | None = None,
    sub_agent_client: FakeClaudeClient | None = None,
    broker_adapter: MockBrokerAdapter | None = None,
):
    return run_hot_cold_strategy_pipeline(
        run_id=run_id,
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=peer_results if peer_results is not None else _positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=enable_claude_analysis,
        claude_client=claude_client,
        enable_sub_agent_analysis=enable_sub_agent_analysis,
        sub_agent_clients={SubAgentName.SENTIMENT: sub_agent_client}
        if sub_agent_client is not None
        else None,
        enabled_sub_agents=[SubAgentName.SENTIMENT],
        journal_path=journal_path,
        broker_adapter=broker_adapter,
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_candidate_ready_strategy_decision_is_journaled_with_thesis_and_snapshot(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"

    result = _run_pipeline(journal_path=journal_path)

    assert result.journal_events[0].event_type == PipelineJournalEventType.HOT_PATH_DECISION
    assert result.decision_journal_records[0].record_type == (
        DecisionJournalRecordType.STRATEGY_DECISION
    )

    journal_lines = _jsonl(journal_path)
    strategy_record = journal_lines[0]
    payload = strategy_record["payload"]

    assert strategy_record["record_type"] == "strategy_decision"
    assert strategy_record["run_id"] == "scheduled:2026-06-01"
    assert strategy_record["decision_id"] == result.decision_journal_records[0].decision_id
    assert strategy_record["target"] == "NTNX"
    assert strategy_record["theme"] == "AI_STORAGE"
    assert strategy_record["strategy_type"] == "bullish_earnings_readthrough"
    assert strategy_record["strategy_status"] == "candidate_ready_for_analyst"
    assert "Bullish AI_STORAGE read-through for NTNX" in payload["thesis"]
    assert payload["decision_summary"] == "candidate_ready_for_analyst"
    assert payload["strategy_decision"]["status"] == "candidate_ready_for_analyst"
    assert payload["candidate_brief"]["target"] == "NTNX"
    assert payload["data_snapshot"]["target_market_data_present"] is True
    assert payload["data_snapshot"]["option_contract_count"] == 1
    assert payload["settings_snapshot"]["min_reported_peers"] == 3
    assert payload["missing_data"] == []


def test_rejected_strategy_decision_is_journaled_without_trade_thesis(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"

    result = _run_pipeline(journal_path=journal_path, peer_results=[_peer_result("NTAP")])

    assert result.strategy_decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert result.strategy_decisions[0].rejection_reasons == [
        RejectionReason.INSUFFICIENT_PEERS_REPORTED
    ]
    rejected_record = _jsonl(journal_path)[0]
    payload = rejected_record["payload"]

    assert rejected_record["record_type"] == "strategy_decision"
    assert rejected_record["strategy_status"] == "rejected_with_reason"
    assert payload["candidate_brief"] is None
    assert payload["rejection_reasons"] == ["insufficient_peers_reported"]
    assert "Rejected strategy decision" in payload["thesis"]
    assert "Bullish" not in payload["thesis"]


def test_decision_id_is_stable_for_same_run_and_decision() -> None:
    first = _run_pipeline(run_id="scheduled:2026-06-01")
    second = _run_pipeline(run_id="scheduled:2026-06-01")

    first_id = build_decision_id(
        run_id="scheduled:2026-06-01",
        decision_index=0,
        decision=first.strategy_decisions[0],
    )
    second_id = build_decision_id(
        run_id="scheduled:2026-06-01",
        decision_index=0,
        decision=second.strategy_decisions[0],
    )

    assert first_id == second_id
    assert first.decision_journal_records[0].decision_id == first_id
    assert second.decision_journal_records[0].decision_id == second_id


def test_hot_path_record_is_written_before_cold_path_records(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    claude_client = FakeClaudeClient(
        _valid_claude_response(),
        journal_path_to_check=journal_path,
    )
    sub_agent_client = FakeClaudeClient(
        _valid_sub_agent_response(SubAgentName.SENTIMENT),
        journal_path_to_check=journal_path,
    )

    result = _run_pipeline(
        journal_path=journal_path,
        enable_claude_analysis=True,
        enable_sub_agent_analysis=True,
        claude_client=claude_client,
        sub_agent_client=sub_agent_client,
    )

    record_types = [record["record_type"] for record in _jsonl(journal_path)]
    assert record_types == ["strategy_decision", "sub_agent_review", "analyst_review"]
    assert result.decision_journal_records[1].decision_id == (
        result.decision_journal_records[0].decision_id
    )
    assert result.decision_journal_records[2].decision_id == (
        result.decision_journal_records[0].decision_id
    )
    assert result.sub_agent_packets[0].results[0].status == SubAgentStatus.ANALYZED


def test_broker_run_appends_risk_and_sizing_records_with_same_decision_id(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    broker = MockBrokerAdapter(
        execution_mode="paper",
        account_equity=100_000.0,
        account_cash=100_000.0,
        account_buying_power=100_000.0,
    )

    result = _run_pipeline(journal_path=journal_path, broker_adapter=broker)

    journal_lines = _jsonl(journal_path)
    record_types = [line["record_type"] for line in journal_lines]
    decision_id = journal_lines[0]["decision_id"]

    assert record_types == [
        "strategy_decision",
        "analyst_review",
        "risk_decision",
        "position_sizing",
    ]
    assert all(line["decision_id"] == decision_id for line in journal_lines)
    assert journal_lines[2]["execution_mode"] == "paper"
    assert journal_lines[2]["payload"]["risk_gate_decision"]["status"] == "approved"
    assert journal_lines[3]["payload"]["position_sizing_decision"]["status"] == "sized"
    assert len(result.risk_gate_decisions) == 1
    assert len(result.sizing_decisions) == 1


def test_outcome_classifier_uses_realized_net_pnl_and_preserves_unknowns() -> None:
    assert classify_decision_outcome(net_realized_pnl=12.25).outcome_type == (
        DecisionOutcomeType.CLOSED_WIN
    )
    assert classify_decision_outcome(net_realized_pnl=-2.0).outcome_type == (
        DecisionOutcomeType.CLOSED_LOSS
    )
    assert classify_decision_outcome(net_realized_pnl=0.0).outcome_type == (
        DecisionOutcomeType.CLOSED_FLAT
    )

    unresolved = classify_decision_outcome(net_realized_pnl=None)
    ambiguous = classify_decision_outcome(
        net_realized_pnl=None,
        ambiguous=True,
        outcome_reasons=["ambiguous_outcome_match"],
    )

    assert unresolved.outcome_type == DecisionOutcomeType.UNKNOWN
    assert unresolved.net_realized_pnl is None
    assert ambiguous.outcome_type == DecisionOutcomeType.UNKNOWN
    assert ambiguous.ambiguous is True
    assert ambiguous.outcome_reasons == ["ambiguous_outcome_match"]


def test_jsonl_reader_filters_by_run_id_and_decision_id(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    result = _run_pipeline(journal_path=journal_path, run_id="scheduled:2026-06-01")
    _run_pipeline(journal_path=journal_path, run_id="scheduled:2026-06-02")

    run_records = read_decision_journal_records(
        journal_path,
        run_id="scheduled:2026-06-01",
    )
    decision_records = read_decision_journal_records(
        journal_path,
        decision_id=result.decision_journal_records[0].decision_id,
    )

    assert {record.run_id for record in run_records} == {"scheduled:2026-06-01"}
    assert {record.decision_id for record in decision_records} == {
        result.decision_journal_records[0].decision_id
    }


def test_domain_packages_do_not_import_decision_journal_writer() -> None:
    forbidden_packages = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/analyst"),
    ]
    forbidden_import = "prescient.runtime.decision_journal"

    offenders: list[Path] = []
    for package_path in forbidden_packages:
        for path in package_path.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported_modules = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            imported_modules.extend(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )
            if any(
                module == forbidden_import or module.startswith(f"{forbidden_import}.")
                for module in imported_modules
            ):
                offenders.append(path)

    assert offenders == []
