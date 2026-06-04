from __future__ import annotations

from datetime import date
from pathlib import Path

from pytest import MonkeyPatch

from prescient.analyst import ClaudeAnalysisStatus, ClaudeAnalystSettings
from prescient.rollout import RolloutSettings, RolloutStage
from prescient.runtime import PipelineRunResult
from prescient.scheduler import (
    ScheduleTriggerType,
    ScheduledRunRequest,
    derive_scheduled_run_requests,
    run_scheduled_strategy_pipeline,
)
from prescient.signal.models import (
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
    StrategySettings,
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


def _calendar_event(
    ticker: str,
    earnings_date: date | None,
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


def _request(
    *,
    trigger_type: ScheduleTriggerType = ScheduleTriggerType.SCHEDULED,
) -> ScheduledRunRequest:
    return ScheduledRunRequest(
        run_id=f"{trigger_type.value}:2026-06-01",
        trigger_type=trigger_type,
        scheduled_date=date(2026, 6, 1),
        current_date=date(2026, 6, 1),
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 2),
        relevant_tickers=["NTNX"],
    )


def _audit() -> DecisionAudit:
    return DecisionAudit(
        target="NTNX",
        theme="AI_STORAGE",
        peer_scores=[
            PeerScore(
                ticker="NTAP",
                score=5,
                positive_factors=["eps_beat"],
            )
        ],
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


def test_configured_upcoming_ticker_inside_window_creates_scheduled_request() -> None:
    requests = derive_scheduled_run_requests(
        universe=_universe(),
        upcoming_events=[
            _calendar_event("NTNX", date(2026, 6, 2)),
            _calendar_event("nvda", date(2026, 6, 2)),
        ],
        peer_results=[],
        current_date=date(2026, 6, 1),
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.run_id == "scheduled:2026-06-01"
    assert request.trigger_type == ScheduleTriggerType.SCHEDULED
    assert request.current_date == date(2026, 6, 1)
    assert request.window_start == date(2026, 6, 1)
    assert request.window_end == date(2026, 6, 2)
    assert request.relevant_tickers == ["NTNX"]


def test_out_of_universe_or_outside_window_events_do_not_create_request() -> None:
    requests = derive_scheduled_run_requests(
        universe=_universe(),
        upcoming_events=[
            _calendar_event("NVDA", date(2026, 6, 2)),
            _calendar_event("NTNX", date(2026, 6, 4)),
        ],
        peer_results=[],
        current_date=date(2026, 6, 1),
    )

    assert requests == []


def test_recent_in_universe_peer_result_can_create_scheduled_request() -> None:
    requests = derive_scheduled_run_requests(
        universe=_universe(),
        upcoming_events=[],
        peer_results=[
            _peer_result("ntap", earnings_date=date(2026, 5, 20)),
            _peer_result("nvda", earnings_date=date(2026, 5, 20)),
        ],
        current_date=date(2026, 6, 1),
    )

    assert len(requests) == 1
    assert requests[0].relevant_tickers == ["NTAP"]


def test_relevant_tickers_are_sorted_unique_and_run_id_is_deterministic() -> None:
    settings = StrategySettings(earnings_window_days=2)

    first = derive_scheduled_run_requests(
        universe=_universe(),
        upcoming_events=[
            _calendar_event("wdc", date(2026, 6, 2)),
            _calendar_event("NTNX", date(2026, 6, 2)),
            _calendar_event("WDC", date(2026, 6, 3)),
        ],
        peer_results=[_peer_result("pstg", earnings_date=date(2026, 5, 20))],
        current_date=date(2026, 6, 1),
        settings=settings,
    )
    second = derive_scheduled_run_requests(
        universe=_universe(),
        upcoming_events=[
            _calendar_event("wdc", date(2026, 6, 2)),
            _calendar_event("NTNX", date(2026, 6, 2)),
            _calendar_event("WDC", date(2026, 6, 3)),
        ],
        peer_results=[_peer_result("pstg", earnings_date=date(2026, 5, 20))],
        current_date=date(2026, 6, 1),
        settings=settings,
    )

    assert first[0].relevant_tickers == ["NTNX", "PSTG", "WDC"]
    assert first[0].run_id == "scheduled:2026-06-01"
    assert first[0].model_dump(mode="json") == second[0].model_dump(mode="json")


def test_manual_and_catch_up_trigger_types_serialize_explicitly() -> None:
    manual = _request(trigger_type=ScheduleTriggerType.MANUAL)
    catch_up = _request(trigger_type=ScheduleTriggerType.CATCH_UP)

    assert manual.model_dump(mode="json")["trigger_type"] == "manual"
    assert catch_up.model_dump(mode="json")["trigger_type"] == "catch_up"


def test_scheduled_runner_calls_runtime_once_and_uses_request_current_date(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_runtime(**kwargs: object) -> PipelineRunResult:
        calls.append(kwargs)
        return PipelineRunResult(
            strategy_decisions=[_rejected_decision()],
            claude_results=[],
            journal_events=[],
        )

    monkeypatch.setattr(
        "prescient.scheduler.runner.runtime_pipeline.run_hot_cold_strategy_pipeline",
        fake_runtime,
    )

    result = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=[],
        target_market_data=None,
        options_chains=None,
        journal_path="journal/scheduled.jsonl",
        rollout_stage=RolloutStage.ALERTS_ONLY,
        rollout_settings=RolloutSettings(tiny_live_max_trade_loss_pct=0.0025),
    )

    assert len(calls) == 1
    assert calls[0]["run_id"] == "scheduled:2026-06-01"
    assert calls[0]["current_date"] == date(2026, 6, 1)
    assert calls[0]["enable_claude_analysis"] is False
    assert calls[0]["rollout_stage"] == RolloutStage.ALERTS_ONLY
    assert calls[0]["rollout_settings"].tiny_live_max_trade_loss_pct == 0.0025
    assert result.summary.run_id == "scheduled:2026-06-01"
    assert result.summary.journal_path == "journal/scheduled.jsonl"
    assert result.summary.upcoming_event_count == 1
    assert result.summary.total_decision_count == 1
    assert result.summary.rejected_count == 1
    assert result.summary.candidate_ready_count == 0


def test_candidate_ready_scheduled_run_skips_claude_when_disabled() -> None:
    result = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=False,
    )

    assert result.runtime_result.strategy_decisions[0].status == (
        StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    )
    assert result.runtime_result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert result.summary.candidate_ready_count == 1
    assert result.summary.claude_analysis_enabled is False


def test_claude_failure_does_not_mutate_scheduled_decision() -> None:
    disabled_result = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=False,
    )

    failed_result = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=True,
        claude_client=FakeClaudeClient("{not valid json"),
    )

    assert failed_result.runtime_result.claude_results[0].status == ClaudeAnalysisStatus.FAILED
    assert failed_result.runtime_result.strategy_decisions[0].model_dump(mode="json") == (
        disabled_result.runtime_result.strategy_decisions[0].model_dump(mode="json")
    )


