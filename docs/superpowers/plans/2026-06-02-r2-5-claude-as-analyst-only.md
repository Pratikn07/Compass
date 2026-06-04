# R2.5 Claude As Analyst Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the existing `prescient.analyst` layer fully in line with `docs/prd/02-architecture-r2-5-claude-as-analyst-only-prd.md`.

**Architecture:** The deterministic strategy engine remains in `prescient.signal`; Claude remains a cold-path analyst under `prescient.analyst`, reached through runtime orchestration only. This work tightens the analyst response schema, updates the prompt contract, and expands tests without adding live Claude credentials, broker access, execution logic, or raw event analysis.

**Tech Stack:** Python, Pydantic v2, pytest, uv, ruff, mypy.

---

## PRD Check

The PRD exists at:

`/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/02-architecture-r2-5-claude-as-analyst-only-prd.md`

Current implementation already has:

- `prescient.analyst` package with fakeable `ClaudeCompletionClient`.
- Candidate-ready gating in `analyze_strategy_decision(...)`.
- Strict extra-field rejection via Pydantic `extra="forbid"`.
- Malformed JSON failure handling.
- Runtime hot/cold path orchestration.
- Tests proving skipped non-candidates and fake-client behavior.

Known gaps from the PRD:

- `ClaudeStrategyAnalysis` lacks required `thesis`.
- `ClaudeStrategyAnalysis` lacks required bounded `conviction_score`.
- Prompt does not request `thesis` or `conviction_score`.
- Prompt does not list the full unsafe-field set from the PRD.
- Tests do not reject invalid conviction scores.
- Existing fake Claude responses in runtime/scheduler/event tests must be updated once the schema becomes stricter.

## File Structure

Modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/analyst/models.py`
  - Add `thesis: str`.
  - Add `conviction_score: int` with strict inclusive `0..100` validation.

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/analyst/prompt.py`
  - Add an auditable prompt version constant.
  - Update safety rules and exact JSON shape.
  - Keep the candidate brief as the only strategy data payload.

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_claude_analyst.py`
  - Update valid fake responses.
  - Assert thesis and conviction score.
  - Add invalid conviction score coverage.
  - Expand unsafe extra-field coverage and prompt contract assertions.

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_hot_cold_runtime.py`
  - Update fake Claude success response for the stricter schema.

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_scheduled_pipeline.py`
  - Update fake Claude success response for the stricter schema.

- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_event_triggers.py`
  - Update fake Claude success response for the stricter schema.

Do not modify:

- `prescient.signal` logic.
- Candidate detection.
- Peer scoring.
- Target filters.
- Broker, risk, data, or journal database layers.
- Any real Claude/Anthropic API client.

## Task 1: Add Failing Analyst Schema Tests

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_claude_analyst.py`

- [ ] **Step 1: Add imports for JSON payload construction and parametrized validation**

Change the top of the file from:

```python
from datetime import date
```

to:

```python
import json
from datetime import date

