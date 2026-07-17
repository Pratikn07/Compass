from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from compass.api.auth import require_owner
from compass.api.dependencies import Repository

router = APIRouter(prefix="/v1", dependencies=[Depends(require_owner)])


class OverrideInput(BaseModel):
    what: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2_000)

    @field_validator("what", "reason")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class RuleChangeInput(BaseModel):
    change: dict[str, object] = Field(min_length=1)


@router.get("/rule-changes")
def rule_changes(repository: Repository) -> list[dict[str, object]]:
    return repository.list_rule_changes()


@router.post("/overrides", status_code=status.HTTP_201_CREATED)
def create_override(
    body: OverrideInput,
    repository: Repository,
) -> dict[str, object]:
    return repository.create_override(what=body.what, reason=body.reason)


@router.post("/recommendations/{decision_id}/ack")
def acknowledge_recommendation(
    decision_id: str,
    repository: Repository,
) -> dict[str, object]:
    acknowledged_at = datetime.now(UTC).isoformat()
    decision = repository.acknowledge_decision(
        decision_id,
        acknowledged_at=acknowledged_at,
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return decision


@router.post("/rule-changes", status_code=status.HTTP_201_CREATED)
def create_rule_change(
    body: RuleChangeInput,
    repository: Repository,
) -> dict[str, object]:
    proposed_at = datetime.now(UTC)
    row = body.model_dump()
    row.update(
        {
            "proposed_at": proposed_at.isoformat(),
            "effective_at": (proposed_at + timedelta(hours=48)).isoformat(),
            "approved": False,
        }
    )
    created = repository.create_rule_change(row)
    created.setdefault("note", "Rule changes take effect after the 48-hour cooling-off period.")
    return created
