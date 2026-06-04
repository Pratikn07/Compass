from __future__ import annotations

from datetime import date
from pathlib import Path

from prescient.alerts import (
    AlertChannelType,
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertEventType,
    AlertProvider,
    AlertRecipient,
    build_alert_events,
)
from prescient.rollout import RolloutStage
from prescient.runtime import run_hot_cold_strategy_pipeline
from prescient.runtime.models import DecisionJournalRecord
from prescient.scheduler import (
    ScheduleTriggerType,
    ScheduledRunRequest,
    run_scheduled_strategy_pipeline,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)


class RecordingAlertDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[list[DecisionJournalRecord], list[AlertRecipient], bool]] = []

    def dispatch_records(
        self,
        records: list[DecisionJournalRecord],
        recipients: list[AlertRecipient],
        *,
        dry_run: bool = False,
    ) -> list[AlertDeliveryResult]:
        self.calls.append((list(records), list(recipients), dry_run))
        return [
            AlertDeliveryResult(
                alert_id=event.alert_id,
                provider=AlertProvider.TELEGRAM,
                channel_type=AlertChannelType.TELEGRAM,
                destination_label=recipients[0].destination_label,
                status=AlertDeliveryStatus.DRY_RUN
                if dry_run
                else AlertDeliveryStatus.SENT,
            )
            for event in build_alert_events(records)
        ]


def _recipient() -> AlertRecipient:
    return AlertRecipient(
        channel_type=AlertChannelType.TELEGRAM,
        provider=AlertProvider.TELEGRAM,
        destination_label="ops",
        destination="chat-1",
    )


def test_runtime_dispatches_alerts_when_dispatcher_is_provided() -> None:
    dispatcher = RecordingAlertDispatcher()

    result = _run_pipeline(
        alert_dispatcher=dispatcher,
        alert_recipients=[_recipient()],
        alert_dry_run=True,
        rollout_stage=RolloutStage.ALERTS_ONLY,
    )

    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][2] is True
    assert result.alert_delivery_results
    assert result.alert_delivery_results[0].status == AlertDeliveryStatus.DRY_RUN


def test_runtime_does_not_dispatch_alerts_without_dispatcher() -> None:
    result = _run_pipeline(alert_dispatcher=None, alert_recipients=[_recipient()])

    assert result.alert_delivery_results == []


def test_runtime_dashboard_only_suppresses_alert_dispatch_by_default() -> None:
    dispatcher = RecordingAlertDispatcher()

    result = _run_pipeline(
        alert_dispatcher=dispatcher,
        alert_recipients=[_recipient()],
    )

    assert dispatcher.calls == []
    assert result.alert_delivery_results == []
    assert result.decision_journal_records[0].record_type.value == "strategy_decision"


def test_scheduler_passes_alert_options_through() -> None:
    dispatcher = RecordingAlertDispatcher()
    request = ScheduledRunRequest(
        run_id="scheduled:2026-06-03",
        trigger_type=ScheduleTriggerType.SCHEDULED,
        scheduled_date=date(2026, 6, 3),
        current_date=date(2026, 6, 3),
        window_start=date(2026, 6, 3),
        window_end=date(2026, 6, 4),
        relevant_tickers=["NTNX"],
    )

    result = run_scheduled_strategy_pipeline(
        request=request,
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        alert_dispatcher=dispatcher,
        alert_recipients=[_recipient()],
        alert_dry_run=True,
        rollout_stage=RolloutStage.ALERTS_ONLY,
    )

    assert result.runtime_result.alert_delivery_results
    assert dispatcher.calls[0][0][0].run_id == "scheduled:2026-06-03"


def test_runtime_alert_dispatch_preserves_jsonl_journal_behavior(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    dispatcher = RecordingAlertDispatcher()

    result = _run_pipeline(
        journal_path=journal_path,
        alert_dispatcher=dispatcher,
        alert_recipients=[_recipient()],
        rollout_stage=RolloutStage.ALERTS_ONLY,
    )

    assert journal_path.exists()
    assert result.decision_journal_records[0].record_type.value == "strategy_decision"
    assert result.alert_delivery_results[0].status == AlertDeliveryStatus.SENT
    assert build_alert_events(result.decision_journal_records)[0].event_type == (
        AlertEventType.SETUP_DETECTED
    )


def _run_pipeline(
    *,
    alert_dispatcher: RecordingAlertDispatcher | None,
    alert_recipients: list[AlertRecipient] | None,
    alert_dry_run: bool = False,
    journal_path: Path | None = None,
    rollout_stage: RolloutStage | str | None = None,
):
    return run_hot_cold_strategy_pipeline(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_positive_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 3),
        journal_path=journal_path,
        alert_dispatcher=alert_dispatcher,
        alert_recipients=alert_recipients,
        alert_dry_run=alert_dry_run,
        rollout_stage=rollout_stage,
    )


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
        earnings_date=date(2026, 6, 4),
        report_time="AMC",
    )


def _peer_result(ticker: str) -> PeerResult:
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
        price_reaction_pct=4.0,
        guidance_signal="positive",
        theme_driver_signal="positive",
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
