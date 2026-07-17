"""Fetch-once on-disk JSON cache for reproducible provider reads.

Keys are hashed to safe filenames. Callers must only store normalized,
secret-free data — never raw URLs containing API keys.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import CACHE_DIR


class JsonFileCache:
    def __init__(self, directory: str | Path = CACHE_DIR) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

    def put(self, key: str, value: Any) -> None:
        self._path(key).write_text(json.dumps(value), encoding="utf-8")
