from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from prescient.learning.models import (
    LearningMode,
    ParameterProposal,
    ParameterProposalStatus,
)


def write_learning_overlay(
    *,
    path: str,
    run_id: str,
    effective_date: date,
    mode: LearningMode,
    proposals: list[ParameterProposal],
) -> str | None:
    active = mode == LearningMode.AUTO_APPLY_SAFE
    overlay_parameters = {
        proposal.path: {
            "previous_value": proposal.current_value,
            "value": proposal.proposed_value,
            "reason": proposal.evidence_summary,
            "sample_size": proposal.sample_size,
            "distinct_trading_days": proposal.distinct_trading_days,
            "policy_bounds": {
                "min_value": proposal.min_value,
                "max_value": proposal.max_value,
                "max_daily_delta": proposal.max_daily_delta,
            },
        }
        for proposal in proposals
        if _include_in_overlay(proposal, active=active)
    }

    if not overlay_parameters:
        return None

    overlay_path = Path(path)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "learning_overlay": {
            "active": active,
            "run_id": run_id,
            "effective_date": effective_date.isoformat(),
            "mode": mode.value,
            "parameters": overlay_parameters,
        }
    }
    overlay_path.write_text(
        yaml.safe_dump(payload, sort_keys=True),
        encoding="utf-8",
    )
    return str(overlay_path)


def _include_in_overlay(proposal: ParameterProposal, *, active: bool) -> bool:
    if active:
        return proposal.applied and proposal.status == ParameterProposalStatus.APPLIED
    return proposal.status in {
        ParameterProposalStatus.PROPOSED,
        ParameterProposalStatus.REVIEW_ONLY,
    }
