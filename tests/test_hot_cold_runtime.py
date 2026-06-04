from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from prescient.analyst import (
    ClaudeAnalysisStatus,
    ClaudeAnalystSettings,
    SubAgentName,
    SubAgentStatus,
)
from prescient.runtime import PipelineJournalEventType, run_hot_cold_strategy_pipeline
from prescient.signal.core import evaluate_core_strategy
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
    def __init__(
        self,
        response: str,
        *,
        journal_path_to_check: Path | None = None,
    ) -> None:
        self.response = response
        self.journal_path_to_check = journal_path_to_check
        self.calls: list[tuple[str, ClaudeAnalystSettings]] = []

    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        if self.journal_path_to_check is not None:
            journal_lines = self.journal_path_to_check.read_text().splitlines()
            assert [json.loads(line)["record_type"] for line in journal_lines] == [
                "strategy_decision"
            ]

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
    return [
        _peer_result("NTAP"),
        _peer_result("PSTG"),
        _peer_result("WDC"),
    ]


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


def test_claude_disabled_keeps_candidate_hot_path_and_skips_client() -> None:
    client = FakeClaudeClient(_valid_claude_response())

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=False,
        claude_client=client,
    )

    assert result.strategy_decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert result.sub_agent_packets == []
    assert client.calls == []
    assert result.journal_events[0].event_type == PipelineJournalEventType.HOT_PATH_DECISION


def test_rejected_decision_skips_claude_and_preserves_rejection_reasons() -> None:
    client = FakeClaudeClient(_valid_claude_response())

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[_peer_result("NTAP")],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
    )

    assert result.strategy_decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert result.strategy_decisions[0].rejection_reasons == [
        RejectionReason.INSUFFICIENT_PEERS_REPORTED
    ]
    assert result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert client.calls == []


def test_candidate_ready_with_claude_enabled_analyzes_after_hot_journal_event(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "runtime" / "journal.jsonl"
    client = FakeClaudeClient(
        _valid_claude_response(),
        journal_path_to_check=journal_path,
    )

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
        journal_path=journal_path,
    )

    assert len(client.calls) == 1
    assert result.claude_results[0].status == ClaudeAnalysisStatus.ANALYZED
    assert [event.event_type for event in result.journal_events] == [
        PipelineJournalEventType.HOT_PATH_DECISION,
        PipelineJournalEventType.COLD_PATH_ANALYSIS,
    ]

    journal_lines = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [line["record_type"] for line in journal_lines] == [
        "strategy_decision",
        "analyst_review",
    ]
    assert journal_lines[0]["decision_index"] == 0
    assert journal_lines[0]["target"] == "NTNX"
    assert journal_lines[0]["theme"] == "AI_STORAGE"
    assert journal_lines[0]["strategy_status"] == "candidate_ready_for_analyst"


def test_sub_agent_enabled_run_emits_hot_event_before_sub_agent_review(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "runtime" / "journal.jsonl"
    sentiment_client = FakeClaudeClient(
        _valid_sub_agent_response(SubAgentName.SENTIMENT),
        journal_path_to_check=journal_path,
    )

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=False,
        enable_sub_agent_analysis=True,
        sub_agent_clients={SubAgentName.SENTIMENT: sentiment_client},
        enabled_sub_agents=[SubAgentName.SENTIMENT],
        journal_path=journal_path,
    )

    assert len(sentiment_client.calls) == 1
    assert result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert result.sub_agent_packets[0].results[0].status == SubAgentStatus.ANALYZED
    assert [event.event_type for event in result.journal_events] == [
        PipelineJournalEventType.HOT_PATH_DECISION,
        PipelineJournalEventType.SUB_AGENT_REVIEW,
        PipelineJournalEventType.COLD_PATH_ANALYSIS,
    ]

    journal_lines = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [line["record_type"] for line in journal_lines] == [
        "strategy_decision",
        "sub_agent_review",
        "analyst_review",
    ]
    assert journal_lines[1]["payload"]["results"][0]["agent_name"] == "sentiment"


def test_rejected_decision_skips_sub_agents_and_claude() -> None:
    sentiment_client = FakeClaudeClient(_valid_sub_agent_response(SubAgentName.SENTIMENT))
    claude_client = FakeClaudeClient(_valid_claude_response())

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[_peer_result("NTAP")],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=claude_client,
        enable_sub_agent_analysis=True,
        sub_agent_clients={SubAgentName.SENTIMENT: sentiment_client},
        enabled_sub_agents=[SubAgentName.SENTIMENT],
    )

    assert result.strategy_decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert result.sub_agent_packets[0].results[0].status == SubAgentStatus.SKIPPED
    assert sentiment_client.calls == []
    assert claude_client.calls == []


def test_claude_failure_does_not_change_deterministic_decision() -> None:
    expected_decision = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )[0]

    result = run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=FakeClaudeClient("{not valid json"),
    )

    assert result.claude_results[0].status == ClaudeAnalysisStatus.FAILED
    assert result.strategy_decisions[0].model_dump(mode="json") == expected_decision.model_dump(
        mode="json"
    )


def test_signal_package_has_no_claude_or_anthropic_import_boundary_leak() -> None:
    signal_files = Path("src/prescient/signal").glob("*.py")

    forbidden_imports = [
        path
        for path in signal_files
        if "prescient.analyst" in path.read_text() or "anthropic" in path.read_text()
    ]

    assert forbidden_imports == []
