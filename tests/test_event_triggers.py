from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from prescient.analyst import ClaudeAnalysisStatus, ClaudeAnalystSettings
from prescient.events import (
    EventImportance,
    EventSourceType,
    FastPollPlan,
    MarketEventType,
    NormalizedEvent,
    classify_event,
    handle_event_trigger,
    normalize_event,
)
from prescient.runtime import PipelineRunResult
from prescient.signal.models import (
    CandidateBrief,
    DecisionAudit,
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    PeerScore,
    RejectionDetail,
    RejectionReason,
    RejectionStage,
    SignalValue,
    StrategyDecision,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)


class FakeClaudeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, ClaudeAnalystSettings]] = []

    def complete(self, prompt: str, settings: ClaudeAnalystSettings) -> str:
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


def _event(
    *,
    event_type: MarketEventType = MarketEventType.EARNINGS_RESULT,
    ticker: str | None = "ntnx",
    payload_summary: dict[str, str | int | float | bool | None] | None = None,
) -> NormalizedEvent:
    return normalize_event(
        source_type=EventSourceType.WEBHOOK,
        event_type=event_type,
        ticker=ticker,
        source_name="mock-provider",
        payload_summary=payload_summary or {"headline": "structured earnings update"},
        event_time=datetime(2026, 6, 1, 21, 0, 0),
        received_time=datetime(2026, 6, 1, 21, 0, 5),
        event_id="evt-123",
    )


def _calendar_event(
    ticker: str,
    earnings_date: date | None = date(2026, 6, 2),
) -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker=ticker,
        earnings_date=earnings_date,
        report_time="AMC",
    )


def _peer_result(
    ticker: str,
    *,
    earnings_date: date = date(2026, 5, 20),
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
            earnings_date=earnings_date,
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


def _peer_scores() -> list[PeerScore]:
    return [PeerScore(ticker="NTAP", score=5, positive_factors=["eps_beat"])]


def _audit() -> DecisionAudit:
    return DecisionAudit(
        target="NTNX",
        theme="AI_STORAGE",
        peer_scores=_peer_scores(),
        thresholds={
            "min_positive_peer_ratio": 0.67,
            "min_average_peer_score": 2.0,
            "min_avg_daily_volume": 1_000_000,
            "max_target_runup_pct": 10.0,
            "allow_stock_fallback": True,
        },
        missing_peer_factor_count=0,
        all_peer_data_missing=False,
        target_market_data_present=True,
        option_contract_count=1,
    )


def _candidate_brief() -> CandidateBrief:
    return CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 2),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=5.0,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP"],
        peer_scores=_peer_scores(),
        main_thesis="Bullish AI_STORAGE read-through for NTNX.",
        supporting_evidence=["1 of 1 peers had positive scores."],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
    )


def _candidate_ready_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=_candidate_brief(),
        rejection_reasons=[],
        rejection_details=[],
        audit=_audit(),
        claude_analysis_allowed=True,
    )


