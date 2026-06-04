from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore[import-untyped]

from prescient.signal.models import StrategyUniverse, ThemeConfig


def load_strategy_universe(path: str | Path) -> StrategyUniverse:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    if not isinstance(raw, Mapping):
        raise ValueError("Strategy universe config must contain a 'themes' mapping.")

    return parse_strategy_universe(raw)


def parse_strategy_universe(raw: Mapping[str, Any]) -> StrategyUniverse:
    raw_themes = raw.get("themes")
    if not isinstance(raw_themes, Mapping):
        raise ValueError("Strategy universe config must contain a 'themes' mapping.")

    themes: list[ThemeConfig] = []
    for name, theme_data in raw_themes.items():
        if not isinstance(theme_data, Mapping):
            raise ValueError("Each strategy universe theme must be a mapping.")
        themes.append(
            ThemeConfig(
                name=str(name),
                tickers=_list_value(theme_data, "tickers"),
                drivers=_list_value(theme_data, "drivers"),
            )
        )

    return StrategyUniverse(themes=themes)


def _list_value(data: Mapping[Any, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Theme field '{key}' must be a list.")
    return [str(item) for item in value]
