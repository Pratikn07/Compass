"""Environment access and shared paths for compass."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / ".cache"

load_dotenv(REPO_ROOT / ".env")

# Backtests and coverage measure from this date (rulebook §5.2).
DEVELOPMENT_START = "2006-01-01"


def require_env(name: str) -> str:
    """Return the env var or raise a clear error naming the missing var."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value
