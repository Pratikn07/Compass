# Prescient Web Frontend — Slice 3 (Runs + System Status) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the authenticated `/runs` system-status screen with latest scheduler/storage status, execution-mode status, daily-halt visibility, provider errors, and the first guarded operator action: a mode-authorization request that goes through a Next route handler and a Python action endpoint.

**Architecture:** The browser keeps read-only database access through Supabase for status data already written to `prescient_storage`. Operator actions never write to Supabase from the browser: the `/runs` page calls a Next App Router route handler, the handler verifies the Supabase session server-side, then forwards the request to a small Python FastAPI action endpoint protected by a server-only bearer token. The Python endpoint owns execution-mode authorization state and refuses unsafe live-mode authorization by default.

**Tech Stack:** Existing Slice 0-2 stack: Next.js App Router + TypeScript, Tailwind, shadcn-style primitives, TanStack Query v5, `@supabase/supabase-js`, `@supabase/ssr`, Zod, Vitest + React Testing Library. New backend action endpoint: FastAPI + Uvicorn, Pydantic models, pytest. Existing Python runtime remains Python >=3.11 with `uv`.

**Reference spec:** `docs/superpowers/specs/2026-06-03-prescient-web-frontend-design.md`

> **Prerequisites:** Execute this only after Slice 0, Slice 1, and Slice 2 exist and pass. This plan assumes `web/`, Supabase clients, authenticated `(app)` layout, design primitives, state components, decision list, and decision chain are already in place.

> **Git note:** The earlier Slice 0 plan recorded the operator decision to defer git. If `prescient/` is still not a git repository, skip every `git add` / `git commit` step and treat each task ending as a logical checkpoint.

---

## Slice Boundary

Slice 3 builds:

- `/runs` system-status screen.
- Supabase read hooks for:
  - latest rows from `prescient_storage.runs`
  - recent rows from `prescient_storage.provider_errors`
  - recent rows from `prescient_storage.storage_write_audit`
  - latest daily-halt signal inferred from `risk_decision` journal records
- server-only Next route handlers:
  - `GET /api/operator/status`
  - `POST /api/operator/mode-authorization`
- Python operator action endpoint:
  - `GET /status`
  - `POST /mode-authorization`
- audited execution-mode authorization file under `.prescient/execution-mode.json`

Slice 3 does not build:

- kill-switch activate/reset UI
- buy/sell/approve/size buttons
- live-mode enablement by default
- websocket/live streaming
- backtest charts

---

## File Structure

New and modified files:

```
pyproject.toml
src/prescient/operator/
  __init__.py                       # public exports
  models.py                         # operator status + mode authorization models
  mode_authorization.py             # code-owned mode authorization rules + file state
  api.py                            # FastAPI action endpoint
tests/
  test_operator_mode_authorization.py
  test_operator_api.py

web/.env.local.example              # add server-only operator API vars
web/package.json                    # add lucide-react if not already installed
web/src/app/api/operator/status/route.ts
web/src/app/api/operator/mode-authorization/route.ts
web/src/app/(app)/runs/page.tsx
web/src/components/runs/
  mode-authorization-panel.tsx
  provider-errors-table.tsx
  runs-summary-cards.tsx
  storage-audit-table.tsx
web/src/lib/operator/
  schemas.ts
  client.ts
  hooks.ts
web/src/lib/runs/
  schemas.ts
  queries.ts
  hooks.ts
web/__tests__/
  operator-routes.test.ts
  runs-schemas.test.ts
  runs-page.test.tsx
```

Boundary notes:

- Python `prescient.operator` owns mode authorization. It is deliberately separate from `prescient.broker` and `prescient.risk`; it can import their enums and safety state, but it does not size, approve, or place trades.
- Next route handlers are a backend-for-frontend layer only. They verify the Supabase user and hold `PRESCIENT_OPERATOR_API_TOKEN`; they do not hold or expose Supabase `service_role`.
- Browser hooks call only Supabase read APIs and local Next route handlers. They never call the Python endpoint directly.

---

## Task 1: Backend Dependency + Operator Package Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/prescient/operator/__init__.py`

- [ ] **Step 1: Add FastAPI runtime dependencies**

Modify `pyproject.toml` dependencies:

```toml
    "supabase>=2,<3",       # R6.4 backend-only Supabase storage adapter
    "fastapi>=0.115",       # operator action endpoint behind Next route handlers
    "uvicorn[standard]>=0.30", # local ASGI server for operator actions
```

- [ ] **Step 2: Sync the Python environment**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv sync
```

Expected: lockfile updates and FastAPI/Uvicorn install without resolver errors.

- [ ] **Step 3: Create the operator package export**

Create `src/prescient/operator/__init__.py`:

```python
from prescient.operator.mode_authorization import (
    DEFAULT_MODE_AUTHORIZATION_PATH,
    LIVE_CONFIRMATION_TEXT,
    authorize_execution_mode,
    read_operator_status,
)
from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
    OperatorStatus,
)

__all__ = [
    "DEFAULT_MODE_AUTHORIZATION_PATH",
    "LIVE_CONFIRMATION_TEXT",
    "ModeAuthorizationRequest",
    "ModeAuthorizationResult",
    "ModeAuthorizationStatus",
    "OperatorStatus",
    "authorize_execution_mode",
    "read_operator_status",
]
```

- [ ] **Step 4: Run import smoke test**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run python - <<'PY'
import prescient.operator
print("operator package ok")
PY
```

Expected:

```text
operator package ok
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/prescient/operator/__init__.py
git commit -m "feat(operator): add operator action package skeleton"
```

---

## Task 2: Backend Mode Authorization Models

**Files:**
- Create: `src/prescient/operator/models.py`
- Test: `tests/test_operator_mode_authorization.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_operator_mode_authorization.py` with these first tests:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
)
from prescient.risk.models import ExecutionMode


def test_mode_authorization_request_cleans_actor_and_reason() -> None:
    request = ModeAuthorizationRequest(
        requested_mode=ExecutionMode.PAPER,
        actor=" operator@example.com ",
        reason=" validate broker sandbox ",
    )

    assert request.actor == "operator@example.com"
    assert request.reason == "validate broker sandbox"


def test_mode_authorization_request_rejects_empty_reason() -> None:
    with pytest.raises(ValueError, match="reason is required"):
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.PAPER,
            actor="operator@example.com",
            reason=" ",
        )


def test_mode_authorization_result_serializes_execution_mode_values() -> None:
    result = ModeAuthorizationResult(
        status=ModeAuthorizationStatus.ACCEPTED,
        requested_mode=ExecutionMode.PAPER,
        previous_mode=ExecutionMode.PROPOSE_ONLY,
        active_mode=ExecutionMode.PAPER,
        actor="operator@example.com",
        reason="paper validation",
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )

    dumped = result.model_dump(mode="json")

    assert dumped["requested_mode"] == "paper"
    assert dumped["previous_mode"] == "propose_only"
    assert dumped["active_mode"] == "paper"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_mode_authorization.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing model classes.

- [ ] **Step 3: Create the models**

Create `src/prescient/operator/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from prescient.risk.models import ExecutionMode
from prescient.safety.models import KillSwitchState


class ModeAuthorizationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ModeAuthorizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_mode: ExecutionMode
    actor: str
    reason: str
    confirmation_text: str | None = None

    @field_validator("actor", "reason", "confirmation_text")
    @classmethod
    def clean_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned and info.field_name in {"actor", "reason"}:
            raise ValueError(f"{info.field_name} is required.")
        return cleaned or None


class ModeAuthorizationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ModeAuthorizationStatus
    requested_mode: ExecutionMode
    previous_mode: ExecutionMode
    active_mode: ExecutionMode
    actor: str
    reason: str
    created_at: datetime
    rejection_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OperatorStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_mode: ExecutionMode
    mode_source: str
    kill_switch: KillSwitchState
    latest_mode_authorization: ModeAuthorizationResult | None = None
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run model tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_mode_authorization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/models.py tests/test_operator_mode_authorization.py
git commit -m "feat(operator): add mode authorization models"
```

---

## Task 3: Backend Mode Authorization Service

**Files:**
- Create: `src/prescient/operator/mode_authorization.py`
- Modify: `tests/test_operator_mode_authorization.py`

- [ ] **Step 1: Add failing service tests**

Append these tests to `tests/test_operator_mode_authorization.py`:

```python
from pathlib import Path

from prescient.operator.mode_authorization import (
    LIVE_CONFIRMATION_TEXT,
    authorize_execution_mode,
    read_operator_status,
)
from prescient.safety import KillSwitchStatus


def test_operator_status_defaults_to_propose_only_and_inactive_kill_switch(tmp_path: Path) -> None:
    status = read_operator_status(
        mode_path=tmp_path / "execution-mode.json",
        kill_switch_path=tmp_path / "kill-switch.json",
        env={},
    )

    assert status.execution_mode == ExecutionMode.PROPOSE_ONLY
    assert status.mode_source == "default"
    assert status.kill_switch.status == KillSwitchStatus.INACTIVE


def test_authorizing_paper_writes_mode_state(tmp_path: Path) -> None:
    mode_path = tmp_path / "execution-mode.json"

    result = authorize_execution_mode(
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.PAPER,
            actor="operator@example.com",
            reason="paper validation",
        ),
        mode_path=mode_path,
        env={},
    )

    assert result.status == ModeAuthorizationStatus.ACCEPTED
    assert result.previous_mode == ExecutionMode.PROPOSE_ONLY
    assert result.active_mode == ExecutionMode.PAPER

    status = read_operator_status(mode_path=mode_path, env={})
    assert status.execution_mode == ExecutionMode.PAPER
    assert status.mode_source == "file"


def test_invalid_mode_file_fails_closed_to_propose_only(tmp_path: Path) -> None:
    mode_path = tmp_path / "execution-mode.json"
    mode_path.write_text("{not-json", encoding="utf-8")

    status = read_operator_status(mode_path=mode_path, env={})

    assert status.execution_mode == ExecutionMode.PROPOSE_ONLY
    assert status.mode_source == "default"
    assert any("unreadable" in warning for warning in status.warnings)


def test_live_mode_is_rejected_by_default_even_with_confirmation(tmp_path: Path) -> None:
    result = authorize_execution_mode(
        ModeAuthorizationRequest(
            requested_mode=ExecutionMode.LIVE,
            actor="operator@example.com",
            reason="testing live guard",
            confirmation_text=LIVE_CONFIRMATION_TEXT,
        ),
        mode_path=tmp_path / "execution-mode.json",
        env={},
    )

    assert result.status == ModeAuthorizationStatus.REJECTED
    assert result.active_mode == ExecutionMode.PROPOSE_ONLY
    assert "live_mode_disabled" in result.rejection_reasons
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_mode_authorization.py -q
```

Expected: FAIL because `mode_authorization.py` does not exist yet.

- [ ] **Step 3: Implement mode authorization service**

Create `src/prescient/operator/mode_authorization.py`:

```python
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    ModeAuthorizationStatus,
    OperatorStatus,
)
from prescient.risk.models import ExecutionMode
from prescient.safety import get_kill_switch_state


DEFAULT_MODE_AUTHORIZATION_PATH = Path(".prescient/execution-mode.json")
LIVE_CONFIRMATION_TEXT = "AUTHORIZE LIVE TRADING"


def read_operator_status(
    *,
    mode_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> OperatorStatus:
    active_env = env if env is not None else os.environ
    warnings: list[str] = []
    mode, source, latest = _read_mode_state(
        path=Path(mode_path) if mode_path is not None else DEFAULT_MODE_AUTHORIZATION_PATH,
        env=active_env,
        warnings=warnings,
    )
    kill_switch = get_kill_switch_state(path=kill_switch_path, env=active_env)

    return OperatorStatus(
        execution_mode=mode,
        mode_source=source,
        kill_switch=kill_switch,
        latest_mode_authorization=latest,
        warnings=warnings,
    )


def authorize_execution_mode(
    request: ModeAuthorizationRequest,
    *,
    mode_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    allow_live: bool = False,
    now: datetime | None = None,
) -> ModeAuthorizationResult:
    path = Path(mode_path) if mode_path is not None else DEFAULT_MODE_AUTHORIZATION_PATH
    warnings: list[str] = []
    previous_mode, _, _ = _read_mode_state(path=path, env=env or {}, warnings=warnings)
    timestamp = now or datetime.now(timezone.utc)
    rejection_reasons = _mode_rejection_reasons(request, allow_live=allow_live)
    status = (
        ModeAuthorizationStatus.REJECTED
        if rejection_reasons
        else ModeAuthorizationStatus.ACCEPTED
    )
    active_mode = previous_mode if rejection_reasons else request.requested_mode

    result = ModeAuthorizationResult(
        status=status,
        requested_mode=request.requested_mode,
        previous_mode=previous_mode,
        active_mode=active_mode,
        actor=request.actor,
        reason=request.reason,
        created_at=timestamp,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )

    if status == ModeAuthorizationStatus.ACCEPTED:
        _write_mode_state(path, result)

    return result


def _mode_rejection_reasons(
    request: ModeAuthorizationRequest,
    *,
    allow_live: bool,
) -> list[str]:
    if request.requested_mode != ExecutionMode.LIVE:
        return []

    reasons: list[str] = []
    if not allow_live:
        reasons.append("live_mode_disabled")
    if request.confirmation_text != LIVE_CONFIRMATION_TEXT:
        reasons.append("live_confirmation_missing")
    return reasons


def _read_mode_state(
    *,
    path: Path,
    env: Mapping[str, str],
    warnings: list[str],
) -> tuple[ExecutionMode, str, ModeAuthorizationResult | None]:
    env_mode = (env.get("PRESCIENT_EXECUTION_MODE") or "").strip()
    if env_mode:
        try:
            return ExecutionMode(env_mode), "environment", None
        except ValueError:
            warnings.append("PRESCIENT_EXECUTION_MODE was invalid; defaulting to propose_only")
            return ExecutionMode.PROPOSE_ONLY, "default", None

    if not path.exists():
        return ExecutionMode.PROPOSE_ONLY, "default", None

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        latest = ModeAuthorizationResult.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError):
        warnings.append(f"mode authorization state unreadable at {path}")
        return ExecutionMode.PROPOSE_ONLY, "default", None

    if latest.status != ModeAuthorizationStatus.ACCEPTED:
        return ExecutionMode.PROPOSE_ONLY, "default", latest

    return latest.active_mode, "file", latest


def _write_mode_state(path: Path, result: ModeAuthorizationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(result.model_dump_json(), encoding="utf-8")
    tmp_path.replace(path)
```

