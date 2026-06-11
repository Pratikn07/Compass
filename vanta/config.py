"""Ticker universe, theme map, and environment access for vanta."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # loads .env at repo root if present

TARGET = "MU"


@dataclass(frozen=True)
class Ticker:
    symbol: str
    name: str
    theme: str
    role: str  # "target" | "rival" | "demand_driver"


UNIVERSE: list[Ticker] = [
    Ticker("MU", "Micron Technology", "AI Memory", "target"),
    Ticker("WDC", "Western Digital", "AI Memory", "rival"),
    Ticker("SNDK", "SanDisk", "AI Memory", "rival"),
    Ticker("NVDA", "NVIDIA", "AI Memory", "demand_driver"),
    Ticker("AMD", "Advanced Micro Devices", "AI Memory", "demand_driver"),
    Ticker("AVGO", "Broadcom", "AI Memory", "demand_driver"),
]


def require_env(name: str) -> str:
    """Return env var or raise a clear error naming the missing var."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value
