from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

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


R2_4_PRD_PATH = Path("docs/prd/02-architecture-r2-4-deterministic-signal-engine-in-code-prd.md")


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC", "STX", "DELL"],
                drivers=["AI data center demand"],
            )
        ]
    )


def _upcoming_target(
    ticker: str = "NTNX",
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


def _negative_peer_result(ticker: str) -> PeerResult:
    return _peer_result(
        ticker,
        eps_actual=0.8,
        revenue_actual=900.0,
        price_reaction_pct=-4.0,
        guidance_signal="negative",
        theme_driver_signal="negative",
    )


def _target_data(
    *,
    ticker: str = "NTNX",
    avg_daily_volume: int | None = 2_000_000,
    pre_earnings_runup_pct: float | None = 4.0,
) -> TargetMarketData:
    return TargetMarketData(
        ticker=ticker,
        avg_daily_volume=avg_daily_volume,
        pre_earnings_runup_pct=pre_earnings_runup_pct,
    )


def _call_option(ticker: str = "NTNX") -> OptionContractSnapshot:
    return OptionContractSnapshot(
        ticker=ticker,
        option_type="CALL",
        expiration_date=date(2026, 6, 12),
        bid=4.85,
        ask=5.15,
        open_interest=250,
    )


def _strong_peer_results() -> list[PeerResult]:
    return [
        _peer_result("NTAP"),
        _peer_result("PSTG"),
        _peer_result("WDC"),
        _peer_result("STX"),
    ]


def test_r2_4_prd_exists_and_names_public_signal_entrypoint() -> None:
    prd = R2_4_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R2.4 Deterministic Signal Engine In Code" in prd
    assert "prescient.signal.core.evaluate_core_strategy" in prd
    assert "event triggers may call" in prd
    assert "must not duplicate peer scoring" in prd


def test_readme_names_deterministic_signal_engine_entrypoint() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "deterministic signal engine" in readme
    assert "evaluate_core_strategy" in readme
    assert "Claude-free" in readme


def test_evaluate_core_strategy_produces_identical_serialized_output() -> None:
    first = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_strong_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )
    second = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_strong_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert [decision.model_dump(mode="json") for decision in first] == [
        decision.model_dump(mode="json") for decision in second
    ]


def test_signal_package_has_no_cold_path_or_network_imports() -> None:
    forbidden_roots = {
        "anthropic",
        "alpaca",
        "httpx",
        "requests",
        "prescient.analyst",
        "prescient.runtime",
        "prescient.scheduler",
    }

    for path in Path("src/prescient/signal").glob("*.py"):
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
        ), f"{path} imports a cold-path or network dependency: {imports}"


def test_signal_package_has_no_hidden_clock_sleep_or_polling_loop() -> None:
    forbidden_calls = {
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.sleep",
        "asyncio.sleep",
    }

    for path in Path("src/prescient/signal").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert "while True" not in source
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                assert call_name not in forbidden_calls, (
                    f"{path} uses hidden clock/sleep call {call_name}"
                )


def test_out_of_universe_target_rejects_and_blocks_claude() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target(ticker="NVDA")],
        peer_results=_strong_peer_results(),
        target_market_data={"NVDA": _target_data(ticker="NVDA")},
        options_chains={"NVDA": [_call_option(ticker="NVDA")]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.THEME_NOT_CONFIGURED]
    assert decisions[0].candidate is None
    assert decisions[0].claude_analysis_allowed is False


def test_weak_peer_signal_rejects_and_blocks_claude() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[
            _peer_result("NTAP"),
            _negative_peer_result("PSTG"),
            _negative_peer_result("WDC"),
        ],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]
    assert decisions[0].candidate is None
    assert decisions[0].claude_analysis_allowed is False


def test_target_filter_failure_rejects_before_candidate_brief_creation() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_strong_peer_results(),
        target_market_data={"NTNX": _target_data(pre_earnings_runup_pct=12.5)},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.TARGET_ALREADY_OVEREXTENDED]
    assert decisions[0].candidate is None
    assert decisions[0].claude_analysis_allowed is False


def test_passing_setup_creates_candidate_brief_and_allows_claude_analysis() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=_strong_peer_results(),
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decisions[0].candidate is not None
    assert decisions[0].candidate.target == "NTNX"
    assert decisions[0].candidate.theme == "AI_STORAGE"
    assert decisions[0].candidate.recommended_expression == "CALL_OPTION"
    assert decisions[0].claude_analysis_allowed is True


def test_multiple_upcoming_events_return_independent_decisions_in_input_order() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[
            _upcoming_target(ticker="NTNX"),
            _upcoming_target(ticker="DELL"),
        ],
        peer_results=[
            *_strong_peer_results(),
            _peer_result("DELL"),
        ],
        target_market_data={
            "NTNX": _target_data(ticker="NTNX"),
            "DELL": _target_data(ticker="DELL", pre_earnings_runup_pct=14.0),
        },
        options_chains={
            "NTNX": [_call_option(ticker="NTNX")],
            "DELL": [_call_option(ticker="DELL")],
        },
        current_date=date(2026, 6, 1),
    )

    assert [decision.audit.target for decision in decisions] == ["NTNX", "DELL"]
    assert decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decisions[1].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[1].rejection_reasons == [RejectionReason.TARGET_ALREADY_OVEREXTENDED]


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
