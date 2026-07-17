from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from compass.api.auth import require_owner
from compass.api.dependencies import Repository

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready")
def ready(repository: Repository):
    try:
        repository.ping()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unready", "database": "error"},
        )
    return {"status": "ready", "database": "ok"}


@router.get("/health", dependencies=[Depends(require_owner)])
def health(repository: Repository) -> dict[str, object]:
    return repository.detailed_health()
