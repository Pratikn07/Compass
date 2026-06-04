# Part 5 Test Triage Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Part 5 testing phase as a repeatable no-fix triage workflow that produces a clear `PRESCIENT_TEST_TRIAGE_REPORT.md` separating confirmed bugs from test assumptions, environment issues, and ambiguous behavior.

**Architecture:** Add durable documentation and contract tests for the triage report structure, then run the relevant test suites and create the actual root-level report from real output. The workflow is documentation/test-only and must not modify production source code under `src/prescient`, especially risk, signal, broker behavior, or execution-mode defaults.

**Tech Stack:** Python 3.11+, pytest, uv, Markdown.

---

## Source PRD

Use the Part 5 PRD from the conversation as source of truth. Save it before implementation at:

`/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/11-testing-part-5-triage-report-prd.md`

## File Structure

Create:

- `/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/11-testing-part-5-triage-report-prd.md`
  - Durable PRD for the no-fix triage/report phase.
- `/Users/pratik.nandoskar/Documents/working/prescient/docs/testing/prescient-test-triage-report-template.md`
  - Canonical report structure with required headings, classification rules, severity levels, and no-fix confirmation.
- `/Users/pratik.nandoskar/Documents/working/prescient/docs/testing/prescient-test-triage-playbook.md`
  - Exact agent instructions for running Part 5 safely.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_part5_triage_report_contract.py`
  - Contract tests proving the PRD, template, and playbook contain the required sections and guardrails.
- `/Users/pratik.nandoskar/Documents/working/prescient/PRESCIENT_TEST_TRIAGE_REPORT.md`
  - The actual report produced after running tests and classifying findings.

Do not modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/risk/**`
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/signal/**`
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/broker/**`
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/runtime/**`
- `/Users/pratik.nandoskar/Documents/working/prescient/CLAUDE.md`

This phase may inspect source files and tests, but it must not change production behavior.

## Tasks

### Task 1: Save the Part 5 PRD

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/11-testing-part-5-triage-report-prd.md`

- [ ] **Step 1: Create the PRD file**

Create the file with this content:

```markdown
# PRD: Part 5 Test Triage & Report

## Overview

The purpose of this phase is to collect, classify, and report everything discovered during the Prescient testing effort without modifying production code or changing test expectations silently.

This phase is strictly diagnostic. It separates confirmed product/code defects from incorrect test assumptions, environment issues, and unclear requirements. Fixing issues is out of scope and must happen in a separate approved phase.

## Problem Statement

Prescient is a safety-sensitive trading system where deterministic code owns risk, execution mode, and broker boundaries. During testing, failures may appear for different reasons:

- the application has a real bug
- the test was written with the wrong assumption
- the intended behavior is unclear
- the failure came from environment or mock setup
- the failure exposes a dangerous architectural boundary issue

If the AI agent fixes failures while testing, it may accidentally hide real defects, weaken risk rails, or change behavior just to make tests pass. This PRD prevents that.

## Goals

- Produce a clear findings report from all new tests.
- Separate real bugs from wrong or uncertain test assumptions.
- Preserve evidence from failing tests.
- Prevent any source-code fixes during the triage phase.
- Give the human owner a clean decision list for what should be fixed later.
- Protect Prescient's risk, broker, and execution boundaries from quiet changes.

## Non-Goals

- Do not fix production code.
- Do not edit risk caps, execution rules, broker safety checks, or signal logic.
- Do not rewrite tests just to make the suite pass unless the test assumption is explicitly classified as wrong.
- Do not enable or test against live trading.
- Do not touch production broker accounts, production Supabase data, or real credentials.

## Scope

This phase covers findings from earlier testing work, especially:

- broker adapter tests
- Supabase/storage tests
- runtime/journal tests
- LLM/analyst boundary tests
- authority boundary tests proving Claude cannot size, approve, or execute trades
- execution mode tests proving `propose_only` cannot silently become `live`

## Required Output

The agent must produce a report called:

`PRESCIENT_TEST_TRIAGE_REPORT.md`

The report must include these sections:

1. Executive Summary
2. Confirmed Bugs
3. Test Assumption Issues
4. Environment or Mock Issues
5. Ambiguous Behavior
6. Coverage Gaps Only
7. No-Fix Confirmation

## Finding Classification

Every finding must be classified as one of:

- Confirmed Bug: Code behavior violates existing requirements or safety rules.
- Test Assumption Issue: Test expectation was wrong or unsupported by the spec.
- Environment/Mock Issue: Failure caused by setup, not product behavior.
- Ambiguous Requirement: Intended behavior is unclear and requires human decision.
- Coverage Gap Only: Untested code was found, but no failure was produced.

## Severity Levels

- Critical: Could place, approve, size, or route a live trade incorrectly.
- High: Could bypass risk rails, corrupt journal/storage, or mis-handle broker state.
- Medium: Incorrect system behavior with limited safety impact.
- Low: Minor edge case, logging, formatting, or non-critical reporting issue.

## Hard Guardrails

During this phase, the agent must not:

- modify files under `src/prescient/risk/`
- modify files under `src/prescient/signal/`
- change broker adapter behavior
- change execution mode defaults
- edit tests to hide failures
- change fixtures without documenting why
- use real broker credentials
- use production Supabase data
- claim tests passed without showing actual output

## Acceptance Criteria

This phase is complete when:

- The full relevant test suite has been run.
- The actual pytest output is captured in the report.
- Every failure is classified.
- Confirmed bugs are separated from test-assumption issues.
- No source-code fixes were made.
- The human owner has a clear list of what to fix in a later phase.

## Success Metric

The output should let the owner answer three questions quickly:

1. What is genuinely broken?
2. What tests were wrong or uncertain?
3. What should be fixed next, in priority order?

This phase is successful only if it improves clarity without changing system behavior.
```

- [ ] **Step 2: Verify the PRD file exists**

Run:

```bash
test -f docs/prd/11-testing-part-5-triage-report-prd.md
```

Expected: exit code `0`.

### Task 2: Write the Contract Test First

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_part5_triage_report_contract.py`

- [ ] **Step 1: Add failing tests for required Part 5 artifacts**

Create `tests/test_part5_triage_report_contract.py` with this content:

```python
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
```

- [ ] **Step 2: Run the new contract test and verify RED**

Run:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q
```

Expected: fail because the template and playbook files do not exist yet.

### Task 3: Create the Report Template

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/docs/testing/prescient-test-triage-report-template.md`

- [ ] **Step 1: Create the template file**

Create `docs/testing/prescient-test-triage-report-template.md` with this content:

```markdown
# Prescient Test Triage Report

## Executive Summary

| Metric | Value |
|---|---:|
| Report date | 2026-06-04 |
| Test command count | 0 |
| Total tests run | 0 |
| Total failures | 0 |
| Confirmed bugs | 0 |
| Test assumption issues | 0 |
| Environment/mock issues | 0 |
| Ambiguous requirements | 0 |
| Coverage gaps only | 0 |
| Highest-risk finding | None recorded |

## Test Runs and Evidence

Record every command that was run during triage. Paste the real output summary, including failing test names and pytest summaries.

| ID | Command | Exit Code | Evidence |
|---|---|---:|---|
| RUN-001 | `uv run pytest -q` | 0 | `0 tests recorded in template` |

## Confirmed Bugs

Use this section only when code behavior violates an existing requirement, safety rule, PRD, or documented contract.

| ID | Severity | Affected File | Exposing Test | Expected Behavior | Actual Behavior | Evidence | Recommended Next Step |
|---|---|---|---|---|---|---|---|
| None recorded | Low | None | None | None | None | None | No confirmed bug recorded in template |

## Test Assumption Issues

Use this section when the test expectation is unsupported, contradicted by the existing spec, or based on a misunderstood interface.

| ID | Test Name | Incorrect Assumption | Actual Code Behavior | Spec Clarification Needed | Recommended Test Change |
|---|---|---|---|---|---|
| None recorded | None | None | None | No | No test assumption issue recorded in template |

## Environment or Mock Issues

Use this section when a failure is caused by setup rather than product behavior.

| ID | Failure Source | Affected Test | Cause | Evidence | Recommended Next Step |
|---|---|---|---|---|---|
| None recorded | None | None | None | None | No environment or mock issue recorded in template |

## Ambiguous Behavior

Use this section when the intended behavior is unclear and the agent cannot classify the finding confidently.

| ID | Area | Question | Evidence | Human Decision Needed |
|---|---|---|---|---|
| None recorded | None | None | None | No ambiguous behavior recorded in template |

## Coverage Gaps Only

Use this section for untested lines that did not produce a failing test but remain worth prioritizing.

| ID | Severity | File | Lines | Untested Behavior | Risk Rationale | Recommended Next Step |
|---|---|---:|---|---|---|---|
| None recorded | Low | None | 0 | None | None | No coverage gap recorded in template |

## Prioritized Next Fixes

This section lists recommended follow-up fix work. It must not include fixes performed during triage.

| Priority | Finding ID | Reason |
|---:|---|---|
| 1 | None recorded | No fix priority recorded in template |

## No-Fix Confirmation

- Production source code modified during triage: No
- Files under `src/prescient/risk/` modified during triage: No
- Files under `src/prescient/signal/` modified during triage: No
- Broker adapter behavior changed during triage: No
- Execution mode defaults changed during triage: No
- Tests edited to hide failures: No
- Real broker credentials used: No
- Production Supabase data used: No
- Actual command output captured above: Yes

## Classification Reference

- Confirmed Bug: Code behavior violates existing requirements or safety rules.
- Test Assumption Issue: Test expectation was wrong or unsupported by the spec.
- Environment/Mock Issue: Failure caused by setup, not product behavior.
- Ambiguous Requirement: Intended behavior is unclear and requires human decision.
- Coverage Gap Only: Untested code was found, but no failure was produced.

## Severity Reference

- Critical: Could place, approve, size, or route a live trade incorrectly.
- High: Could bypass risk rails, corrupt journal/storage, or mis-handle broker state.
- Medium: Incorrect system behavior with limited safety impact.
- Low: Minor edge case, logging, formatting, or non-critical reporting issue.
```

- [ ] **Step 2: Run the contract test and verify it still fails on the missing playbook**

Run:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q
```

Expected: fail because `docs/testing/prescient-test-triage-playbook.md` does not exist yet.

### Task 4: Create the Triage Playbook

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/docs/testing/prescient-test-triage-playbook.md`

- [ ] **Step 1: Create the playbook file**

Create `docs/testing/prescient-test-triage-playbook.md` with this content:

```markdown
# Prescient Part 5 Test Triage Playbook

## Purpose

This playbook tells an AI agent how to perform Part 5 triage after new tests have been added. The job is to report what tests exposed, not to fix production behavior.

## Hard Guardrails

- Do not modify production source code during triage.
- Do not modify `src/prescient/risk/`.
- Do not modify `src/prescient/signal/`.
- Do not change broker adapter behavior.
- Do not change execution mode defaults.
- Do not use real broker credentials.
- Do not use production Supabase data.
- Do not claim tests passed without actual command output.
- Do not edit tests to hide failures.
- Do not change fixtures unless the report classifies the original expectation as a Test Assumption Issue.

## Required Setup

Run all commands from the repository root:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
```

Create a local evidence directory:

```bash
mkdir -p artifacts/test-triage
```

## Commands to Run

Run the Part 5 contract test:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q | tee artifacts/test-triage/part5-contract.txt
```

Run the full test suite:

```bash
uv run pytest -q | tee artifacts/test-triage/full-pytest.txt
```

Run targeted broker/storage/runtime/analyst test groups:

```bash
uv run pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  tests/test_broker_adapter.py \
  tests/test_broker_boundaries.py \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_storage_runtime.py \
  tests/test_r6_1_decision_journal.py \
  tests/test_execution.py \
  tests/test_claude_analyst.py \
  tests/test_r5_4_execution_mode_flag.py \
  -q | tee artifacts/test-triage/risk-adjacent-pytest.txt
```

If `pytest-cov` is available, run coverage for risk-adjacent modules:

```bash
uv run pytest \
  --cov=prescient.broker \
  --cov=prescient.storage \
  --cov=prescient.runtime \
  --cov=prescient.data.gpt_summarizer \
  --cov-report=term-missing \
  -q | tee artifacts/test-triage/risk-adjacent-coverage.txt
```

If `pytest-cov` is unavailable, record that as an Environment/Mock Issue and continue with pytest evidence.

## Classification Rules

Classify every finding into exactly one category:

- Confirmed Bug: Code behavior violates an existing requirement, safety rule, PRD, or documented contract.
- Test Assumption Issue: The test expectation is unsupported, contradicted by the spec, or based on a misunderstood interface.
- Environment/Mock Issue: Failure is caused by setup, missing tooling, missing environment variables, service availability, or a bad fake.
- Ambiguous Requirement: The intended behavior is unclear and requires a human decision.
- Coverage Gap Only: Untested code was found, but no failing test proves a bug.

## Severity Rules

- Critical: Could place, approve, size, or route a live trade incorrectly.
- High: Could bypass risk rails, corrupt journal/storage, or mis-handle broker state.
- Medium: Incorrect system behavior with limited safety impact.
- Low: Minor edge case, logging, formatting, or non-critical reporting issue.

## Report Procedure

1. Copy `docs/testing/prescient-test-triage-report-template.md` to `PRESCIENT_TEST_TRIAGE_REPORT.md`.
2. Replace the template metrics with the real command results.
3. Paste concise evidence from `artifacts/test-triage/*.txt`.
4. Classify every failure or notable coverage gap.
5. Add prioritized next fixes without implementing them.
6. Complete the No-Fix Confirmation honestly.
7. Run `uv run pytest tests/test_part5_triage_report_contract.py -q` again.
8. Stop and hand the report to the human owner.

## Stop Conditions

Stop immediately and report if:

- A finding suggests risk rails are wrong.
- A finding suggests live mode can be reached without explicit human authorization.
- A test requires real broker credentials.
- A test requires production Supabase data.
- The agent is tempted to fix source code during triage.
```

- [ ] **Step 2: Run the contract test and verify GREEN**

Run:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q
```

Expected: pass.

### Task 5: Produce the Actual Triage Report

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/PRESCIENT_TEST_TRIAGE_REPORT.md`
- Create directory: `/Users/pratik.nandoskar/Documents/working/prescient/artifacts/test-triage/`

- [ ] **Step 1: Create the evidence directory**

Run:

```bash
mkdir -p artifacts/test-triage
```

Expected: directory exists at `artifacts/test-triage`.

- [ ] **Step 2: Run the Part 5 contract test and capture output**

Run:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q | tee artifacts/test-triage/part5-contract.txt
```

Expected: output includes `passed`.

- [ ] **Step 3: Run the full test suite and capture output**

Run:

```bash
uv run pytest -q | tee artifacts/test-triage/full-pytest.txt
```

Expected: output ends with a pytest summary. Record the exact total in the report.

- [ ] **Step 4: Run targeted risk-adjacent tests and capture output**

Run:

```bash
uv run pytest \
  tests/test_alpaca_adapter.py \
  tests/test_robinhood_adapter.py \
  tests/test_broker_adapter.py \
  tests/test_broker_boundaries.py \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_storage_runtime.py \
  tests/test_r6_1_decision_journal.py \
  tests/test_execution.py \
  tests/test_claude_analyst.py \
  tests/test_r5_4_execution_mode_flag.py \
  -q | tee artifacts/test-triage/risk-adjacent-pytest.txt
```

Expected: output ends with a pytest summary. If failures occur, classify each failure in the report before any fix work.

- [ ] **Step 5: Run coverage if the dependency is available**

Run:

```bash
uv run pytest \
  --cov=prescient.broker \
  --cov=prescient.storage \
  --cov=prescient.runtime \
  --cov=prescient.data.gpt_summarizer \
  --cov-report=term-missing \
  -q | tee artifacts/test-triage/risk-adjacent-coverage.txt
```

Expected: if `pytest-cov` is installed, output includes a coverage table. If pytest rejects `--cov`, write an Environment/Mock Issue in the report stating that coverage tooling is not installed.

- [ ] **Step 6: Create the report from the template**

Copy the template content into `/Users/pratik.nandoskar/Documents/working/prescient/PRESCIENT_TEST_TRIAGE_REPORT.md`, then replace the metrics and rows using the real evidence from `artifacts/test-triage`.

The report must include:

```markdown
# Prescient Test Triage Report

## Executive Summary

## Test Runs and Evidence

## Confirmed Bugs

## Test Assumption Issues

## Environment or Mock Issues

## Ambiguous Behavior

## Coverage Gaps Only

## Prioritized Next Fixes

## No-Fix Confirmation
```

- [ ] **Step 7: Verify no production files changed**

Run:

```bash
python - <<'PY'
from pathlib import Path

for path in [
    "src/prescient/risk",
    "src/prescient/signal",
    "src/prescient/broker",
    "src/prescient/runtime",
]:
    touched = [p for p in Path(path).rglob("*") if p.is_file()]
    print(f"{path}: inspected {len(touched)} files; no write check performed by this script")
PY
```

Expected: command prints inspected file counts. The agent must also verify through file-edit history that no production source edits were made during this phase.

- [ ] **Step 8: Run the contract test one final time**

Run:

```bash
uv run pytest tests/test_part5_triage_report_contract.py -q
```

Expected: pass.

## Self-Review Checklist

- The PRD is saved under `docs/prd`.
- The template contains every report section required by the PRD.
- The playbook contains the no-fix guardrails verbatim.
- The contract test passes.
- The actual report contains real command output, not claims without evidence.
- Confirmed bugs, test assumptions, environment/mock issues, ambiguous behavior, and coverage gaps are separated.
- No production source code was changed during triage.
- No live broker credentials or production Supabase data were used.
