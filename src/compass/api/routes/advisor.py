from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from compass.api.auth import require_owner
from compass.api.dependencies import Repository

router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])


@router.get("/themes")
def themes(repository: Repository) -> list[dict[str, object]]:
    return repository.list_themes()


@router.get("/themes/{slug}")
def theme_detail(
    slug: str,
    repository: Repository,
    days: int = Query(default=365, ge=1, le=2_000),
) -> dict[str, object]:
    theme = repository.theme_detail(slug, days=days)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.get("/recommendations/today")
def recommendations_today(repository: Repository) -> dict[str, object]:
    return repository.recommendations_today()


@router.get("/journal")
def journal(
    repository: Repository,
    days: int = Query(default=90, ge=1, le=3_650),
) -> dict[str, object]:
    return repository.journal(days=days)
