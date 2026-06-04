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