- [ ] **Step 4: Run service tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_mode_authorization.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prescient/operator/mode_authorization.py tests/test_operator_mode_authorization.py
git commit -m "feat(operator): add guarded execution mode authorization"
```

---

## Task 4: Backend FastAPI Operator Endpoint

**Files:**
- Create: `src/prescient/operator/api.py`
- Test: `tests/test_operator_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_operator_api.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from prescient.operator.api import create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        token="test-token",
        mode_path=tmp_path / "execution-mode.json",
        kill_switch_path=tmp_path / "kill-switch.json",
        env={},
    )
    return TestClient(app)


def test_status_requires_bearer_token(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/status")

    assert response.status_code == 401


def test_status_returns_operator_state(tmp_path: Path) -> None:
    response = _client(tmp_path).get(
        "/status",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "propose_only"
    assert payload["kill_switch"]["status"] == "inactive"


def test_mode_authorization_uses_server_token_and_actor_from_payload(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/mode-authorization",
        headers={"Authorization": "Bearer test-token"},
        json={
            "requested_mode": "paper",
            "actor": "operator@example.com",
            "reason": "paper validation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["active_mode"] == "paper"


def test_live_mode_is_rejected_by_default(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/mode-authorization",
        headers={"Authorization": "Bearer test-token"},
        json={
            "requested_mode": "live",
            "actor": "operator@example.com",
            "reason": "try live",
            "confirmation_text": "AUTHORIZE LIVE TRADING",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert "live_mode_disabled" in payload["rejection_reasons"]
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_api.py -q
```

Expected: FAIL because `prescient.operator.api` does not exist.

- [ ] **Step 3: Implement the API**

Create `src/prescient/operator/api.py`:

```python
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status

from prescient.operator.mode_authorization import (
    DEFAULT_MODE_AUTHORIZATION_PATH,
    authorize_execution_mode,
    read_operator_status,
)
from prescient.operator.models import (
    ModeAuthorizationRequest,
    ModeAuthorizationResult,
    OperatorStatus,
)


def create_app(
    *,
    token: str | None = None,
    mode_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    allow_live: bool = False,
) -> FastAPI:
    app = FastAPI(title="prescient operator actions", version="0.1.0")
    active_env = env if env is not None else os.environ
    active_token = token or active_env.get("PRESCIENT_OPERATOR_API_TOKEN", "").strip()
    active_mode_path = Path(
        mode_path
        or active_env.get("PRESCIENT_MODE_AUTHORIZATION_PATH", "")
        or DEFAULT_MODE_AUTHORIZATION_PATH
    )
    active_kill_switch_path = kill_switch_path or active_env.get("PRESCIENT_KILL_SWITCH_PATH")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if not active_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="operator action token is not configured",
            )
        if authorization != f"Bearer {active_token}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid operator action token",
            )

    @app.get("/status", response_model=OperatorStatus)
    def get_status(_: None = Depends(require_token)) -> OperatorStatus:
        return read_operator_status(
            mode_path=active_mode_path,
            kill_switch_path=active_kill_switch_path,
            env=active_env,
        )

    @app.post("/mode-authorization", response_model=ModeAuthorizationResult)
    def post_mode_authorization(
        request: ModeAuthorizationRequest,
        _: None = Depends(require_token),
    ) -> ModeAuthorizationResult:
        return authorize_execution_mode(
            request,
            mode_path=active_mode_path,
            env=active_env,
            allow_live=allow_live,
        )

    return app


app = create_app()
```

- [ ] **Step 4: Run API tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Start endpoint manually**

Run in one terminal:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
PRESCIENT_OPERATOR_API_TOKEN=dev-operator-token \
uv run uvicorn prescient.operator.api:app --host 127.0.0.1 --port 8008
```

Run in another terminal:

```bash
curl -s http://127.0.0.1:8008/status \
  -H "Authorization: Bearer dev-operator-token"
```

Expected JSON includes:

```json
{"execution_mode":"propose_only","mode_source":"default","kill_switch":{"status":"inactive"}}
```

- [ ] **Step 6: Commit**

```bash
git add src/prescient/operator/api.py tests/test_operator_api.py
git commit -m "feat(operator): expose guarded action endpoint"
```

---

## Task 5: Next Operator Proxy Routes

**Files:**
- Modify: `web/.env.local.example`
- Create: `web/src/app/api/operator/status/route.ts`
- Create: `web/src/app/api/operator/mode-authorization/route.ts`
- Test: `web/__tests__/operator-routes.test.ts`

- [ ] **Step 1: Add server-only operator env vars**

Append to `web/.env.local.example`:

```bash
# Server-only operator action endpoint (do not prefix with NEXT_PUBLIC)
PRESCIENT_OPERATOR_API_URL=http://127.0.0.1:8008
PRESCIENT_OPERATOR_API_TOKEN=replace-with-local-operator-token
```

Then copy those values into local `web/.env.local` using a local dev token. Do not commit `web/.env.local`.

- [ ] **Step 2: Write failing route tests**

Create `web/__tests__/operator-routes.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

import { createClient } from "@/lib/supabase/server";
import { GET as getStatus } from "@/app/api/operator/status/route";
import { POST as postModeAuthorization } from "@/app/api/operator/mode-authorization/route";

const mockedCreateClient = vi.mocked(createClient);

function mockUser(email = "operator@example.com") {
  mockedCreateClient.mockResolvedValue({
    auth: {
      getUser: vi.fn().mockResolvedValue({
        data: { user: { id: "user-1", email } },
        error: null,
      }),
    },
  } as never);
}

describe("operator proxy routes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.PRESCIENT_OPERATOR_API_URL = "http://operator.test";
    process.env.PRESCIENT_OPERATOR_API_TOKEN = "server-token";
  });

  it("GET /api/operator/status requires an authenticated Supabase user", async () => {
    mockedCreateClient.mockResolvedValue({
      auth: {
        getUser: vi.fn().mockResolvedValue({
          data: { user: null },
          error: null,
        }),
      },
    } as never);

    const response = await getStatus();

    expect(response.status).toBe(401);
  });

  it("GET /api/operator/status forwards with the server-only token", async () => {
    mockUser();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ execution_mode: "propose_only" }),
    );

    const response = await getStatus();

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith("http://operator.test/status", {
      headers: { Authorization: "Bearer server-token" },
      cache: "no-store",
    });
  });

  it("POST /api/operator/mode-authorization forwards actor from the session", async () => {
    mockUser("operator@example.com");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ status: "accepted", active_mode: "paper" }),
    );

    const request = new Request("http://localhost/api/operator/mode-authorization", {
      method: "POST",
      body: JSON.stringify({
        requested_mode: "paper",
        reason: "paper validation",
      }),
    });

    const response = await postModeAuthorization(request);

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://operator.test/mode-authorization",
      expect.objectContaining({
        method: "POST",
        headers: {
          Authorization: "Bearer server-token",
          "Content-Type": "application/json",
        },
        cache: "no-store",
      }),
    );
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.actor).toBe("operator@example.com");
    expect(body.requested_mode).toBe("paper");
  });
});
```

- [ ] **Step 3: Run route tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- operator-routes.test.ts
```

Expected: FAIL because route files do not exist.

- [ ] **Step 4: Create `GET /api/operator/status` proxy**

Create `web/src/app/api/operator/status/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const operatorUrl = process.env.PRESCIENT_OPERATOR_API_URL;
  const operatorToken = process.env.PRESCIENT_OPERATOR_API_TOKEN;

  if (!operatorUrl || !operatorToken) {
    return NextResponse.json(
      { error: "Operator action endpoint is not configured" },
      { status: 503 },
    );
  }

  const response = await fetch(`${operatorUrl}/status`, {
    headers: { Authorization: `Bearer ${operatorToken}` },
    cache: "no-store",
  });

  const payload = await response.json().catch(() => ({
    error: "Operator endpoint returned malformed JSON",
  }));

  return NextResponse.json(payload, { status: response.status });
}
```

- [ ] **Step 5: Create `POST /api/operator/mode-authorization` proxy**

Create `web/src/app/api/operator/mode-authorization/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

const requestSchema = z.object({
  requested_mode: z.enum(["propose_only", "paper", "live"]),
  reason: z.string().trim().min(1),
  confirmation_text: z.string().trim().optional(),
});

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const operatorUrl = process.env.PRESCIENT_OPERATOR_API_URL;
  const operatorToken = process.env.PRESCIENT_OPERATOR_API_TOKEN;

  if (!operatorUrl || !operatorToken) {
    return NextResponse.json(
      { error: "Operator action endpoint is not configured" },
      { status: 503 },
    );
  }

  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid mode authorization request" },
      { status: 400 },
    );
  }

  const actor = user.email ?? user.id;
  const response = await fetch(`${operatorUrl}/mode-authorization`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${operatorToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...parsed.data,
      actor,
    }),
    cache: "no-store",
  });

  const payload = await response.json().catch(() => ({
    error: "Operator endpoint returned malformed JSON",
  }));

  return NextResponse.json(payload, { status: response.status });
}
```

- [ ] **Step 6: Run route tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- operator-routes.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/.env.local.example web/src/app/api/operator/ web/__tests__/operator-routes.test.ts
git commit -m "feat(web): proxy guarded operator actions through Next routes"
```

