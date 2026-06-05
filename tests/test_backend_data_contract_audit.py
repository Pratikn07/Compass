from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from prescient.runtime import DecisionJournalRecordType
from tests.test_r6_1_decision_journal import _run_pipeline


AUDIT_DOC = Path(
    "docs/superpowers/specs/2026-06-04-prescient-backend-data-contract-audit.md"
)

BACKEND_DEPENDENT_FIELDS = [
    "Company name",
    "Earnings date",
    "Edge BP",
    "Confidence",
    "Key drivers",
    "Option legs",
    "Engine health",
    "Watchlists",
    "System status health",
    "Needs attention",
]


def _strategy_payload() -> Mapping[str, Any]:
    result = _run_pipeline()
    record = result.decision_journal_records[0]

    assert record.record_type == DecisionJournalRecordType.STRATEGY_DECISION
    return record.payload


def test_strategy_payload_exposes_current_frontend_usable_fields() -> None:
    payload = _strategy_payload()
    candidate = payload["candidate_brief"]
    snapshot = payload["data_snapshot"]

    assert candidate["earnings_date"] == "2026-06-02"
    assert isinstance(candidate["peer_signal_score"], (int, float))
    assert candidate["supporting_evidence"]
    assert candidate["peer_scores"]
    assert snapshot["option_contract_count"] == 1


def test_strategy_payload_documents_fields_that_are_not_stable_contracts() -> None:
    payload = _strategy_payload()
    candidate = payload["candidate_brief"]
    snapshot = payload["data_snapshot"]
    option_summary = snapshot["options_chain_summary"][0]

    for unavailable_field in (
        "company_name",
        "edge_bp",
        "needs_attention",
        "confidence",
        "list_confidence",
        "key_drivers",
    ):
        assert unavailable_field not in payload
        assert unavailable_field not in candidate
        assert unavailable_field not in snapshot

    for unavailable_option_leg_field in (
        "strike",
        "side",
        "iv",
        "price",
        "credit",
        "breakeven",
        "breakevens",
    ):
        assert unavailable_option_leg_field not in option_summary


def test_backend_data_contract_audit_doc_covers_visual_gap_fields() -> None:
    audit = AUDIT_DOC.read_text(encoding="utf-8")

    for field in BACKEND_DEPENDENT_FIELDS:
        assert f"| {field} |" in audit

    assert "| Available now |" in audit
    assert "| Available with parser/query work |" in audit
    assert "| Backend change required |" in audit
    assert "Do not treat citation confidence or analyst conviction" in audit
