from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from prescient.operator.models import ModeAuthorizationResult


@runtime_checkable
class ModeStateStore(Protocol):
    """Persistence boundary for operator execution-mode authorizations.

    Implementations must fail safe: read_latest_accepted returns None on any
    unreadable state (callers default to propose_only). append_accepted must
    raise on persistence failure (never silently succeed).
    """

    def read_latest_accepted(self) -> ModeAuthorizationResult | None: ...

    def append_accepted(self, result: ModeAuthorizationResult) -> None: ...


class FileModeStateStore:
    """Stores the latest accepted authorization in a single JSON file.

    Matches the historical .prescient/execution-mode.json behavior: the file
    holds the most recent accepted authorization (append overwrites).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read_latest_accepted(self) -> ModeAuthorizationResult | None:
        if not self._path.exists():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return ModeAuthorizationResult.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

    def append_accepted(self, result: ModeAuthorizationResult) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_name(f".{self._path.name}.tmp")
        tmp_path.write_text(result.model_dump_json(), encoding="utf-8")
        os.replace(tmp_path, self._path)