def test_rejected_scheduled_decision_remains_rejected_and_claude_skipped() -> None:
    client = FakeClaudeClient(_valid_claude_response())

    result = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=[_peer_result("NTAP")],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=True,
        claude_client=client,
    )

    assert result.runtime_result.strategy_decisions[0].status == (
        StrategyStatus.REJECTED_WITH_REASON
    )
    assert result.runtime_result.claude_results[0].status == ClaudeAnalysisStatus.SKIPPED
    assert client.calls == []
    assert result.summary.rejected_count == 1


def test_scheduler_source_has_no_continuous_polling_constructs() -> None:
    scheduler_source = "\n".join(
        path.read_text() for path in Path("src/prescient/scheduler").glob("*.py")
    )

    assert "while True" not in scheduler_source
    assert "time.sleep" not in scheduler_source
    assert "asyncio.sleep" not in scheduler_source


def test_repeated_scheduled_runs_with_identical_inputs_are_deterministic() -> None:
    first = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=False,
    )
    second = run_scheduled_strategy_pipeline(
        request=_request(),
        universe=_universe(),
        upcoming_events=[_calendar_event("NTNX", date(2026, 6, 2))],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        enable_claude_analysis=False,
    )

    first_dump = first.model_dump(mode="json")
    second_dump = second.model_dump(mode="json")
    for dumped in (first_dump, second_dump):
        for record in dumped["runtime_result"]["decision_journal_records"]:
            record["created_at"] = "<append-time>"

    assert first_dump == second_dump
