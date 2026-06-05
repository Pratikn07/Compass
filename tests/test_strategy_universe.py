from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from prescient.signal.models import StrategyUniverse, ThemeConfig
from prescient.signal.universe import (
    build_watchlist_seed_rows,
    load_strategy_universe,
    parse_strategy_universe,
)


def test_loads_current_themes_config() -> None:
    universe = load_strategy_universe(Path("config/themes.yaml"))

    assert universe.get_theme("AI_STORAGE").tickers == ["NTAP", "PSTG", "WDC", "STX", "NTNX"]
    assert universe.get_theme("SEMICONDUCTORS").drivers == [
        "AI accelerator demand",
        "data center capex",
        "memory pricing",
    ]


def test_normalizes_lowercase_theme_names_and_tickers() -> None:
    universe = parse_strategy_universe(
        {
            "themes": {
                "ai_storage": {
                    "tickers": ["ntap", "pstg"],
                    "drivers": ["AI data center demand"],
                }
            }
        }
    )

    assert universe.get_theme("ai_storage").name == "AI_STORAGE"
    assert universe.get_theme("AI_STORAGE").tickers == ["NTAP", "PSTG"]
    assert universe.contains_ticker("ntap")


def test_rejects_missing_top_level_themes() -> None:
    with pytest.raises(ValueError, match="Strategy universe config must contain a 'themes' mapping."):
        parse_strategy_universe({})


def test_rejects_theme_with_fewer_than_two_tickers() -> None:
    with pytest.raises(ValidationError, match="Theme must contain at least 2 tickers."):
        StrategyUniverse(themes=[ThemeConfig(name="AI_STORAGE", tickers=["NTAP"])])


def test_rejects_duplicate_tickers_inside_same_theme() -> None:
    with pytest.raises(ValidationError, match="Theme tickers must not contain duplicates."):
        ThemeConfig(name="AI_STORAGE", tickers=["NTAP", "ntap"])


def test_allows_same_ticker_in_multiple_themes() -> None:
    universe = StrategyUniverse(
        themes=[
            ThemeConfig(name="AI_STORAGE", tickers=["NTAP", "PSTG"], drivers=[]),
            ThemeConfig(name="ENTERPRISE_HARDWARE", tickers=["NTAP", "DELL"], drivers=[]),
        ]
    )

    assert [theme.name for theme in universe.themes_for_ticker("ntap")] == [
        "AI_STORAGE",
        "ENTERPRISE_HARDWARE",
    ]


def test_finds_all_themes_for_a_ticker() -> None:
    universe = parse_strategy_universe(
        {
            "themes": {
                "AI_STORAGE": {"tickers": ["NTAP", "PSTG"], "drivers": []},
                "CLOUD_INFRA": {"tickers": ["NTAP", "DDOG"], "drivers": []},
            }
        }
    )

    assert [theme.name for theme in universe.themes_for_ticker("NTAP")] == [
        "AI_STORAGE",
        "CLOUD_INFRA",
    ]


def test_returns_sorted_unique_ticker_universe() -> None:
    universe = StrategyUniverse(
        themes=[
            ThemeConfig(name="AI_STORAGE", tickers=["PSTG", "NTAP"], drivers=[]),
            ThemeConfig(name="ENTERPRISE_HARDWARE", tickers=["DELL", "NTAP"], drivers=[]),
        ]
    )

    assert universe.all_tickers() == ["DELL", "NTAP", "PSTG"]


def test_unknown_ticker_is_outside_universe() -> None:
    universe = StrategyUniverse(
        themes=[ThemeConfig(name="AI_STORAGE", tickers=["NTAP", "PSTG"], drivers=[])]
    )

    assert not universe.contains_ticker("NVDA")
    assert universe.themes_for_ticker("NVDA") == []


def test_universe_does_not_expand_strategy_types() -> None:
    universe = StrategyUniverse(
        themes=[ThemeConfig(name="AI_STORAGE", tickers=["NTAP", "PSTG"], drivers=[])]
    )

    assert universe.model_dump(mode="json") == {
        "themes": [
            {
                "name": "AI_STORAGE",
                "tickers": ["NTAP", "PSTG"],
                "drivers": [],
            }
        ]
    }


def test_builds_read_only_watchlist_seed_rows_from_universe() -> None:
    universe = StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTAP", "PSTG"],
                drivers=["AI data center demand"],
            )
        ]
    )

    watchlists, items = build_watchlist_seed_rows(universe)

    assert watchlists == [
        {
            "watchlist_id": "theme:AI_STORAGE",
            "name": "AI STORAGE",
            "description": "AI data center demand",
            "source": "strategy_universe",
            "schema_version": 1,
        }
    ]
    assert items == [
        {
            "watchlist_item_id": "theme:AI_STORAGE:NTAP",
            "watchlist_id": "theme:AI_STORAGE",
            "ticker": "NTAP",
            "theme": "AI_STORAGE",
            "sort_order": 0,
            "schema_version": 1,
        },
        {
            "watchlist_item_id": "theme:AI_STORAGE:PSTG",
            "watchlist_id": "theme:AI_STORAGE",
            "ticker": "PSTG",
            "theme": "AI_STORAGE",
            "sort_order": 1,
            "schema_version": 1,
        },
    ]