---

## Task 6: Runs + Operator Data Schemas and Hooks

**Files:**
- Create: `web/src/lib/operator/schemas.ts`
- Create: `web/src/lib/operator/client.ts`
- Create: `web/src/lib/operator/hooks.ts`
- Create: `web/src/lib/runs/schemas.ts`
- Create: `web/src/lib/runs/queries.ts`
- Create: `web/src/lib/runs/hooks.ts`
- Test: `web/__tests__/runs-schemas.test.ts`

- [ ] **Step 1: Install icon dependency if absent**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm install lucide-react
```

Expected: package installs and `package-lock.json` updates.

- [ ] **Step 2: Write failing schema tests**

Create `web/__tests__/runs-schemas.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  operatorStatusSchema,
  modeAuthorizationResultSchema,
} from "@/lib/operator/schemas";
import {
  runRowSchema,
  providerErrorRowSchema,
  dailyHaltFromRiskRecords,
} from "@/lib/runs/schemas";

describe("operator schemas", () => {
  it("parses operator status from the Python endpoint", () => {
    const parsed = operatorStatusSchema.parse({
      execution_mode: "propose_only",
      mode_source: "default",
      kill_switch: { status: "inactive", warnings: [] },
      latest_mode_authorization: null,
      warnings: [],
    });

    expect(parsed.executionMode).toBe("propose_only");
    expect(parsed.killSwitch.status).toBe("inactive");
  });

  it("parses rejected live mode authorization loudly", () => {
    const parsed = modeAuthorizationResultSchema.parse({
      status: "rejected",
      requested_mode: "live",
      previous_mode: "propose_only",
      active_mode: "propose_only",
      actor: "operator@example.com",
      reason: "try live",
      created_at: "2026-06-04T12:00:00Z",
      rejection_reasons: ["live_mode_disabled"],
      warnings: [],
    });

    expect(parsed.status).toBe("rejected");
    expect(parsed.rejectionReasons).toContain("live_mode_disabled");
  });
});

