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