def _rejected_decision() -> StrategyDecision:
    return StrategyDecision(
        status=StrategyStatus.REJECTED_WITH_REASON,
        candidate=None,
        rejection_reasons=[RejectionReason.INSUFFICIENT_PEERS_REPORTED],
        rejection_details=[
            RejectionDetail(
                reason=RejectionReason.INSUFFICIENT_PEERS_REPORTED,
                stage=RejectionStage.CANDIDATE_DETECTION,
                message="Not enough peers reported.",
            )
        ],
        audit=_audit(),
        claude_analysis_allowed=False,
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


def test_normalization_uppercases_ticker_and_produces_stable_fingerprint() -> None:
    first = _event()
    second = _event()

    assert first.ticker == "NTNX"
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert first.payload_summary == {"headline": "structured earnings update"}


def test_different_stable_event_fields_change_fingerprint() -> None:
    first = _event()
    second = normalize_event(
        source_type=EventSourceType.WEBHOOK,
        event_type=MarketEventType.EARNINGS_RESULT,
        ticker="NTNX",
        source_name="mock-provider",
        payload_summary={"headline": "structured earnings update"},
        event_time=datetime(2026, 6, 1, 21, 0, 0),
        received_time=datetime(2026, 6, 1, 21, 0, 5),
        event_id="evt-456",
    )

    assert first.fingerprint != second.fingerprint


def test_payload_summary_rejects_raw_unbounded_payload_key() -> None:
    with pytest.raises(ValueError, match="raw"):
        normalize_event(
            source_type=EventSourceType.WEBHOOK,
            event_type=MarketEventType.MAJOR_NEWS,
            ticker="NTNX",
            source_name="mock-provider",
            payload_summary={"raw_text": "large transcript should not pass"},
        )


def test_missing_ticker_is_ignored_and_does_not_refresh() -> None:
    classification = classify_event(_event(ticker=None), universe=_universe())

    assert classification.importance == EventImportance.IGNORED
    assert classification.is_relevant is False
    assert classification.should_refresh_strategy is False
    assert classification.claude_analysis_allowed is False


def test_unsupported_or_out_of_universe_event_is_ignored() -> None:
    unsupported = classify_event(
        _event(event_type=MarketEventType.UNSUPPORTED),
        universe=_universe(),
    )
    out_of_universe = classify_event(_event(ticker="NVDA"), universe=_universe())

    assert unsupported.importance == EventImportance.IGNORED
    assert out_of_universe.importance == EventImportance.IGNORED
    assert out_of_universe.theme is None


def test_in_universe_quote_is_journal_only() -> None:
    classification = classify_event(
        _event(event_type=MarketEventType.QUOTE),
        universe=_universe(),
    )

    assert classification.importance == EventImportance.JOURNAL_ONLY
    assert classification.is_relevant is True
    assert classification.should_refresh_strategy is False
    assert classification.theme == "AI_STORAGE"


@pytest.mark.parametrize(
    "event_type",
    [MarketEventType.EARNINGS_RESULT, MarketEventType.GUIDANCE_UPDATE],
)
def test_earnings_and_guidance_events_are_candidate_review(
    event_type: MarketEventType,
) -> None:
    classification = classify_event(_event(event_type=event_type), universe=_universe())

    assert classification.importance == EventImportance.CANDIDATE_REVIEW
    assert classification.should_refresh_strategy is True
    assert classification.claude_analysis_allowed is True


@pytest.mark.parametrize(
    "event_type",
    [
        MarketEventType.MAJOR_NEWS,
        MarketEventType.PRICE_MOVE,
        MarketEventType.VOLUME_SPIKE,
        MarketEventType.OPTIONS_LIQUIDITY_CHANGE,
    ],
)
def test_market_events_are_strategy_refresh(event_type: MarketEventType) -> None:
    classification = classify_event(_event(event_type=event_type), universe=_universe())

    assert classification.importance == EventImportance.STRATEGY_REFRESH
    assert classification.should_refresh_strategy is True
    assert classification.claude_analysis_allowed is False


def test_in_universe_inactive_ticker_downgrades_to_journal_only() -> None:
    classification = classify_event(
        _event(event_type=MarketEventType.EARNINGS_RESULT, ticker="NTNX"),
        universe=_universe(),
        active_tickers={"WDC"},
    )

    assert classification.importance == EventImportance.JOURNAL_ONLY
    assert classification.should_refresh_strategy is False
    assert "active" in classification.reason


def test_same_event_classified_twice_is_deterministic() -> None:
    event = _event(event_type=MarketEventType.MAJOR_NEWS)

    first = classify_event(event, universe=_universe())
    second = classify_event(event, universe=_universe())

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_ignored_and_journal_only_events_do_not_call_runtime_or_claude(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_runtime(**kwargs: object) -> PipelineRunResult:
        calls.append(kwargs)
        return PipelineRunResult()

    monkeypatch.setattr(
        "prescient.events.runner.runtime_pipeline.run_hot_cold_strategy_pipeline",
        fake_runtime,
    )
    client = FakeClaudeClient(_valid_claude_response())

    ignored = handle_event_trigger(
        event=_event(ticker="NVDA"),
        universe=_universe(),
        upcoming_events=[],
        peer_results=[],
        target_market_data=None,
        options_chains=None,
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
    )
    journal_only = handle_event_trigger(
        event=_event(event_type=MarketEventType.QUOTE),
        universe=_universe(),
        upcoming_events=[],
        peer_results=[],
        target_market_data=None,
        options_chains=None,
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
    )

    assert ignored.runtime_result is None
    assert journal_only.runtime_result is None
    assert calls == []
    assert client.calls == []


def test_important_event_calls_runtime_once(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_runtime(**kwargs: object) -> PipelineRunResult:
        calls.append(kwargs)
        return PipelineRunResult(strategy_decisions=[_rejected_decision()])

    monkeypatch.setattr(
        "prescient.events.runner.runtime_pipeline.run_hot_cold_strategy_pipeline",
        fake_runtime,
    )

    result = handle_event_trigger(
        event=_event(event_type=MarketEventType.MAJOR_NEWS),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX")],
        peer_results=[],
        target_market_data=None,
        options_chains=None,
        current_date=date(2026, 6, 1),
    )

    assert result.runtime_result is not None
    assert len(calls) == 1
    assert calls[0]["current_date"] == date(2026, 6, 1)
    assert calls[0]["enable_claude_analysis"] is False


def test_duplicate_fingerprint_skips_runtime(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_runtime(**kwargs: object) -> PipelineRunResult:
        calls.append(kwargs)
        return PipelineRunResult()

    monkeypatch.setattr(
        "prescient.events.runner.runtime_pipeline.run_hot_cold_strategy_pipeline",
        fake_runtime,
    )
    event = _event(event_type=MarketEventType.EARNINGS_RESULT)

    result = handle_event_trigger(
        event=event,
        universe=_universe(),
        upcoming_events=[],
        peer_results=[],
        target_market_data=None,
        options_chains=None,
        current_date=date(2026, 6, 1),
        processed_fingerprints={event.fingerprint},
    )

    assert result.classification.is_duplicate is True
    assert result.classification.should_refresh_strategy is False
    assert result.runtime_result is None
    assert calls == []


def test_candidate_ready_event_can_reach_claude_only_through_runtime() -> None:
    client = FakeClaudeClient(_valid_claude_response())

    result = handle_event_trigger(
        event=_event(event_type=MarketEventType.EARNINGS_RESULT),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX")],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
    )

    assert result.runtime_result is not None
    assert result.runtime_result.strategy_decisions[0].status == (
        StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    )
    assert result.runtime_result.claude_results[0].status == ClaudeAnalysisStatus.ANALYZED
    assert len(client.calls) == 1
    assert "structured earnings update" not in client.calls[0][0]


def test_rejected_runtime_result_skips_fake_claude() -> None:
    client = FakeClaudeClient(_valid_claude_response())

    result = handle_event_trigger(
        event=_event(event_type=MarketEventType.EARNINGS_RESULT),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX")],
        peer_results=[_peer_result("NTAP")],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=True,
        claude_client=client,
    )

    assert result.runtime_result is not None
    assert result.runtime_result.strategy_decisions[0].status == (
        StrategyStatus.REJECTED_WITH_REASON
    )
    assert result.runtime_result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert client.calls == []


def test_fast_poll_plan_serializes_explicit_bounds() -> None:
    plan = FastPollPlan(
        ticker="ntnx",
        window_start=datetime(2026, 6, 1, 20, 0, 0),
        window_end=datetime(2026, 6, 1, 21, 0, 0),
        max_attempts=10,
        interval_seconds=15,
        max_duration_seconds=180,
    )

    dumped = plan.model_dump(mode="json")

    assert dumped["ticker"] == "NTNX"
    assert dumped["max_attempts"] == 10
    assert dumped["interval_seconds"] == 15
    assert dumped["max_duration_seconds"] == 180


@pytest.mark.parametrize(
    "field",
    ["max_attempts", "interval_seconds", "max_duration_seconds"],
)
def test_fast_poll_plan_rejects_zero_or_negative_bounds(field: str) -> None:
    with pytest.raises(ValueError):
        FastPollPlan(
            ticker="NTNX",
            window_start=datetime(2026, 6, 1, 20, 0, 0),
            window_end=datetime(2026, 6, 1, 21, 0, 0),
            max_attempts=0 if field == "max_attempts" else 10,
            interval_seconds=0 if field == "interval_seconds" else 15,
            max_duration_seconds=0 if field == "max_duration_seconds" else 180,
        )


def test_events_package_has_no_continuous_polling_constructs() -> None:
    event_source = "\n".join(
        path.read_text() for path in Path("src/prescient/events").glob("*.py")
    )

    assert "while True" not in event_source
    assert "time.sleep" not in event_source
    assert "asyncio.sleep" not in event_source


def test_event_runner_does_not_import_analyst_directly() -> None:
    event_source = "\n".join(
        path.read_text() for path in Path("src/prescient/events").glob("*.py")
    )

    assert "prescient.analyst" not in event_source