describe("runs schemas", () => {
  it("parses latest run rows", () => {
    const parsed = runRowSchema.parse({
      run_id: "scheduled:2026-06-04",
      trigger_type: "scheduled",
      scheduled_date: "2026-06-04",
      current_date: "2026-06-04",
      window_start: "2026-06-04",
      window_end: "2026-06-06",
      status: "completed",
      payload: { total_decision_count: 3 },
      schema_version: 1,
      created_at: "2026-06-04T12:00:00Z",
    });

    expect(parsed.runId).toBe("scheduled:2026-06-04");
    expect(parsed.status).toBe("completed");
  });

  it("parses provider errors without exposing sensitive payload assumptions", () => {
    const parsed = providerErrorRowSchema.parse({
      provider_error_id: "err-1",
      provider: "finnhub",
      error_type: "rate_limited",
      run_id: "scheduled:2026-06-04",
      target: "NTNX",
      source: "earnings",
      message: "rate limit",
      payload: {},
      schema_version: 1,
      created_at: "2026-06-04T12:00:00Z",
    });

    expect(parsed.provider).toBe("finnhub");
    expect(parsed.errorType).toBe("rate_limited");
  });

  it("infers daily halt from risk-decision audit payloads", () => {
    const dailyHalt = dailyHaltFromRiskRecords([
      {
        journal_record_id: "risk-1",
        record_type: "risk_decision",
        payload: {
          status: "blocked",
          risk_gate_decision: {
            status: "blocked",
            explanation: "Daily halt is active.",
            audit_trail: { rule_name: "daily_halt", reason: "daily_halt_active" },
          },
        },
        created_at: "2026-06-04T12:00:00Z",
      },
    ]);

    expect(dailyHalt.status).toBe("halted");
  });
});
```

- [ ] **Step 3: Run schema tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- runs-schemas.test.ts
```

Expected: FAIL because schema files do not exist.

- [ ] **Step 4: Create operator schemas**

Create `web/src/lib/operator/schemas.ts`:

```typescript
import { z } from "zod";

const executionModeSchema = z.enum(["propose_only", "paper", "live"]);

export const killSwitchSchema = z
  .object({
    status: z.enum(["inactive", "active"]),
    reason: z.string().nullable().optional(),
    activated_at: z.string().nullable().optional(),
    activated_by: z.string().nullable().optional(),
    reset_at: z.string().nullable().optional(),
    reset_by: z.string().nullable().optional(),
    warnings: z.array(z.string()).default([]),
  })
  .passthrough()
  .transform((value) => ({
    status: value.status,
    reason: value.reason ?? null,
    activatedAt: value.activated_at ?? null,
    activatedBy: value.activated_by ?? null,
    resetAt: value.reset_at ?? null,
    resetBy: value.reset_by ?? null,
    warnings: value.warnings,
  }));

export const modeAuthorizationResultSchema = z
  .object({
    status: z.enum(["accepted", "rejected"]),
    requested_mode: executionModeSchema,
    previous_mode: executionModeSchema,
    active_mode: executionModeSchema,
    actor: z.string(),
    reason: z.string(),
    created_at: z.string(),
    rejection_reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
  })
  .transform((value) => ({
    status: value.status,
    requestedMode: value.requested_mode,
    previousMode: value.previous_mode,
    activeMode: value.active_mode,
    actor: value.actor,
    reason: value.reason,
    createdAt: value.created_at,
    rejectionReasons: value.rejection_reasons,
    warnings: value.warnings,
  }));

export const operatorStatusSchema = z
  .object({
    execution_mode: executionModeSchema,
    mode_source: z.string(),
    kill_switch: killSwitchSchema,
    latest_mode_authorization: modeAuthorizationResultSchema.nullable().optional(),
    warnings: z.array(z.string()).default([]),
  })
  .transform((value) => ({
    executionMode: value.execution_mode,
    modeSource: value.mode_source,
    killSwitch: value.kill_switch,
    latestModeAuthorization: value.latest_mode_authorization ?? null,
    warnings: value.warnings,
  }));

export type OperatorStatus = z.infer<typeof operatorStatusSchema>;
export type ModeAuthorizationResult = z.infer<typeof modeAuthorizationResultSchema>;
export type ExecutionMode = z.infer<typeof executionModeSchema>;
```

- [ ] **Step 5: Create runs schemas**

Create `web/src/lib/runs/schemas.ts`:

```typescript
import { z } from "zod";

const payloadSchema = z.record(z.string(), z.unknown()).default({});

export const runRowSchema = z
  .object({
    run_id: z.string(),
    trigger_type: z.string().nullable(),
    scheduled_date: z.string().nullable(),
    current_date: z.string().nullable(),
    window_start: z.string().nullable(),
    window_end: z.string().nullable(),
    status: z.string().nullable(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    runId: value.run_id,
    triggerType: value.trigger_type,
    scheduledDate: value.scheduled_date,
    currentDate: value.current_date,
    windowStart: value.window_start,
    windowEnd: value.window_end,
    status: value.status ?? "unknown",
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export const providerErrorRowSchema = z
  .object({
    provider_error_id: z.string(),
    provider: z.string(),
    error_type: z.string(),
    run_id: z.string().nullable(),
    target: z.string().nullable(),
    source: z.string().nullable(),
    message: z.string(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    providerErrorId: value.provider_error_id,
    provider: value.provider,
    errorType: value.error_type,
    runId: value.run_id,
    target: value.target,
    source: value.source,
    message: value.message,
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export const storageAuditRowSchema = z
  .object({
    storage_write_audit_id: z.string(),
    provider: z.string(),
    table_name: z.string(),
    run_id: z.string().nullable(),
    attempted_record_count: z.number(),
    written_record_count: z.number(),
    error_count: z.number(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    storageWriteAuditId: value.storage_write_audit_id,
    provider: value.provider,
    tableName: value.table_name,
    runId: value.run_id,
    attemptedRecordCount: value.attempted_record_count,
    writtenRecordCount: value.written_record_count,
    errorCount: value.error_count,
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

const riskJournalRecordSchema = z.object({
  journal_record_id: z.string(),
  record_type: z.literal("risk_decision"),
  payload: z
    .object({
      status: z.string().optional(),
      risk_gate_decision: z
        .object({
          status: z.string().optional(),
          explanation: z.string().optional(),
          audit_trail: z
            .object({
              rule_name: z.string().optional(),
              reason: z.string().optional(),
            })
            .passthrough()
            .optional(),
        })
        .passthrough()
        .optional(),
    })
    .passthrough(),
  created_at: z.string(),
});

export function dailyHaltFromRiskRecords(records: unknown[]) {
  const parsed = z.array(riskJournalRecordSchema).parse(records);
  const halt = parsed.find((record) => {
    const risk = record.payload.risk_gate_decision;
    const ruleName = risk?.audit_trail?.rule_name;
    const explanation = risk?.explanation?.toLowerCase() ?? "";
    return ruleName === "daily_halt" || explanation.includes("daily halt is active");
  });

  if (!halt) {
    return { status: "allowed" as const, record: null, createdAt: null };
  }

  return {
    status: "halted" as const,
    record: halt,
    createdAt: halt.created_at,
  };
}

export type RunRow = z.infer<typeof runRowSchema>;
export type ProviderErrorRow = z.infer<typeof providerErrorRowSchema>;
export type StorageAuditRow = z.infer<typeof storageAuditRowSchema>;
```