import pytest
```

- [ ] **Step 2: Update the valid fake response to include the PRD schema**

Replace `_valid_response()` with:

```python
def _valid_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from positive storage peers.",
      "reasoning": "Peer read-through is strong and contradictions are limited.",
      "conviction_score": 78,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """
```

- [ ] **Step 3: Strengthen the prompt contract test**

In `test_prompt_contains_candidate_brief_json_and_prd_safety_rules`, add these assertions:

```python
assert "Prompt version: r2.5-v1" in prompt
assert '"thesis":' in prompt
assert '"conviction_score": 0' in prompt
assert "integer from 0 to 100" in prompt
assert (
    "Do not suggest position_size, order_quantity, broker_action, limit_price, "
    "stop_loss, take_profit, account_allocation, risk_override, or execute_trade."
    in prompt
)
assert "Do not use conviction_score as a position size, risk budget, or trading authorization." in prompt
```

Update the old unsafe-field assertion:

```python
assert "Do not suggest position_size, order_quantity, or broker_action." in prompt
```

to the expanded assertion above.

- [ ] **Step 4: Assert valid response fields**

In `test_valid_fake_claude_response_returns_analyzed_result`, add:

```python
assert result.analysis.thesis == (
    "NTNX has a bullish AI_STORAGE read-through from positive storage peers."
)
assert result.analysis.conviction_score == 78
```

- [ ] **Step 5: Update unsafe extra-field test response**

Replace the JSON in `test_unsafe_extra_fields_are_rejected` with:

```python
"""
{
  "recommendation": "go",
  "thesis": "NTNX has a bullish AI_STORAGE read-through.",
  "reasoning": "Looks good.",
  "conviction_score": 80,
  "missing_context": [],
  "contradictions": [],
  "suggested_expression": "CALL_OPTION",
  "position_size": "10%",
  "order_quantity": 5,
  "broker_action": "buy",
  "limit_price": 1.25,
  "stop_loss": 0.8,
  "take_profit": 2.0,
  "account_allocation": "5%",
  "risk_override": true,
  "execute_trade": true
}
"""
```

- [ ] **Step 6: Update invalid suggested expression response**

Add the required fields to `test_invalid_suggested_expression_is_rejected`:

```python
"""
{
  "recommendation": "go",
  "thesis": "NTNX has a bullish AI_STORAGE read-through.",
  "reasoning": "Use puts despite bullish setup.",
  "conviction_score": 72,
  "missing_context": [],
  "contradictions": [],
  "suggested_expression": "PUT_OPTION"
}
"""
```

- [ ] **Step 7: Update needs-more-context response**

Add the required fields to `test_needs_more_context_supports_missing_context_items`:

```python
"""
{
  "recommendation": "needs_more_context",
  "thesis": "NTNX has a plausible AI_STORAGE read-through but key context is missing.",
  "reasoning": "Need one more structured confirmation before go/no-go.",
  "conviction_score": 45,
  "missing_context": ["latest management commentary summary"],
  "contradictions": ["target already moved before earnings"],
  "suggested_expression": "NONE"
}
"""
```

Add:

```python
assert result.analysis.conviction_score == 45
assert result.analysis.thesis == (
    "NTNX has a plausible AI_STORAGE read-through but key context is missing."
)
```

- [ ] **Step 8: Add invalid conviction score tests**

Append this test to `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_claude_analyst.py`:

```python
@pytest.mark.parametrize("conviction_score", [-1, 101, 75.5, "80", True])
def test_invalid_conviction_score_is_rejected(conviction_score: object) -> None:
    response = json.dumps(
        {
            "recommendation": "go",
            "thesis": "NTNX has a bullish AI_STORAGE read-through.",
            "reasoning": "Score must be a strict bounded integer.",
            "conviction_score": conviction_score,
            "missing_context": [],
            "contradictions": [],
            "suggested_expression": "CALL_OPTION",
        }
    )
    client = FakeClaudeClient(response)

    result = analyze_candidate_brief(_candidate_brief(), client=client)

    assert result.status == ClaudeAnalysisStatus.FAILED
    assert result.analysis is None
    assert result.error_message is not None
    assert "conviction_score" in result.error_message
```

- [ ] **Step 9: Run the focused test and confirm it fails for missing implementation**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev pytest tests/test_claude_analyst.py -v
```

Expected before implementation:

```text
FAILED ... thesis
FAILED ... conviction_score
```

The exact failure text may come from Pydantic validation or missing prompt assertions.

## Task 2: Implement Strict Analyst Output Schema

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/analyst/models.py`

- [ ] **Step 1: Import `Field`**

Change:

```python
from pydantic import BaseModel, ConfigDict
```

to:

```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 2: Add `thesis` and strict bounded `conviction_score`**

Replace `ClaudeStrategyAnalysis` with:

```python
class ClaudeStrategyAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation: ClaudeRecommendation
    thesis: str
    reasoning: str
    conviction_score: int = Field(ge=0, le=100, strict=True)
    missing_context: list[str]
    contradictions: list[str]
    suggested_expression: ClaudeSuggestedExpression
```

- [ ] **Step 3: Run the focused analyst tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev pytest tests/test_claude_analyst.py -v
```

Expected after this task:

- Schema-related assertions pass.
- Prompt-related assertions may still fail because `prompt.py` is not updated yet.

## Task 3: Update Prompt Contract And Prompt Version

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/analyst/prompt.py`

- [ ] **Step 1: Add an auditable prompt version constant**

Add below the import:

```python
CLAUDE_ANALYST_PROMPT_VERSION = "r2.5-v1"
```

- [ ] **Step 2: Replace the prompt body**

Replace `build_claude_strategy_prompt(...)` with:

```python
def build_claude_strategy_prompt(brief: CandidateBrief) -> str:
    candidate_json = brief.model_dump_json()

    return (
        "You are the Claude analyst layer for prescient.\n"
        f"Prompt version: {CLAUDE_ANALYST_PROMPT_VERSION}\n"
        "Read only the candidate brief JSON below and return strict JSON.\n\n"
        "Safety rules:\n"
        "- Claude must not override deterministic filters or risk limits.\n"
        "- Do not invent missing financial data.\n"
        "- Do not choose position size.\n"
        "- Do not place trades or issue broker instructions.\n"
        "- Do not trade on a single headline.\n"
        "- Do not recommend tickers outside the configured theme.\n"
        "- Do not use conviction_score as a position size, risk budget, or trading authorization.\n"
        "- Do not suggest position_size, order_quantity, broker_action, limit_price, "
        "stop_loss, take_profit, account_allocation, risk_override, or execute_trade.\n"
        "- Only suggest CALL_OPTION, STOCK, or NONE.\n\n"
        "Recommendation semantics:\n"
        "- Use go only when the candidate brief supports the deterministic thesis and has no material contradiction.\n"
        "- Use no_go when the brief contains a material contradiction, stale evidence, unsupported thesis, or expression mismatch.\n"
        "- Use needs_more_context when the brief is plausible but lacks structured context for a clean judgment.\n"
        "- Prefer suggested_expression NONE for no_go or needs_more_context.\n\n"
        "Thesis requirements:\n"
        "- Name the target and theme from the candidate brief.\n"
        "- Reflect the deterministic direction.\n"
        "- Reference peer read-through evidence at a high level.\n"
        "- Do not invent financial facts, order instructions, position sizing, or unsupported tickers.\n\n"
        "Conviction score requirements:\n"
        "- conviction_score must be an integer from 0 to 100.\n"
        "- 0..39 means weak or no conviction.\n"
        "- 40..69 means moderate conviction or meaningful uncertainty.\n"
        "- 70..100 means high conviction from a clean brief and low contradiction load.\n\n"
        "Return exactly this JSON shape with no extra fields:\n"
        "{\n"
        '  "recommendation": "go | no_go | needs_more_context",\n'
        '  "thesis": "short analyst thesis based only on the candidate brief",\n'
        '  "reasoning": "short explanation of the recommendation",\n'
        '  "conviction_score": 0,\n'
        '  "missing_context": ["structured context still needed"],\n'
        '  "contradictions": ["material contradiction found in the brief"],\n'
        '  "suggested_expression": "CALL_OPTION | STOCK | NONE"\n'
        "}\n\n"
        f"Candidate brief JSON:\n{candidate_json}"
    )
```

- [ ] **Step 3: Run the analyst tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev pytest tests/test_claude_analyst.py -v
```

Expected:

```text
tests/test_claude_analyst.py ... PASSED
```

## Task 4: Update Fake Claude Responses Across Runtime Boundaries

**Files:**

- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_hot_cold_runtime.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_scheduled_pipeline.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_event_triggers.py`

- [ ] **Step 1: Update `_valid_claude_response()` in hot/cold runtime tests**

In `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_hot_cold_runtime.py`, replace `_valid_claude_response()` with:

```python
def _valid_claude_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from positive storage peers.",
      "reasoning": "The candidate brief supports the bullish peer read-through setup.",
      "conviction_score": 78,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """
