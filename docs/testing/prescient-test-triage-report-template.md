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