- [ ] **Step 6: Create operator client and hooks**

Create `web/src/lib/operator/client.ts`:

```typescript
import {
  modeAuthorizationResultSchema,
  operatorStatusSchema,
  type ExecutionMode,
} from "@/lib/operator/schemas";

export async function fetchOperatorStatus() {
  const response = await fetch("/api/operator/status", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? "Unable to load operator status");
  }
  return operatorStatusSchema.parse(payload);
}

export async function requestModeAuthorization(input: {
  requestedMode: Exclude<ExecutionMode, "live">;
  reason: string;
}) {
  const response = await fetch("/api/operator/mode-authorization", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requested_mode: input.requestedMode,
      reason: input.reason,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? "Unable to request mode authorization");
  }
  return modeAuthorizationResultSchema.parse(payload);
}
```

Create `web/src/lib/operator/hooks.ts`:

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchOperatorStatus, requestModeAuthorization } from "@/lib/operator/client";

export function useOperatorStatus() {
  return useQuery({
    queryKey: ["operator-status"],
    queryFn: fetchOperatorStatus,
    refetchOnWindowFocus: true,
  });
}

export function useModeAuthorizationMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: requestModeAuthorization,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-status"] });
    },
  });
}
```

- [ ] **Step 7: Create Supabase query functions and hooks**

Create `web/src/lib/runs/queries.ts`:

```typescript
import { createClient } from "@/lib/supabase/client";
import {
  dailyHaltFromRiskRecords,
  providerErrorRowSchema,
  runRowSchema,
  storageAuditRowSchema,
} from "@/lib/runs/schemas";

export async function fetchLatestRuns(limit = 10) {
  const supabase = createClient();
  const { data, error } = await supabase
    .schema("prescient_storage")
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) throw new Error(error.message);
  return runRowSchema.array().parse(data ?? []);
}

export async function fetchRecentProviderErrors(limit = 20) {
  const supabase = createClient();
  const { data, error } = await supabase
    .schema("prescient_storage")
    .from("provider_errors")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) throw new Error(error.message);
  return providerErrorRowSchema.array().parse(data ?? []);
}

export async function fetchRecentStorageAudit(limit = 10) {
  const supabase = createClient();
  const { data, error } = await supabase
    .schema("prescient_storage")
    .from("storage_write_audit")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) throw new Error(error.message);
  return storageAuditRowSchema.array().parse(data ?? []);
}

export async function fetchDailyHaltStatus() {
  const supabase = createClient();
  const { data, error } = await supabase
    .schema("prescient_storage")
    .from("journal_records")
    .select("journal_record_id, record_type, payload, created_at")
    .eq("record_type", "risk_decision")
    .order("created_at", { ascending: false })
    .limit(50);

  if (error) throw new Error(error.message);
  return dailyHaltFromRiskRecords(data ?? []);
}
```

Create `web/src/lib/runs/hooks.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchDailyHaltStatus,
  fetchLatestRuns,
  fetchRecentProviderErrors,
  fetchRecentStorageAudit,
} from "@/lib/runs/queries";

export function useLatestRuns() {
  return useQuery({
    queryKey: ["runs", "latest"],
    queryFn: () => fetchLatestRuns(10),
    refetchOnWindowFocus: true,
  });
}

export function useRecentProviderErrors() {
  return useQuery({
    queryKey: ["runs", "provider-errors"],
    queryFn: () => fetchRecentProviderErrors(20),
    refetchOnWindowFocus: true,
  });
}

export function useRecentStorageAudit() {
  return useQuery({
    queryKey: ["runs", "storage-audit"],
    queryFn: () => fetchRecentStorageAudit(10),
    refetchOnWindowFocus: true,
  });
}

export function useDailyHaltStatus() {
  return useQuery({
    queryKey: ["runs", "daily-halt"],
    queryFn: fetchDailyHaltStatus,
    refetchOnWindowFocus: true,
  });
}
```

- [ ] **Step 8: Run schema tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- runs-schemas.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/package.json web/package-lock.json web/src/lib/operator/ web/src/lib/runs/ web/__tests__/runs-schemas.test.ts
git commit -m "feat(web): add runs and operator status data hooks"
```

---

## Task 7: `/runs` UI Components and Page

**Files:**
- Create: `web/src/components/runs/mode-authorization-panel.tsx`
- Create: `web/src/components/runs/provider-errors-table.tsx`
- Create: `web/src/components/runs/runs-summary-cards.tsx`
- Create: `web/src/components/runs/storage-audit-table.tsx`
- Modify/Create: `web/src/app/(app)/runs/page.tsx`
- Test: `web/__tests__/runs-page.test.tsx`

- [ ] **Step 1: Write failing page tests**

Create `web/__tests__/runs-page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/runs/hooks", () => ({
  useLatestRuns: () => ({
    isLoading: false,
    isError: false,
    data: [
      {
        runId: "scheduled:2026-06-04",
        triggerType: "scheduled",
        scheduledDate: "2026-06-04",
        currentDate: "2026-06-04",
        windowStart: "2026-06-04",
        windowEnd: "2026-06-06",
        status: "completed",
        payload: {},
        schemaVersion: 1,
        createdAt: "2026-06-04T12:00:00Z",
      },
    ],
  }),
  useRecentProviderErrors: () => ({
    isLoading: false,
    isError: false,
    data: [],
  }),
  useRecentStorageAudit: () => ({
    isLoading: false,
    isError: false,
    data: [],
  }),
  useDailyHaltStatus: () => ({
    isLoading: false,
    isError: false,
    data: { status: "allowed", record: null, createdAt: null },
  }),
}));

const mutate = vi.fn();

vi.mock("@/lib/operator/hooks", () => ({
  useOperatorStatus: () => ({
    isLoading: false,
    isError: false,
    data: {
      executionMode: "propose_only",
      modeSource: "default",
      killSwitch: { status: "inactive", reason: null, warnings: [] },
      latestModeAuthorization: null,
      warnings: [],
    },
  }),
  useModeAuthorizationMutation: () => ({
    mutate,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

import RunsPage from "@/app/(app)/runs/page";

describe("/runs page", () => {
  it("renders system status without trade execution actions", () => {
    render(<RunsPage />);

    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByText("scheduled:2026-06-04")).toBeInTheDocument();
    expect(screen.getByText("propose_only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /live/i })).not.toBeInTheDocument();
  });

  it("submits a guarded paper-mode request with a reason", async () => {
    const user = userEvent.setup();
    render(<RunsPage />);

    await user.type(screen.getByLabelText("Reason"), "paper validation");
    await user.click(screen.getByRole("button", { name: /request paper mode/i }));

    expect(mutate).toHaveBeenCalledWith({
      requestedMode: "paper",
      reason: "paper validation",
    });
  });
});
```

