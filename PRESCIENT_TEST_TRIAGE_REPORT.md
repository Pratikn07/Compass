# Prescient Test Triage Report

## Executive Summary

| Metric | Value |
|---|---:|
| Report date | 2026-06-04 |
| Test command count | 6 |
| Unique tests in final full suite | 612 |
| Total test executions captured | 2474 |
| Total failures | 0 |
| Confirmed bugs | 0 |
| Test assumption issues | 0 |
| Environment/mock issues | 1 |
| Ambiguous requirements | 0 |
| Coverage gaps only | 6 |
| Highest-risk finding | CG-001: Robinhood order read/cancel and exception paths remain under-covered |

No new test exposed a confirmed product bug. The required suites passed, including the full project suite and the risk-adjacent broker/storage/runtime/analyst subset.

The main output of this triage is a prioritized coverage-gap list. These are not bugs proven by failing tests; they are follow-up test targets where untested behavior sits near broker execution, storage, runtime journal, or LLM summarization boundaries.

## Test Runs and Evidence

| ID | Command | Exit Code | Evidence |
|---|---|---:|---|
| RUN-001 | `uv run pytest tests/test_part5_triage_report_contract.py -q \| tee artifacts/test-triage/part5-contract.txt` | 0 | `4 passed in 0.01s` |
| RUN-002 | `uv run pytest -q \| tee artifacts/test-triage/full-pytest.txt` | 0 | `585 passed, 1 warning in 3.81s` |
| RUN-003 | `uv run pytest tests/test_alpaca_adapter.py tests/test_robinhood_adapter.py tests/test_broker_adapter.py tests/test_broker_boundaries.py tests/test_r6_4_supabase_storage.py tests/test_r6_4_storage_runtime.py tests/test_r6_1_decision_journal.py tests/test_execution.py tests/test_claude_analyst.py tests/test_r5_4_execution_mode_flag.py -q \| tee artifacts/test-triage/risk-adjacent-pytest.txt` | 0 | `77 passed, 1 warning in 1.50s` |
| RUN-004 | `uv run pytest --cov=prescient.broker --cov=prescient.storage --cov=prescient.runtime --cov=prescient.data.gpt_summarizer --cov-report=term-missing -q \| tee artifacts/test-triage/risk-adjacent-coverage.txt` | 0 | `598 passed, 1 warning in 3.71s`; coverage total `82%` for selected modules |
| RUN-005 | `uv run pytest --cov=prescient.broker --cov=prescient.storage --cov=prescient.runtime --cov=prescient.data.gpt_summarizer --cov-report=term-missing -q 2>&1 \| tee artifacts/test-triage/risk-adjacent-coverage-combined.txt` | 0 | `598 passed, 1 warning in 3.48s`; stderr captured 56 `ResourceWarning: unclosed database` lines |
| RUN-006 | `uv run pytest -q \| tee artifacts/test-triage/final-full-pytest.txt` | 0 | `612 passed, 1 warning in 2.53s` |

Evidence files:

- `artifacts/test-triage/part5-contract.txt`
- `artifacts/test-triage/full-pytest.txt`
- `artifacts/test-triage/risk-adjacent-pytest.txt`
- `artifacts/test-triage/risk-adjacent-coverage.txt`
- `artifacts/test-triage/risk-adjacent-coverage-combined.txt`
- `artifacts/test-triage/final-full-pytest.txt`

## Confirmed Bugs

No confirmed bugs were exposed by the triage test runs.

| ID | Severity | Affected File | Exposing Test | Expected Behavior | Actual Behavior | Evidence | Recommended Next Step |
|---|---|---|---|---|---|---|---|
| None recorded | Low | None | None | None | None | No failing tests | No bug-fix phase is needed from this triage alone |

## Test Assumption Issues

No incorrect test assumptions were identified. The new Part 5 contract test followed the expected RED/GREEN sequence:

- RED: 1 passed, 3 failed while the template/playbook were missing.
- Intermediate RED: 3 passed, 1 failed while only the playbook was missing.
- GREEN: 4 passed after the template and playbook were created.

| ID | Test Name | Incorrect Assumption | Actual Code Behavior | Spec Clarification Needed | Recommended Test Change |
|---|---|---|---|---|---|
| None recorded | None | None | None | No | No test assumption issue recorded |

## Environment or Mock Issues

| ID | Failure Source | Affected Test | Cause | Evidence | Recommended Next Step |
|---|---|---|---|---|---|
| ENV-001 | Pytest coverage run stderr | Coverage run across broker/storage/runtime/LLM modules | The combined stdout/stderr coverage command emitted 56 `ResourceWarning: unclosed database` lines for `sqlite3.Connection` objects. The run still exited 0 and no specific product failure was proven during triage. | `artifacts/test-triage/risk-adjacent-coverage-combined.txt` contains repeated `ResourceWarning: unclosed database` lines. | Run a separate follow-up with warnings-as-errors and tracemalloc/source tracing, then decide whether this is production SQLite resource handling or test fixture cleanup. Do not fix it in triage. |

