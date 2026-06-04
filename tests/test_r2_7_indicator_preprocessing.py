from __future__ import annotations

from datetime import date, datetime
from typing import TypedDict

from prescient.analyst import build_claude_strategy_prompt
from prescient.events import (
    EventSourceType,
    MarketEventType,
    handle_event_trigger,
    normalize_event,
)
from prescient.runtime import run_hot_cold_strategy_pipeline
from prescient.scheduler import (
    ScheduleTriggerType,
    ScheduledRunRequest,
    run_scheduled_strategy_pipeline,
)
from prescient.signal.core import evaluate_core_strategy
from prescient.signal.models import (
    CandidateBrief,
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    SignalValue,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
    ThemeConfig,
)


class StrategyInputs(TypedDict):
    universe: StrategyUniverse
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: dict[str, TargetMarketData]
    options_chains: dict[str, list[OptionContractSnapshot]]
    current_date: date


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
            eps_estimate=1.0,
            eps_actual=1.2,
            revenue_estimate=1_000.0,
            revenue_actual=1_100.0,
        ),
        price_reaction_pct=price_reaction_pct,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )


def _peer_results() -> list[PeerResult]:
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


def _indicator_snapshot(**overrides: object) -> TechnicalIndicatorSnapshot:
    values = {
        "ticker": "NTNX",
        "as_of": date(2026, 6, 1),
        "rsi_14": 62.4,
        "macd_line": 1.25,
        "macd_signal": 1.05,
        "macd_histogram": 0.2,
        "macd_state": "bullish",
        "vwap": 42.75,
        "price_vs_vwap": "above",
        "missing_fields": [],
        "source": "mock-provider",
        "freshness": "current",
    }
    values.update(overrides)
    return TechnicalIndicatorSnapshot.model_validate(values)


def _strategy_inputs() -> StrategyInputs:
    return {
        "universe": _universe(),
        "upcoming_events": [_upcoming_target()],
        "peer_results": _peer_results(),
        "target_market_data": {"NTNX": _target_data()},
        "options_chains": {"NTNX": [_call_option()]},
        "current_date": date(2026, 6, 1),
    }


def _scheduled_request() -> ScheduledRunRequest:
    return ScheduledRunRequest(
        run_id="scheduled:2026-06-01",
        trigger_type=ScheduleTriggerType.SCHEDULED,
        scheduled_date=date(2026, 6, 1),
        current_date=date(2026, 6, 1),
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 2),
        relevant_tickers=["NTNX"],
    )


def test_core_strategy_attaches_matching_indicator_snapshot_to_candidate() -> None:
    snapshot = _indicator_snapshot()

    decisions = evaluate_core_strategy(
        **_strategy_inputs(),
        indicator_snapshots={"NTNX": snapshot},
    )

    assert decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decisions[0].candidate is not None
    assert decisions[0].candidate.technical_indicators == snapshot
    assert decisions[0].audit.indicator_snapshot_present is True
    assert decisions[0].audit.indicator_missing_fields == []
    assert decisions[0].audit.indicator_source == "mock-provider"
    assert decisions[0].audit.indicator_freshness == "current"


def test_missing_indicator_snapshot_preserves_candidate_behavior() -> None:
    first = evaluate_core_strategy(**_strategy_inputs(), indicator_snapshots=None)
    second = evaluate_core_strategy(**_strategy_inputs(), indicator_snapshots={})

    assert first[0].model_dump(mode="json") == second[0].model_dump(mode="json")
    assert first[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert first[0].candidate is not None
    assert first[0].candidate.technical_indicators is None
    assert first[0].audit.indicator_snapshot_present is False


def test_indicator_snapshot_with_missing_fields_remains_advisory() -> None:
    snapshot = _indicator_snapshot(
        rsi_14=None,
        macd_line=None,
        macd_signal=None,
        macd_histogram=None,
        macd_state="unknown",
        missing_fields=["rsi_14", "macd_line", "macd_signal", "macd_histogram"],
        freshness="stale",
    )

    decisions = evaluate_core_strategy(
        **_strategy_inputs(),
        indicator_snapshots={"NTNX": snapshot},
    )

    assert decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decisions[0].candidate is not None
    assert decisions[0].candidate.technical_indicators == snapshot
    assert decisions[0].audit.indicator_missing_fields == [
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_histogram",
    ]
    assert decisions[0].audit.indicator_freshness == "stale"


def test_runtime_scheduled_and_event_runners_pass_indicator_snapshots_through() -> None:
    snapshot = _indicator_snapshot()

    runtime_result = run_hot_cold_strategy_pipeline(
        **_strategy_inputs(),
        indicator_snapshots={"NTNX": snapshot},
        enable_claude_analysis=False,
    )
    scheduled_result = run_scheduled_strategy_pipeline(
        request=_scheduled_request(),
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        indicator_snapshots={"NTNX": snapshot},
        enable_claude_analysis=False,
    )
    event_result = handle_event_trigger(
        event=normalize_event(
            source_type=EventSourceType.WEBHOOK,
            event_type=MarketEventType.EARNINGS_RESULT,
            ticker="ntnx",
            source_name="mock-provider",
            payload_summary={"headline": "structured earnings update"},
            event_time=datetime(2026, 6, 1, 21, 0, 0),
            received_time=datetime(2026, 6, 1, 21, 0, 5),
            event_id="evt-r2-7",
        ),
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        indicator_snapshots={"NTNX": snapshot},
        current_date=date(2026, 6, 1),
        enable_claude_analysis=False,
    )

    assert runtime_result.strategy_decisions[0].candidate is not None
    assert (
        runtime_result.strategy_decisions[0].candidate.technical_indicators == snapshot
    )
    assert scheduled_result.runtime_result.strategy_decisions[0].candidate is not None
    assert (
        scheduled_result.runtime_result.strategy_decisions[
            0
        ].candidate.technical_indicators
        == snapshot
    )
    assert event_result.runtime_result is not None
    assert event_result.runtime_result.strategy_decisions[0].candidate is not None
    assert (
        event_result.runtime_result.strategy_decisions[0].candidate.technical_indicators
        == snapshot
    )


def test_claude_prompt_receives_compact_indicators_but_no_raw_candles() -> None:
    brief = CandidateBrief(
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 2),
        report_time="AMC",
        direction="bullish",
        peer_signal_score=4.5,
        positive_peer_ratio=1.0,
        reported_peers=["NTAP", "PSTG", "WDC"],
        peer_scores=[],
        main_thesis="Bullish AI_STORAGE read-through for NTNX.",
        supporting_evidence=["3 of 3 peers had positive scores."],
        contradictions=[],
        recommended_expression="CALL_OPTION",
        technical_indicators=_indicator_snapshot(),
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
    )

    prompt = build_claude_strategy_prompt(brief)

    assert '"rsi_14":62.4' in prompt
    assert '"macd_state":"bullish"' in prompt
    assert '"price_vs_vwap":"above"' in prompt
    assert '"source":"mock-provider"' in prompt
    assert '"freshness":"current"' in prompt
    assert "Do not calculate RSI, MACD, VWAP" in prompt
    assert "Do not reconstruct indicators from raw candles" in prompt
    assert '"raw_ohlcv"' not in prompt
    assert '"candles"' not in prompt
    assert '"ohlcv"' not in prompt
