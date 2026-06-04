from __future__ import annotations

import json
from datetime import date
from typing import TypedDict

from prescient.journal import SourceCitation
from prescient.runtime import run_hot_cold_strategy_pipeline
from prescient.analyst import ClaudeAnalystSettings
from prescient.signal import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
    ThemeConfig,
)


class FakeClaude:
    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
        return json.dumps(
            {
                "recommendation": "go",
                "thesis": "Peer results support the read-through.",
                "reasoning": "Structured peer evidence is positive.",
                "conviction_score": 72,
                "missing_context": [],
                "contradictions": [],
                "suggested_expression": "CALL_OPTION",
                "cited_citation_ids": ["peer-ntap"],
            }
        )


class RuntimeInputs(TypedDict):
    universe: StrategyUniverse
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: dict[str, TargetMarketData]
    options_chains: dict[str, list[OptionContractSnapshot]] | None
    indicator_snapshots: dict[str, TechnicalIndicatorSnapshot] | None
    current_date: date


def _citation(citation_id: str) -> SourceCitation:
    return SourceCitation(
        citation_id=citation_id,
        provider="fixture",
        source_type="earnings_result",
        excerpt="bounded peer result",
    )


def _runtime_inputs() -> RuntimeInputs:
    universe = StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC"],
                drivers=["AI data center demand"],
            )
        ]
    )
    upcoming_events = [
            EarningsCalendarEvent(
                ticker="NTNX",
                earnings_date=date(2026, 6, 10),
                report_time="AMC",
            source_citations=[_citation("target-calendar")],
        )
    ]
    peer_results = [
        PeerResult(
            ticker=ticker,
            earnings_event=EarningsEvent(
                ticker=ticker,
                earnings_date=date(2026, 6, 1),
                report_time="AMC",
                eps_estimate=1.0,
                eps_actual=1.2,
                revenue_estimate=100.0,
                revenue_actual=120.0,
                source_citations=[_citation(f"peer-{ticker.lower()}")],
            ),
            price_reaction_pct=4.0,
            guidance_signal="positive",
            theme_driver_signal="positive",
        )
        for ticker in ["NTAP", "PSTG", "WDC"]
    ]
    target_market_data = {
        "NTNX": TargetMarketData(
            ticker="NTNX",
            avg_daily_volume=2_000_000,
            pre_earnings_runup_pct=4.0,
            source_citations=[_citation("target-market")],
        )
    }
    return {
        "universe": universe,
        "upcoming_events": upcoming_events,
        "peer_results": peer_results,
        "target_market_data": target_market_data,
        "options_chains": None,
        "indicator_snapshots": None,
        "current_date": date(2026, 6, 2),
    }


def test_runtime_journal_events_include_identity_and_citations(tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"

    result = run_hot_cold_strategy_pipeline(
        **_runtime_inputs(),
        run_id="scheduled:2026-06-02",
        enable_claude_analysis=True,
        claude_client=FakeClaude(),
        journal_path=journal_path,
    )

    assert result.journal_events[0].event_type == "hot_path_decision"
    assert result.journal_events[1].event_type == "cold_path_analysis"
    assert result.journal_events[0].run_id == "scheduled:2026-06-02"
    assert result.journal_events[0].decision_id
    assert result.journal_events[0].source_citations
    assert result.journal_events[1].parent_decision_ids == [
        result.journal_events[0].decision_id
    ]

    lines = journal_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["record_type"] == "strategy_decision"
    assert second["record_type"] == "analyst_review"
    assert first["source_citations"]
    assert first["decision_id"] == result.decision_journal_records[0].decision_id
    serialized = "\n".join(lines)
    forbidden = ["raw_payload", "api_key", "Authorization", "account_id", "raw prompt"]
    assert not any(token in serialized for token in forbidden)


def test_runtime_default_run_id_is_deterministic() -> None:
    first = run_hot_cold_strategy_pipeline(**_runtime_inputs())
    second = run_hot_cold_strategy_pipeline(**_runtime_inputs())

    assert [e.run_id for e in first.journal_events] == [e.run_id for e in second.journal_events]
    assert first.journal_events[0].run_id == "runtime:2026-06-02"
