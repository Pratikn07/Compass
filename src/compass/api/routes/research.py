from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from compass.api.auth import require_owner
from compass.api.dependencies import Repository

router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])


@router.get("/backtests/latest")
def latest_backtest(repository: Repository) -> dict[str, object]:
    report = repository.latest_backtest()
    if report is None:
        raise HTTPException(status_code=404, detail="No backtest report is available")
    return report


@router.get("/decisions")
def decisions(
    repository: Repository,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, object]:
    items, next_cursor = repository.list_decisions(limit=limit, cursor=cursor)
    return {"items": items, "next_cursor": next_cursor}


@router.get("/decisions/{decision_id}")
def decision_detail(
    decision_id: str,
    repository: Repository,
) -> dict[str, object]:
    decision = repository.decision_detail(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision
