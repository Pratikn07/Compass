from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from compass.api.auth import require_owner
from compass.api.dependencies import Repository

router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])


@router.get("/runs")
def runs(
    repository: Repository,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, object]:
    items, next_cursor = repository.list_runs(limit=limit, cursor=cursor)
    return {"items": items, "next_cursor": next_cursor}


@router.get("/providers/health")
def provider_health(repository: Repository) -> dict[str, object]:
    return repository.provider_health()


@router.get("/system-health")
def system_health(repository: Repository) -> list[dict[str, object]]:
    return repository.system_health()
