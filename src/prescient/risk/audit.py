from __future__ import annotations

from prescient.journal import (
    DecisionAuditTrail,
    DecisionLayer,
    DecisionType,
    audit_trail,
    internal_rule_citation,
    rule_fact,
)


def risk_audit_trail(
    *,
    decision_type: DecisionType,
    rule_name: str,
    target: str | None = None,
    theme: str | None = None,
    passed: bool | None = None,
    reason: str | None = None,
) -> DecisionAuditTrail:
    citation = internal_rule_citation(f"risk-{rule_name}")
    return audit_trail(
        decision_type=decision_type,
        decision_layer=DecisionLayer.RISK,
        target=target,
        theme=theme,
        source_citations=[citation],
        rule_facts=[
            rule_fact(
                rule_name,
                passed=passed,
                reason=reason,
                citation_ids=[citation.citation_id],
            )
        ],
        seed=f"{rule_name}:{target}:{theme}:{passed}:{reason}",
    )
