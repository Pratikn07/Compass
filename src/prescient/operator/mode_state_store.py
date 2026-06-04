from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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


class SupabaseModeStateStore:
    """Append-only Supabase-backed store. Current = newest accepted row.

    Fails safe: read_latest_accepted returns None on any read/parse error so
    callers default to propose_only. append_accepted lets write errors raise.
    """

    _TABLE = "operator_mode_authorizations"

    def __init__(self, *, client: Any, schema: str = "prescient_storage") -> None:
        self._client = client
        self._schema = schema

    def read_latest_accepted(self) -> ModeAuthorizationResult | None:
        try:
            response = (
                self._client.schema(self._schema)
                .table(self._TABLE)
                .select("*")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            return None

        rows = getattr(response, "data", None) or []
        if not rows:
            return None
        try:
            return ModeAuthorizationResult.model_validate(_row_to_result(rows[0]))
        except Exception:
            return None

    def append_accepted(self, result: ModeAuthorizationResult) -> None:
        row = _result_to_row(result)
        self._client.schema(self._schema).table(self._TABLE).insert(row).execute()

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str],
        create_client_factory: Any = None,
    ) -> "SupabaseModeStateStore":
        url = env.get("SUPABASE_URL", "").strip()
        key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        schema = env.get("PRESCIENT_STORAGE_SCHEMA", "prescient_storage").strip()
        factory = create_client_factory
        if factory is None:
            from supabase import create_client

            factory = create_client
        return cls(client=factory(url, key), schema=schema)


def _result_to_row(result: ModeAuthorizationResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "requested_mode": result.requested_mode.value,
        "previous_mode": result.previous_mode.value,
        "active_mode": result.active_mode.value,
        "actor": result.actor,
        "reason": result.reason,
        "rejection_reasons": list(result.rejection_reasons),
        "warnings": list(result.warnings),
        "created_at": result.created_at.isoformat(),
    }


def _row_to_result(row: dict[str, Any]) -> dict[str, Any]:
    # Map a stored row back to ModeAuthorizationResult fields. Extra DB-only
    # columns (id, schema_version) are dropped because the model forbids extras.
    return {
        "status": row["status"],
        "requested_mode": row["requested_mode"],
        "previous_mode": row["previous_mode"],
        "active_mode": row["active_mode"],
        "actor": row["actor"],
        "reason": row["reason"],
        "rejection_reasons": row.get("rejection_reasons") or [],
        "warnings": row.get("warnings") or [],
        "created_at": row["created_at"],
    }


DEFAULT_MODE_AUTHORIZATION_PATH = Path(".prescient/execution-mode.json")


def build_mode_state_store(
    *,
    env: Mapping[str, str],
    mode_path: str | Path | None = None,
    create_client_factory: Any = None,
) -> ModeStateStore:
    """Select the store. Explicit mode_path forces the file store (test/local
    seam). Otherwise, Supabase creds present -> Supabase; else file at the
    default path.
    """
    if mode_path is not None:
        return FileModeStateStore(Path(mode_path))

    has_supabase = bool(
        env.get("SUPABASE_URL", "").strip()
        and env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if has_supabase:
        return SupabaseModeStateStore.from_env(
            env=env, create_client_factory=create_client_factory
        )
    return FileModeStateStore(DEFAULT_MODE_AUTHORIZATION_PATH)