```

- [ ] **Step 2: Update `_valid_claude_response()` in scheduled pipeline tests**

In `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_scheduled_pipeline.py`, replace `_valid_claude_response()` with:

```python
def _valid_claude_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from positive storage peers.",
      "reasoning": "The candidate brief supports the bullish peer read-through setup.",
      "conviction_score": 78,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """
```

- [ ] **Step 3: Update `_valid_claude_response()` in event trigger tests**

In `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_event_triggers.py`, replace `_valid_claude_response()` with:

```python
def _valid_claude_response() -> str:
    return """
    {
      "recommendation": "go",
      "thesis": "NTNX has a bullish AI_STORAGE read-through from positive storage peers.",
      "reasoning": "The candidate brief supports the bullish peer read-through setup.",
      "conviction_score": 78,
      "missing_context": [],
      "contradictions": [],
      "suggested_expression": "CALL_OPTION"
    }
    """
```

- [ ] **Step 4: Run boundary tests that exercise fake Claude responses**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev pytest \
  tests/test_hot_cold_runtime.py \
  tests/test_scheduled_pipeline.py \
  tests/test_event_triggers.py \
  -v
```

Expected:

```text
PASSED
```

## Task 5: Preserve Import And Data Boundaries

**Files:**

- Inspect: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/signal`
- Inspect: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/events`
- Inspect: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/runtime`

- [ ] **Step 1: Verify signal remains Claude-free**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
rg -n 'prescient\\.analyst|anthropic|Claude' src/prescient/signal
```

Expected:

```text
no output
```

- [ ] **Step 2: Verify event handling does not call analyst directly**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
rg -n 'prescient\\.analyst|analyze_candidate_brief|analyze_strategy_decision|build_claude_strategy_prompt' src/prescient/events
```

Expected:

```text
no output
```

- [ ] **Step 3: Verify runtime remains the cold-path orchestration boundary**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
rg -n 'analyze_strategy_decision|ClaudeAnalysisStatus' src/prescient/runtime
```

Expected output should show analyst use only in runtime orchestration files, not inside `signal`.

## Task 6: Full Verification

**Files:**

- All production and test files touched above.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev pytest -v
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Run ruff**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run mypy**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run --extra dev mypy src tests
```

Expected:

```text
Success: no issues found
```

- [ ] **Step 4: Summarize completion**

Report:

- R2.5 PRD checked.
- Analyst schema now includes `thesis` and strict `conviction_score`.
- Prompt contract matches R2.5 safety requirements.
- Claude remains skipped for non-candidates and advisory for candidates.
- No production code calls real Claude or broker APIs.
- Verification command results.

## Acceptance Checklist

- [ ] `prescient.signal` does not import `prescient.analyst` or `anthropic`.
- [ ] Claude receives only `CandidateBrief` JSON as strategy data.
- [ ] Rejected/no-trade decisions skip Claude without client calls.
- [ ] Claude output validates `recommendation`, `thesis`, `reasoning`, `conviction_score`, `missing_context`, `contradictions`, and `suggested_expression`.
- [ ] `conviction_score` rejects values outside `0..100`.
- [ ] `conviction_score` rejects non-integer values such as floats, strings, and booleans.
- [ ] Unsafe extra fields are rejected.
- [ ] Malformed JSON is rejected.
- [ ] Claude failures do not mutate deterministic strategy decisions.
- [ ] Tests use fake Claude clients only.

## Execution Notes

This plan assumes no Git repository is available in `/Users/pratik.nandoskar/Documents/working/prescient`. If the implementation workspace is later placed inside a Git repo, commit after Task 3 and Task 6 with concise messages such as:

```bash
git add src/prescient/analyst tests/test_claude_analyst.py
git commit -m "feat: enforce r2.5 analyst schema"
git add tests/test_hot_cold_runtime.py tests/test_scheduled_pipeline.py tests/test_event_triggers.py
git commit -m "test: update claude boundary fixtures"
```
