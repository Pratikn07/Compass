from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, field_validator


class UniverseRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_market_cap_usd: float
    min_option_open_interest: int
    min_years_history: int
    description: str = ""


class EdgeUniverse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tickers: list[str]
    rule: UniverseRule

    @field_validator("tickers")
    @classmethod
    def normalize_and_validate(cls, value: list[str]) -> list[str]:
        normalized = [t.strip().upper() for t in value if t.strip()]
        if not normalized:
            raise ValueError("Edge universe must contain at least one ticker.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Edge universe tickers must be unique.")
        return normalized


def load_edge_universe(path: str | Path) -> EdgeUniverse:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError("Edge universe config must be a mapping.")
    return EdgeUniverse(
        tickers=raw.get("tickers", []),
        rule=UniverseRule(**(raw.get("rule") or {})),
    )
