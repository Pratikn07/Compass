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
