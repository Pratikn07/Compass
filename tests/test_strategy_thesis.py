from __future__ import annotations

from datetime import date

import pytest

from prescient.signal.models import EarningsEvent, PeerResult, ThemeConfig, ThesisStatus
from prescient.signal.strategy_types import StrategyType
from prescient.signal.thesis import build_strategy_thesis


def _ai_storage_theme() -> ThemeConfig:
    return ThemeConfig(
        name="AI_STORAGE",
        tickers=["NTAP", "PSTG", "WDC", "STX", "NTNX"],
        drivers=[
            "AI data center demand",
            "enterprise storage growth",
            "cloud infrastructure spend",
        ],
    )


def _positive_peer(ticker: str, reported_on: date = date(2026, 5, 20)) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=reported_on,
            report_time="AMC",
            eps_estimate=1.0,
            eps_actual=1.2,
            revenue_estimate=1_000.0,
            revenue_actual=1_100.0,
        ),
        guidance_signal="positive",
        theme_driver_signal="positive",
    )


def test_builds_valid_bullish_readthrough_thesis_with_enough_positive_peers() -> None:
    thesis = build_strategy_thesis(
        target="NTNX",
        theme=_ai_storage_theme(),
        peer_results=[
            _positive_peer("NTAP"),
            _positive_peer("PSTG"),
            _positive_peer("WDC"),
            _positive_peer("STX"),
        ],
    )

    assert thesis.status == ThesisStatus.VALID
    assert thesis.target == "NTNX"
    assert thesis.theme == "AI_STORAGE"
    assert thesis.strategy_type == StrategyType.BULLISH_EARNINGS_READTHROUGH
    assert thesis.direction == "bullish"
    assert thesis.reported_peers == ["NTAP", "PSTG", "WDC", "STX"]
    assert thesis.positive_peer_count == 4
    assert thesis.minimum_peer_count == 3
    assert "AI data center demand" in thesis.shared_drivers
    assert thesis.reason == (
        "Bullish peer read-through thesis: 4 peers in AI_STORAGE reported positive "
        "earnings or theme-driver evidence around shared drivers."
    )


def test_rejects_target_outside_configured_theme() -> None:
    thesis = build_strategy_thesis(
        target="NVDA",
        theme=_ai_storage_theme(),
        peer_results=[
            _positive_peer("NTAP"),
            _positive_peer("PSTG"),
            _positive_peer("WDC"),
        ],
    )

    assert thesis.status == ThesisStatus.INVALID_THEME
    assert thesis.reason == "Target NVDA is not configured in theme AI_STORAGE."


def test_rejects_when_peer_context_is_insufficient() -> None:
    thesis = build_strategy_thesis(
        target="NTNX",
        theme=_ai_storage_theme(),
        peer_results=[_positive_peer("NTAP")],
    )

    assert thesis.status == ThesisStatus.INSUFFICIENT_PEER_CONTEXT
    assert thesis.reported_peers == ["NTAP"]
    assert thesis.positive_peer_count == 1
    assert thesis.reason == (
        "Only 1 positive peer result available; 3 are required for a strategy thesis."
    )


def test_excludes_target_if_it_appears_in_peer_results() -> None:
    thesis = build_strategy_thesis(
        target="NTNX",
        theme=_ai_storage_theme(),
        peer_results=[
            _positive_peer("NTNX"),
            _positive_peer("NTAP"),
            _positive_peer("PSTG"),
            _positive_peer("WDC"),
        ],
    )

    assert thesis.status == ThesisStatus.VALID
    assert thesis.reported_peers == ["NTAP", "PSTG", "WDC"]
    assert "NTNX" not in thesis.reported_peers


def test_preserves_shared_demand_drivers_from_theme() -> None:
    thesis = build_strategy_thesis(
        target="NTNX",
        theme=_ai_storage_theme(),
        peer_results=[
            _positive_peer("NTAP"),
            _positive_peer("PSTG"),
            _positive_peer("WDC"),
        ],
    )

    assert thesis.shared_drivers == [
        "AI data center demand",
        "enterprise storage growth",
        "cloud infrastructure spend",
    ]


def test_same_input_produces_equal_serialized_output() -> None:
    target = "NTNX"
    theme = _ai_storage_theme()
    peer_results = [
        _positive_peer("NTAP"),
        _positive_peer("PSTG"),
        _positive_peer("WDC"),
    ]

    first = build_strategy_thesis(target=target, theme=theme, peer_results=peer_results)
    second = build_strategy_thesis(target=target, theme=theme, peer_results=peer_results)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_explicit_bullish_strategy_matches_default_strategy() -> None:
    target = "NTNX"
    theme = _ai_storage_theme()
    peer_results = [
        _positive_peer("NTAP"),
        _positive_peer("PSTG"),
        _positive_peer("WDC"),
    ]

    default_thesis = build_strategy_thesis(target=target, theme=theme, peer_results=peer_results)
    explicit_thesis = build_strategy_thesis(
        target=target,
        theme=theme,
        peer_results=peer_results,
        strategy_type="bullish_earnings_readthrough",
    )

    assert explicit_thesis.model_dump(mode="json") == default_thesis.model_dump(mode="json")


def test_rejects_planned_strategy_types_before_running_bullish_logic() -> None:
    thesis = build_strategy_thesis(
        target="NTNX",
        theme=_ai_storage_theme(),
        peer_results=[
            _positive_peer("NTAP"),
            _positive_peer("PSTG"),
            _positive_peer("WDC"),
        ],
        strategy_type=StrategyType.BEARISH_EARNINGS_READTHROUGH,
    )

    assert thesis.status == ThesisStatus.UNSUPPORTED_STRATEGY
    assert thesis.strategy_type == StrategyType.BEARISH_EARNINGS_READTHROUGH
    assert thesis.direction == "bearish"
    assert thesis.reported_peers == []
    assert thesis.positive_peer_count == 0
    assert thesis.reason == (
        "Strategy bearish_earnings_readthrough is planned but not executable in the MVP."
    )


def test_rejects_invalid_strategy_type_deterministically() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy type: day_trade_breakout"):
        build_strategy_thesis(
            target="NTNX",
            theme=_ai_storage_theme(),
            peer_results=[
                _positive_peer("NTAP"),
                _positive_peer("PSTG"),
                _positive_peer("WDC"),
            ],
            strategy_type="day_trade_breakout",
        )
