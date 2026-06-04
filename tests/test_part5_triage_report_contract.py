from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_part5_prd_exists_and_preserves_no_fix_scope() -> None:
    content = _read("docs/prd/11-testing-part-5-triage-report-prd.md")

    assert "# PRD: Part 5 Test Triage & Report" in content
    assert "Do not fix production code." in content
    assert "Do not enable or test against live trading." in content
    assert "PRESCIENT_TEST_TRIAGE_REPORT.md" in content


def test_triage_report_template_has_required_sections() -> None:
    content = _read("docs/testing/prescient-test-triage-report-template.md")

    required_sections = [
        "# Prescient Test Triage Report",
        "## Executive Summary",
        "## Test Runs and Evidence",
        "## Confirmed Bugs",
        "## Test Assumption Issues",
        "## Environment or Mock Issues",
        "## Ambiguous Behavior",
        "## Coverage Gaps Only",
        "## Prioritized Next Fixes",
        "## No-Fix Confirmation",
    ]
    for section in required_sections:
        assert section in content


def test_triage_template_defines_classification_and_severity_rules() -> None:
    content = _read("docs/testing/prescient-test-triage-report-template.md")

    for classification in [
        "Confirmed Bug",
        "Test Assumption Issue",
        "Environment/Mock Issue",
        "Ambiguous Requirement",
        "Coverage Gap Only",
    ]:
        assert classification in content

    for severity in ["Critical", "High", "Medium", "Low"]:
        assert severity in content


def test_triage_playbook_contains_prescient_safety_guardrails() -> None:
    content = _read("docs/testing/prescient-test-triage-playbook.md")

    required_guardrails = [
        "Do not modify production source code during triage.",
        "Do not modify `src/prescient/risk/`.",
        "Do not modify `src/prescient/signal/`.",
        "Do not change broker adapter behavior.",
        "Do not change execution mode defaults.",
        "Do not use real broker credentials.",
        "Do not use production Supabase data.",
        "Do not claim tests passed without actual command output.",
    ]
    for guardrail in required_guardrails:
        assert guardrail in content
