"""Curated seed inputs for the propose-only engine cron.

These mirror the validated AI-storage / NTNX bullish scenario (the same shapes the
deterministic engine turns into a CANDIDATE_READY_FOR_ANALYST decision, already
verified against the frontend Zod parsers). This is an owned production artifact,
deliberately NOT an import of test fixtures, so the cron stays independent of tests.

Pure data only — no I/O, no network, no Supabase. Live provider-data fetching is a
separate future project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    SignalValue,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)

SEED_THEME = "AI_STORAGE"
SEED_TARGET = "NTNX"


@dataclass(frozen=True)
class SeedInputs:
    """Fully-assembled, typed inputs for run_scheduled_strategy_pipeline."""

    current_date: date
    universe: StrategyUniverse
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: dict[str, TargetMarketData]
    options_chains: dict[str, list[OptionContractSnapshot]]


def _peer_result(
    ticker: str,
    *,
    earnings_date: date,
    eps_actual: float,
    revenue_actual: float,
    price_reaction_pct: float,
    guidance_signal: SignalValue,
    theme_driver_signal: SignalValue,
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=earnings_date,
            report_time="AMC",
            eps_estimate=1.0,
            eps_actual=eps_actual,
            revenue_estimate=1_000.0,
            revenue_actual=revenue_actual,
        ),
        price_reaction_pct=price_reaction_pct,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )


def build_seed_inputs(*, current_date: date) -> SeedInputs:
    """Build the curated bullish AI-storage candidate, dated relative to the run.

    The target reports the day after current_date; peers reported in the trailing
    window. Four strong peers + one negative yields a positive_peer_ratio of 0.8,
    above threshold, producing a bullish CANDIDATE_READY_FOR_ANALYST decision.
    """
    target_earnings = current_date + timedelta(days=1)
    peer_earnings = current_date - timedelta(days=12)

    universe = StrategyUniverse(
        themes=[
            ThemeConfig(
                name=SEED_THEME,
                tickers=["NTNX", "NTAP", "PSTG", "WDC", "STX", "DELL"],
                drivers=["AI data center demand"],
            )
        ]
    )

    upcoming_events = [
        EarningsCalendarEvent(
            ticker=SEED_TARGET,
            earnings_date=target_earnings,
            report_time="AMC",
        )
    ]

    strong = dict(
        earnings_date=peer_earnings,
        eps_actual=1.2,
        revenue_actual=1_100.0,
        price_reaction_pct=4.0,
        guidance_signal="positive",
        theme_driver_signal="positive",
    )
    peer_results = [
        _peer_result("NTAP", **strong),
        _peer_result("PSTG", **strong),
        _peer_result("WDC", **strong),
        _peer_result("STX", **strong),
        _peer_result(
            "DELL",
            earnings_date=peer_earnings,
            eps_actual=0.8,
            revenue_actual=900.0,
            price_reaction_pct=-4.0,
            guidance_signal="negative",
            theme_driver_signal="negative",
        ),
    ]

    target_market_data = {
        SEED_TARGET: TargetMarketData(
            ticker=SEED_TARGET,
            avg_daily_volume=2_000_000,
            pre_earnings_runup_pct=4.0,
        )
    }

    options_chains = {
        SEED_TARGET: [
            OptionContractSnapshot(
                ticker=SEED_TARGET,
                option_type="CALL",
                expiration_date=target_earnings + timedelta(days=10),
                bid=4.85,
                ask=5.15,
                open_interest=250,
            )
        ]
    }

    return SeedInputs(
        current_date=current_date,
        universe=universe,
        upcoming_events=upcoming_events,
        peer_results=peer_results,
        target_market_data=target_market_data,
        options_chains=options_chains,
    )
