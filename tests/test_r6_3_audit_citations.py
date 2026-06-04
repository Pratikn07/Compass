from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from prescient.data import DataProvider, PeerListSnapshot
from prescient.journal import (
    CitationConfidence,
    CitationUnavailableReason,
    DecisionLayer,
    DecisionType,
    SourceCitation,
    deterministic_citation_id,
    internal_rule_citation,
    legacy_audit_trail,
    merge_source_citations,
    url_citation,
)
from prescient.signal import DecisionAudit, StrategyDecision, StrategyStatus


def test_r6_3_prd_exists_and_requires_source_citations() -> None:
    prd_path = (
        "/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/"
        "06-journal-r6-3-audit-trail-source-citations-prd.md"
    )

    text = open(prd_path, encoding="utf-8").read()

    assert "Source Citations on Every Decision" in text
    assert "citation_unavailable_legacy_record" in text


def test_source_citation_normalizes_bounds_and_serializes_deterministically() -> None:
    citation = SourceCitation(
        citation_id="manual-id",
        provider=" Finnhub ",
        source_type=" Earnings Calendar ",
        title="Q2 earnings",
        url="https://example.test/earnings",
        source_endpoint="/calendar/earnings",
        source_id="abc-123",
        as_of=date(2026, 6, 2),
        retrieved_at=datetime(2026, 6, 2, 13, 0, tzinfo=UTC),
        excerpt="x" * 800,
        confidence=CitationConfidence.HIGH,
    )

    assert citation.provider == "finnhub"
    assert citation.source_type == "earnings_calendar"
    assert len(citation.excerpt or "") <= 500
    assert citation.model_dump(mode="json") == citation.model_dump(mode="json")


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Authorization: Bearer abc",
        "api_key=secret",
        "raw_payload={...}",
        "account_id=123",
        "prompt: trade now",
    ],
)
def test_source_citation_rejects_secret_like_fields(unsafe_value: str) -> None:
    with pytest.raises(ValidationError):
        SourceCitation(
            citation_id="bad",
            provider="internal",
            source_type="test",
            excerpt=unsafe_value,
        )


def test_citation_helpers_are_stable_and_merge_safely() -> None:
    first_id = deterministic_citation_id(
        provider="internal",
        source_type="rule",
        source_id="risk-cap",
        as_of=date(2026, 6, 2),
    )
    second_id = deterministic_citation_id(
        provider="internal",
        source_type="rule",
        source_id="risk-cap",
        as_of=date(2026, 6, 2),
    )
    rule = internal_rule_citation("risk-cap")
    url = url_citation(
        provider="finnhub",
        source_type="earnings_calendar",
        url="https://finnhub.io/api/v1/calendar/earnings",
        source_endpoint="/calendar/earnings",
    )

    assert first_id == second_id
    assert rule.citation_id.startswith("cit_")
    assert merge_source_citations([rule, url], [rule]) == [rule, url]


def test_data_snapshot_can_expose_safe_provider_citations() -> None:
    citation = url_citation(
        provider=DataProvider.FMP,
        source_type="stock_peers",
        url="https://financialmodelingprep.com/stable/stock-peers",
        source_endpoint="/stock-peers",
    )
    snapshot = PeerListSnapshot(
        ticker="aapl",
        peers=["msft"],
        provider=DataProvider.FMP,
        source_endpoint="/stock-peers",
        source_citations=[citation],
    )

    assert snapshot.ticker == "AAPL"
    assert snapshot.source_citations == [citation]
    assert "api_key" not in snapshot.model_dump_json()


def test_legacy_strategy_decision_gets_citation_unavailable_audit_marker() -> None:
    decision = StrategyDecision(
        status=StrategyStatus.NO_TRADE,
        candidate=None,
        rejection_reasons=[],
        rejection_details=[],
        audit=DecisionAudit(
            target="NTNX",
            theme="AI_STORAGE",
            peer_scores=[],
            thresholds={},
            missing_peer_factor_count=0,
            all_peer_data_missing=False,
            target_market_data_present=False,
            option_contract_count=0,
        ),
        claude_analysis_allowed=False,
    )

    assert decision.audit_trail.citation_unavailable_reasons == [
        CitationUnavailableReason.CITATION_UNAVAILABLE_LEGACY_RECORD
    ]
    assert decision.audit_trail.decision_layer == DecisionLayer.SIGNAL
    assert decision.audit_trail.decision_type == DecisionType.STRATEGY_DECISION


def test_legacy_audit_trail_can_be_built_for_manual_records() -> None:
    audit = legacy_audit_trail(
        decision_type=DecisionType.RISK_GATE,
        decision_layer=DecisionLayer.RISK,
        target="ntnx",
        theme="ai_storage",
    )

    assert audit.target == "NTNX"
    assert audit.theme == "AI_STORAGE"
    assert audit.citation_unavailable_reasons == [
        CitationUnavailableReason.CITATION_UNAVAILABLE_LEGACY_RECORD
    ]