- [ ] **Step 2: Run page tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- runs-page.test.tsx
```

Expected: FAIL because components/page do not exist.

- [ ] **Step 3: Create summary cards**

Create `web/src/components/runs/runs-summary-cards.tsx`:

```tsx
import { AlertTriangle, CheckCircle2, Clock, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { OperatorStatus } from "@/lib/operator/schemas";
import type { RunRow } from "@/lib/runs/schemas";

export function RunsSummaryCards({
  latestRun,
  operatorStatus,
  dailyHalt,
  providerErrorCount,
}: {
  latestRun: RunRow | null;
  operatorStatus: OperatorStatus;
  dailyHalt: { status: "allowed" | "halted"; createdAt: string | null };
  providerErrorCount: number;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="size-4" aria-hidden="true" />
          Last run
        </div>
        <div className="mt-3 font-mono text-sm">{latestRun?.runId ?? "No runs yet"}</div>
        <div className="mt-2">
          <Badge variant={latestRun?.status === "completed" ? "success" : "muted"}>
            {latestRun?.status ?? "empty"}
          </Badge>
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Shield className="size-4" aria-hidden="true" />
          Execution mode
        </div>
        <div className="mt-3 font-mono text-sm">{operatorStatus.executionMode}</div>
        <p className="mt-2 text-xs text-muted-foreground">Source: {operatorStatus.modeSource}</p>
      </Card>

      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          {dailyHalt.status === "halted" ? (
            <AlertTriangle className="size-4" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="size-4" aria-hidden="true" />
          )}
          Daily halt
        </div>
        <div className="mt-3">
          <Badge variant={dailyHalt.status === "halted" ? "danger" : "success"}>
            {dailyHalt.status}
          </Badge>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {dailyHalt.createdAt ?? "No halt record found"}
        </p>
      </Card>

      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="size-4" aria-hidden="true" />
          Provider errors
        </div>
        <div className="mt-3 text-2xl font-semibold">{providerErrorCount}</div>
        <p className="mt-2 text-xs text-muted-foreground">Recent recorded errors</p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Create mode authorization panel**

Create `web/src/components/runs/mode-authorization-panel.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ShieldCheck, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/states/error-state";
import { useModeAuthorizationMutation } from "@/lib/operator/hooks";

export function ModeAuthorizationPanel() {
  const [reason, setReason] = useState("");
  const mutation = useModeAuthorizationMutation();
  const disabled = reason.trim().length === 0 || mutation.isPending;

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Mode authorization</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Requests go through the Python operator endpoint. Live mode is not offered here.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto]">
        <label className="grid gap-1 text-sm">
          Reason
          <Input
            aria-label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="paper validation"
          />
        </label>
        <Button
          type="button"
          disabled={disabled}
          onClick={() =>
            mutation.mutate({
              requestedMode: "paper",
              reason: reason.trim(),
            })
          }
        >
          <ShieldCheck className="size-4" aria-hidden="true" />
          Request paper mode
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={disabled}
          onClick={() =>
            mutation.mutate({
              requestedMode: "propose_only",
              reason: reason.trim(),
            })
          }
        >
          <Undo2 className="size-4" aria-hidden="true" />
          Return propose-only
        </Button>
      </div>

      {mutation.isError ? (
        <div className="mt-4">
          <ErrorState title="Mode request failed" message={mutation.error.message} />
        </div>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 5: Create provider errors and storage audit tables**

Create `web/src/components/runs/provider-errors-table.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ProviderErrorRow } from "@/lib/runs/schemas";

export function ProviderErrorsTable({ errors }: { errors: ProviderErrorRow[] }) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Provider errors</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Message</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {errors.map((error) => (
            <TableRow key={error.providerErrorId}>
              <TableCell className="font-medium">{error.provider}</TableCell>
              <TableCell>
                <Badge variant="warning">{error.errorType}</Badge>
              </TableCell>
              <TableCell>{error.target ?? "-"}</TableCell>
              <TableCell>{error.message}</TableCell>
              <TableCell>{error.createdAt}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

Create `web/src/components/runs/storage-audit-table.tsx`:

```tsx
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { StorageAuditRow } from "@/lib/runs/schemas";

export function StorageAuditTable({ rows }: { rows: StorageAuditRow[] }) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Storage writes</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead>Table</TableHead>
            <TableHead>Attempted</TableHead>
            <TableHead>Written</TableHead>
            <TableHead>Errors</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.storageWriteAuditId}>
              <TableCell className="font-medium">{row.provider}</TableCell>
              <TableCell>{row.tableName}</TableCell>
              <TableCell>{row.attemptedRecordCount}</TableCell>
              <TableCell>{row.writtenRecordCount}</TableCell>
              <TableCell>{row.errorCount}</TableCell>
              <TableCell>{row.createdAt}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 6: Create `/runs` page**

Create or replace `web/src/app/(app)/runs/page.tsx`:

```tsx
"use client";

import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { ModeAuthorizationPanel } from "@/components/runs/mode-authorization-panel";
import { ProviderErrorsTable } from "@/components/runs/provider-errors-table";
import { RunsSummaryCards } from "@/components/runs/runs-summary-cards";
import { StorageAuditTable } from "@/components/runs/storage-audit-table";
import { useOperatorStatus } from "@/lib/operator/hooks";
import {
  useDailyHaltStatus,
  useLatestRuns,
  useRecentProviderErrors,
  useRecentStorageAudit,
} from "@/lib/runs/hooks";

export default function RunsPage() {
  const runs = useLatestRuns();
  const providerErrors = useRecentProviderErrors();
  const storageAudit = useRecentStorageAudit();
  const dailyHalt = useDailyHaltStatus();
  const operatorStatus = useOperatorStatus();

  const loading =
    runs.isLoading ||
    providerErrors.isLoading ||
    storageAudit.isLoading ||
    dailyHalt.isLoading ||
    operatorStatus.isLoading;

  const firstError =
    runs.error ??
    providerErrors.error ??
    storageAudit.error ??
    dailyHalt.error ??
    operatorStatus.error;

  if (loading) {
    return <LoadingState message="Loading run status..." />;
  }

  if (firstError instanceof Error) {
    return <ErrorState title="Unable to load run status" message={firstError.message} />;
  }

  const latestRun = runs.data?.[0] ?? null;
  const errors = providerErrors.data ?? [];
  const audits = storageAudit.data ?? [];
  const halt = dailyHalt.data ?? { status: "allowed" as const, createdAt: null, record: null };

  if (!operatorStatus.data) {
    return <ErrorState title="Operator status unavailable" />;
  }

  return (
    <section className="grid gap-6">
      <div>
        <h1 className="text-xl font-semibold">Runs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Scheduler status, safety state, and provider health.
        </p>
      </div>

      <RunsSummaryCards
        latestRun={latestRun}
        operatorStatus={operatorStatus.data}
        dailyHalt={{ status: halt.status, createdAt: halt.createdAt }}
        providerErrorCount={errors.length}
      />

      <ModeAuthorizationPanel />

      {runs.data?.length ? null : <EmptyState message="No runs have been recorded yet." />}

      <div className="grid gap-6 xl:grid-cols-2">
        {errors.length ? (
          <ProviderErrorsTable errors={errors} />
        ) : (
          <EmptyState message="No recent provider errors." />
        )}
        {audits.length ? (
          <StorageAuditTable rows={audits} />
        ) : (
          <EmptyState message="No recent storage write audit rows." />
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 7: Run page tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- runs-page.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Run full frontend test suite**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/app/'(app)'/runs/page.tsx web/src/components/runs/ web/__tests__/runs-page.test.tsx
git commit -m "feat(web): add runs system status screen"
```

---

## Task 8: End-to-End Verification

**Files:** none

- [ ] **Step 1: Run Python tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_operator_mode_authorization.py tests/test_operator_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test && npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Start local Supabase**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase start
```

Expected: local Supabase is running; `web/.env.local` has matching URL and anon key from Slice 0.

- [ ] **Step 4: Start Python operator endpoint**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
PRESCIENT_OPERATOR_API_TOKEN=dev-operator-token \
uv run uvicorn prescient.operator.api:app --host 127.0.0.1 --port 8008
```

Expected: Uvicorn listens on `http://127.0.0.1:8008`.

- [ ] **Step 5: Start Next dev server**

Run in another terminal:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run dev
```

Expected: dev server starts on `http://localhost:3000`.

- [ ] **Step 6: Configure local operator env**

Ensure `web/.env.local` contains:

```bash
PRESCIENT_OPERATOR_API_URL=http://127.0.0.1:8008
PRESCIENT_OPERATOR_API_TOKEN=dev-operator-token
```

Restart `npm run dev` after editing env.

- [ ] **Step 7: Verify unauthenticated guard**

Open `http://localhost:3000/runs` in a fresh browser profile.

Expected: redirected to `/login`.

- [ ] **Step 8: Verify `/runs` after login**

Log in with the local operator account from Slice 0, then open:

```text
http://localhost:3000/runs
```

Expected:

- page heading `Runs`
- execution mode card shows `propose_only`
- kill switch/daily halt/provider status cards render
- provider errors empty state renders if no rows exist
- no buy/sell/approve/live buttons exist

- [ ] **Step 9: Verify guarded mode request**

On `/runs`:

1. Enter reason `paper validation`.
2. Click `Request paper mode`.
3. Refresh the page.

Expected:

- the request succeeds
- execution mode card shows `paper`
- `.prescient/execution-mode.json` exists
- the JSON file contains `"active_mode":"paper"`

- [ ] **Step 10: Verify live mode remains blocked by backend**

Run:

```bash
curl -s -X POST http://127.0.0.1:8008/mode-authorization \
  -H "Authorization: Bearer dev-operator-token" \
  -H "Content-Type: application/json" \
  -d '{"requested_mode":"live","actor":"operator@example.com","reason":"test live guard","confirmation_text":"AUTHORIZE LIVE TRADING"}'
```

Expected JSON includes:

```json
{"status":"rejected","active_mode":"paper","rejection_reasons":["live_mode_disabled"]}
```

- [ ] **Step 11: Final checkpoint**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest -q
cd web && npm test && npm run build
```

Expected: Python tests pass; frontend tests and build pass.

- [ ] **Step 12: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add -A
git commit -m "feat(web): complete runs system status slice"
```

---

## Definition of Done

- `/runs` is reachable only through the authenticated `(app)` layout.
- The page renders loading, error, empty, and populated states.
- The browser reads run/status data only through Supabase authenticated read access.
- The browser never writes to `prescient_storage`.
- Operator mode authorization goes browser → Next route handler → Python endpoint.
- Next route handlers verify the Supabase user and use only server-side operator env vars.
- Python mode authorization defaults to `propose_only`, accepts `paper` / `propose_only`, and rejects `live` by default.
- The `/runs` UI exposes no buy, sell, approve, size, or live-mode button.
- `uv run pytest -q`, `npm test`, and `npm run build` pass.

---

## Self-Review

**Spec coverage:**

- Spec §3 hard frontend rules: maintained. No trade actions, no client Claude, no frontend storage writes, no position sizing edits, no live button.
- Spec §4 architecture: preserved. Browser reads Supabase; guarded action goes through Next route handler to Python endpoint.
- Spec §5 shell: uses existing authenticated layout, nav, primitives, and three state components.
- Spec §7 data layer: uses typed hooks and Zod parsing for run/provider/storage/daily-halt data. Parse errors surface through `<ErrorState>`.
- Spec §9 Slice 3: implements scheduler/run status, execution mode, daily-halt status, provider errors, and first guarded mode-authorization action.

**Placeholder scan:** No unfinished-marker steps. Runtime secrets are represented as explicit local placeholders in env examples only and are intentionally not hardcoded.

**Type consistency:** Python uses `ExecutionMode` everywhere for mode state. Frontend schemas normalize snake_case API responses into camelCase UI types. Mutation input excludes `"live"` so the UI cannot offer live mode, while the route and backend still reject live requests defensively.