## Ambiguous Behavior

No ambiguous product behavior blocked classification during this triage.

| ID | Area | Question | Evidence | Human Decision Needed |
|---|---|---|---|---|
| None recorded | None | None | None | No ambiguous behavior recorded |

## Coverage Gaps Only

These gaps did not produce failing tests. They are prioritized follow-up test targets because they sit near broker execution, storage durability, runtime journal, or LLM summarization paths.

| ID | Severity | File | Lines | Untested Behavior | Risk Rationale | Recommended Next Step |
|---|---|---|---|---|---|---|
| CG-001 | High | `src/prescient/broker/robinhood.py` | 70-71, 76-85, 90, 102, 112, 128, 140-142, 181-185, 188-235, 238-241 | Robinhood login exception mapping, HTTP status mapping, account/positions error handling, order listing filters/status mapping, and order cancellation error handling. | Robinhood is a broker adapter. Untested order listing/cancel behavior can misreport broker state or hide execution errors. | Add mock-based tests for `get_orders` open/closed/all filtering, cancel success/failure, and each `_handle_exception` branch. |
| CG-002 | High | `src/prescient/broker/alpaca.py` | 61-62, 76, 83, 95, 119-121, 162, 165-204, 207-210 | Alpaca initialization exception handling, generic API error mapping, account/positions/place-order error handling, order listing conversion, and cancel error handling. | Alpaca is the primary broker adapter. Order listing and cancellation coverage should be explicit before broker confidence increases. | Add mock SDK tests for `get_orders` status conversion, cancel success/failure, and `APIError` branches outside existing auth/rate-limit/422 cases. |
| CG-003 | High | `src/prescient/storage/supabase.py` | 79-85, 96, 110, 120-125, 129-145, 149, 179-198 | Supabase client factory import path, empty-write path, response error handling, read/query filters, row-to-model mapping, and storage error classification branches. | Supabase is durable storage for journal-safe records. Untested read/filter/error branches can corrupt reporting or hide persistence failures. | Add fake-client tests for empty appends, response-level errors, read filters, malformed rows, and every storage error classification branch. |
| CG-004 | Medium | `src/prescient/data/gpt_summarizer.py` | 26-35, 42-100 | API key resolution, OpenAI client creation, no-snapshot validation, transcript truncation, missing client error, structured response parsing, and OpenAI exception mapping. | LLM summarization is not the deterministic trading rail, but it feeds analyst evidence. Bad error mapping or malformed output handling can degrade audit quality. | Add injected-client tests for missing key, empty transcript, truncation, parsed summary success, empty parsed output, timeout, connection, status, and generic OpenAI errors. |
| CG-005 | Medium | `src/prescient/runtime/journal.py` | 15-21 | JSONL pipeline event append path. | Runtime journal writes are part of the audit trail. Missing tests here can let simple append/serialization regressions pass unnoticed. | Add tests for parent directory creation, newline-delimited JSON output, and multiple event append order. |
| CG-006 | Low | `src/prescient/broker/mock.py` and `src/prescient/storage/jsonl.py` | `mock.py` 125-133, 136-154; `jsonl.py` 36, 40, 55, 57, 59, 61, 63 | Mock order filtering/cancel failures and JSONL read/query filter branches. | These are local/test/fallback paths. They matter for confidence in tests and fallback journals but are less dangerous than live broker/storage adapters. | Add small unit tests for mock open/closed/all order filtering, cancel not-found/non-open states, missing JSONL file, blank lines, and every query predicate. |

## Prioritized Next Fixes

These are recommended follow-up testing tasks only. No fixes were implemented during triage.

| Priority | Finding ID | Reason |
|---:|---|---|
| 1 | CG-001 | Robinhood adapter order listing/cancel and exception paths are broker-adjacent and under-covered. |
| 2 | CG-002 | Alpaca is the primary broker adapter; order lifecycle coverage should be stronger. |
| 3 | CG-003 | Supabase storage read/filter/error branches affect durable audit and learning inputs. |
| 4 | ENV-001 | The SQLite `ResourceWarning` should be traced with warnings-as-errors before deciding whether it is product code or test cleanup. |
| 5 | CG-004 | GPT summarizer error handling should be explicit because it feeds analyst evidence. |
| 6 | CG-005 | Runtime journal append coverage protects audit trail basics. |
| 7 | CG-006 | Mock and JSONL fallback gaps improve test reliability and local fallback confidence. |

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
