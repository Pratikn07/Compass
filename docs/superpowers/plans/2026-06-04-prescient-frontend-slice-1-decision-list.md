# Prescient Web Frontend - Slice 1 (Decision List) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Slice 0 empty `/decisions` placeholder with a real, authenticated decision list showing the latest run's projected decisions from Supabase.

**Architecture:** This slice starts by materializing the existing Supabase projection tables that the approved frontend spec depends on: `runs` and `decision_records`. `journal_records` remains the canonical append-only audit trail; `runs` and `decision_records` are read-optimized projections written by the storage adapter from the same journal-safe records. The frontend stays read-only, using typed Supabase queries through TanStack Query hooks and rendering loading/error/empty/populated table states with Slice 0 primitives.

**Tech Stack:** Existing Slice 0 web stack: Next.js App Router + TypeScript, Tailwind CSS, existing UI primitives (`Badge`, `Table`, `Th`, `Td`), TanStack Query v5, Supabase JS client, Zod, Vitest + React Testing Library. Backend projection work uses Python 3.14 in this workspace, Pydantic v2, pytest, and the existing `SupabaseStorageAdapter`.

**Reference spec:** `docs/superpowers/specs/2026-06-03-prescient-web-frontend-design.md`

> **WARNING: Prerequisites.** This plan assumes Slice 0 is complete. At plan-writing time, `web/` does not exist in the current workspace. Do not execute frontend tasks until Slice 0 has created the app shell, auth guard, Supabase clients, generated database types, UI primitives, state components, and authenticated empty `/decisions` page.
>
> **WARNING: Git not yet set up.** `prescient/` was not a git repository when Slice 0 was planned. Until `git init` is run here, skip every `git add` / `git commit` step and treat each task end as a logical checkpoint. Once git is initialized, commit steps become valid as written.

---

## Source Notes

- Supabase Data REST API docs confirm Supabase exposes a REST API from database schemas and supports browser/client-library reads through PostgREST: https://supabase.com/docs/guides/api
- Supabase changelog note `42949` says removing anon-key access to the root OpenAPI spec does **not** affect normal Data API table usage or client-library reads: https://supabase.com/changelog/42949-breaking-change-removing-access-to-openapi-spec-via-the-anon-key
- Supabase changelog note `45329` says table grants are a separate layer from RLS and new projects may require explicit grants for Data API access. Slice 0 already handles schema exposure, grants, and authenticated read policies: https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically

## Current Repo Facts

- `supabase/migrations/20260603063259_r6_4_storage.sql` already creates `prescient_storage.runs`, `prescient_storage.journal_records`, and `prescient_storage.decision_records`.
- `src/prescient/storage/supabase.py` currently writes only `journal_records`.
- `src/prescient/runtime/decision_journal.py` writes `strategy_decision` journal records whose payload includes `thesis`, `decision_summary`, `strategy_decision`, and `candidate_brief`.
- Slice 2 is already planned and expects these Slice 1 frontend files to exist: `web/src/features/decisions/use-latest-run.ts`, `web/src/features/decisions/use-decisions.ts`, and `web/src/features/decisions/decision-list.tsx`.
- Focused baseline before writing this plan:
  - `.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py tests/test_r6_4_storage_runtime.py -q` -> `25 passed`
  - `.venv/bin/python -m pytest tests/test_r6_4_supabase_migration.py -q` -> `3 passed`

## File Structure

Backend changes:

```
src/prescient/storage/
  models.py                         # add run/decision projection row helpers
  supabase.py                       # upsert journal_records + runs + decision_records

tests/
  test_r6_4_supabase_storage.py     # projection row + fake client projection tests
  test_r6_4_storage_runtime.py      # verify runtime writer still sends normalized records only
```

Frontend changes after Slice 0:

```
web/
  src/
    app/
      (app)/
        decisions/
          page.tsx                   # replace Slice 0 placeholder with DecisionListClient
    features/
      decisions/
        decision-list.types.ts       # RunRow, DecisionRecordRow, parsed list item types
        decision-list-schemas.ts     # Zod schemas for list-row payload fields
        parse-decision-list.ts       # DB row -> display row with derived outcome
        decision-list-format.ts      # badge variants + readable labels
        fetch-latest-run.ts          # Supabase query for latest run projection
        use-latest-run.ts            # TanStack Query hook
        fetch-decisions.ts           # Supabase query for decision_records by run_id
        use-decisions.ts             # TanStack Query hook
        decision-list.tsx            # pure table / state-free presentational component
        decision-list-client.tsx     # hook orchestration + loading/error/empty states
  __tests__/
    decision-list-schemas.test.ts
    parse-decision-list.test.ts
    fetch-decision-list.test.ts
    decision-list.test.tsx
```

## Safety Rules

- Do not add trade actions. No buy, approve, edit size, or authorize controls.
- Do not make browser writes to `prescient_storage`.
- Do not expose or use the Supabase service role key in `web/`.
- Do not change risk caps, signal scoring, execution mode defaults, broker behavior, or Claude behavior.
- `runs` and `decision_records` are projections. `journal_records` stays canonical.
- The list `Outcome` column is derived for Slice 1 display only:
  - if the projected row payload contains `outcome_type`, use it;
  - otherwise rejected/no-trade strategy statuses display `no_trade`;
  - otherwise display `pending`.
  Full lifecycle/outcome rendering remains Slice 2+.

---

## Task 0: Preflight - confirm Slice 0 and backend baseline

**Files:** none

- [ ] **Step 1: Verify Slice 0 frontend exists**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
test -d web
test -f web/src/lib/supabase/database.types.ts
test -f web/src/lib/supabase/client.ts
test -f "web/src/app/(app)/decisions/page.tsx"
test -f web/src/components/ui/badge.tsx
test -f web/src/components/ui/table.tsx
test -f web/src/components/states/loading-state.tsx
test -f web/src/components/states/error-state.tsx
test -f web/src/components/states/empty-state.tsx
```

Expected: all commands exit 0. If any fail, stop and execute Slice 0 first.

- [ ] **Step 2: Verify backend storage baseline is green**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py tests/test_r6_4_storage_runtime.py tests/test_r6_4_supabase_migration.py -q
```

Expected: all tests pass. At plan-writing time the focused baseline was `28 passed`.

- [ ] **Step 3: Verify frontend gate is green**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test && npm run build
```

Expected: all existing Slice 0 tests pass and production build succeeds.

---

## Task 1: Backend projection row helpers

**Files:**
- Modify: `src/prescient/storage/models.py`
- Test: `tests/test_r6_4_supabase_storage.py`

- [ ] **Step 1: Write failing tests for projection rows**

In `tests/test_r6_4_supabase_storage.py`, add these tests after `test_storage_record_normalizes_decision_journal_metadata`:

```python
def test_storage_record_projects_run_row_from_journal_record() -> None:
    row = StorageRecord.from_decision_journal_record(_record()).to_run_row()

    assert row == {
        "run_id": "scheduled:2026-06-01",
        "trigger_type": "scheduled",
        "scheduled_date": "2026-06-01",
        "current_date": "2026-06-01",
        "window_start": "2026-06-01",
        "window_end": "2026-06-01",
        "status": "recorded",
        "payload": {
            "source": "storage_projection",
            "execution_mode": "propose_only",
            "record_count": 1,
        },
        "schema_version": 1,
        "created_at": "2026-06-01T14:30:00Z",
    }


def test_storage_record_projects_decision_row_only_for_strategy_decision() -> None:
    strategy_row = StorageRecord.from_decision_journal_record(_record()).to_decision_record_row()

    assert strategy_row == {
        "decision_record_id": "decision_001",
        "run_id": "scheduled:2026-06-01",
        "decision_id": "decision_001",
        "decision_index": 0,
        "trading_date": "2026-06-01",
        "target": "NTNX",
        "theme": "AI_STORAGE",
        "strategy_type": "bullish_earnings_readthrough",
        "strategy_status": "candidate_ready_for_analyst",
        "execution_mode": "propose_only",
        "payload": {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
        "schema_version": 1,
        "created_at": "2026-06-01T14:30:00Z",
    }

    analyst = _record(journal_record_id="jrnl_analyst")
    analyst = analyst.model_copy(update={"record_type": DecisionJournalRecordType.ANALYST_REVIEW})
    assert StorageRecord.from_decision_journal_record(analyst).to_decision_record_row() is None
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py::test_storage_record_projects_run_row_from_journal_record \
  tests/test_r6_4_supabase_storage.py::test_storage_record_projects_decision_row_only_for_strategy_decision \
  -q
```

Expected: FAIL because `to_run_row()` and `to_decision_record_row()` do not exist yet.

- [ ] **Step 3: Add projection helper methods**

In `src/prescient/storage/models.py`, add these methods inside `StorageRecord` after `to_journal_record_row`:

```python
    def to_run_row(self, *, record_count: int = 1) -> dict[str, Any]:
        trading_date = self.trading_date.isoformat() if self.trading_date is not None else None
        return {
            "run_id": self.run_id,
            "trigger_type": _run_trigger_type(self.run_id),
            "scheduled_date": trading_date,
            "current_date": trading_date,
            "window_start": trading_date,
            "window_end": trading_date,
            "status": "recorded",
            "payload": {
                "source": "storage_projection",
                "execution_mode": self.execution_mode,
                "record_count": record_count,
            },
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }

    def to_decision_record_row(self) -> dict[str, Any] | None:
        if self.record_type != "strategy_decision":
            return None
        if self.decision_id is None or self.trading_date is None:
            return None
        return {
            "decision_record_id": self.decision_id,
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "decision_index": self.decision_index,
            "trading_date": self.trading_date.isoformat(),
            "target": self.target,
            "theme": self.theme,
            "strategy_type": self.strategy_type,
            "strategy_status": self.strategy_status,
            "execution_mode": self.execution_mode,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "created_at": _format_datetime(self.created_at),
        }
```

Then add this helper near `_format_datetime`:

```python
def _run_trigger_type(run_id: str) -> str | None:
    prefix = run_id.split(":", 1)[0].strip().lower()
    return prefix or None
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py::test_storage_record_projects_run_row_from_journal_record \
  tests/test_r6_4_supabase_storage.py::test_storage_record_projects_decision_row_only_for_strategy_decision \
  -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add src/prescient/storage/models.py tests/test_r6_4_supabase_storage.py
git commit -m "feat(storage): project runs and decision rows from journal records"
```

---

## Task 2: Backend Supabase projection writes

**Files:**
- Modify: `src/prescient/storage/supabase.py`
- Modify: `tests/test_r6_4_supabase_storage.py`

- [ ] **Step 1: Add a failing test for projection upserts**

In `tests/test_r6_4_supabase_storage.py`, add this test after `test_supabase_adapter_upserts_normalized_rows_with_injected_client`:

```python
def test_supabase_adapter_upserts_run_and_decision_projections() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")
    strategy = _record()
    analyst = strategy.model_copy(
        update={
            "journal_record_id": "jrnl_analyst",
            "record_type": DecisionJournalRecordType.ANALYST_REVIEW,
        }
    )

    result = adapter.append_decision_journal_records([strategy, analyst])

    assert result.ok is True
    assert result.records_written == 2
    assert fake_client.upserts_by_table["journal_records"][0]["journal_record_id"] == "jrnl_001"
    assert fake_client.upserts_by_table["journal_records"][1]["journal_record_id"] == "jrnl_analyst"
    assert fake_client.upserts_by_table["runs"] == [
        {
            "run_id": "scheduled:2026-06-01",
            "trigger_type": "scheduled",
            "scheduled_date": "2026-06-01",
            "current_date": "2026-06-01",
            "window_start": "2026-06-01",
            "window_end": "2026-06-01",
            "status": "recorded",
            "payload": {
                "source": "storage_projection",
                "execution_mode": "propose_only",
                "record_count": 2,
            },
            "schema_version": 1,
            "created_at": "2026-06-01T14:30:00Z",
        }
    ]
    assert fake_client.upserts_by_table["decision_records"] == [
        {
            "decision_record_id": "decision_001",
            "run_id": "scheduled:2026-06-01",
            "decision_id": "decision_001",
            "decision_index": 0,
            "trading_date": "2026-06-01",
            "target": "NTNX",
            "theme": "AI_STORAGE",
            "strategy_type": "bullish_earnings_readthrough",
            "strategy_status": "candidate_ready_for_analyst",
            "execution_mode": "propose_only",
            "payload": {"thesis": "Bullish AI_STORAGE read-through for NTNX."},
            "schema_version": 1,
            "created_at": "2026-06-01T14:30:00Z",
        }
    ]
    assert fake_client.conflicts_by_table == {
        "journal_records": "journal_record_id",
        "runs": "run_id",
        "decision_records": "decision_record_id",
    }
```

- [ ] **Step 2: Update the fake Supabase client to track multiple upsert tables**

In the `FakeSupabaseClient.__init__`, add:

```python
        self.upserts_by_table: dict[str, list[dict[str, Any]]] = {}
        self.conflicts_by_table: dict[str, str] = {}
```

In `FakeSupabaseClient.upsert`, after the existing assignments, add:

```python
        if self.table_name is not None:
            self.upserts_by_table[self.table_name] = rows
            self.conflicts_by_table[self.table_name] = on_conflict
```

- [ ] **Step 3: Run the projection write test and verify it fails**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py::test_supabase_adapter_upserts_run_and_decision_projections -q
```

Expected: FAIL because `SupabaseStorageAdapter` does not upsert `runs` or `decision_records` yet.

- [ ] **Step 4: Add projection upserts to the Supabase adapter**

In `src/prescient/storage/supabase.py`, replace `append_decision_journal_records` with:

```python
    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        storage_records = [
            StorageRecord.from_decision_journal_record(record) for record in records
        ]
        journal_rows = [record.to_journal_record_row() for record in storage_records]
        if not journal_rows:
            return StorageWriteResult(records_written=0)

        try:
            self._upsert_rows(
                table_name="journal_records",
                rows=journal_rows,
                on_conflict="journal_record_id",
            )
            run_rows = _project_run_rows(storage_records)
            if run_rows:
                self._upsert_rows(
                    table_name="runs",
                    rows=run_rows,
                    on_conflict="run_id",
                )
            decision_rows = [
                row
                for row in (
                    record.to_decision_record_row() for record in storage_records
                )
                if row is not None
            ]
            if decision_rows:
                self._upsert_rows(
                    table_name="decision_records",
                    rows=decision_rows,
                    on_conflict="decision_record_id",
                )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        return StorageWriteResult(records_written=len(journal_rows))

    def _upsert_rows(
        self,
        *,
        table_name: str,
        rows: list[dict[str, Any]],
        on_conflict: str,
    ) -> None:
        response = (
            self._client.schema(self._schema)
            .table(table_name)
            .upsert(rows, on_conflict=on_conflict, ignore_duplicates=False)
            .execute()
        )
        response_error = getattr(response, "error", None)
        if response_error is not None:
            raise RuntimeError(str(response_error))
```

Then add this helper below `_apply_query_filters`:

```python
def _project_run_rows(storage_records: list[StorageRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StorageRecord]] = {}
    for record in storage_records:
        grouped.setdefault(record.run_id, []).append(record)

    rows: list[dict[str, Any]] = []
    for records in grouped.values():
        first = min(records, key=lambda record: record.created_at)
        rows.append(first.to_run_row(record_count=len(records)))
    return rows
```

- [ ] **Step 5: Run focused storage tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_supabase_storage.py -q
```

Expected: all Supabase storage tests pass.

- [ ] **Step 6: Run runtime storage tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest tests/test_r6_4_storage_runtime.py -q
```

Expected: all runtime storage tests pass. These tests prove runtime still passes normalized `DecisionJournalRecord` models through the storage boundary and does not learn about concrete projection tables.

- [ ] **Step 7: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add src/prescient/storage/supabase.py tests/test_r6_4_supabase_storage.py
git commit -m "feat(storage): materialize run and decision projections"
```

---

## Task 3: Frontend decision-list types, schemas, and parser

**Files:**
- Create: `web/src/features/decisions/decision-list.types.ts`
- Create: `web/src/features/decisions/decision-list-schemas.ts`
- Create: `web/src/features/decisions/decision-list-format.ts`
- Create: `web/src/features/decisions/parse-decision-list.ts`
- Test: `web/__tests__/decision-list-schemas.test.ts`
- Test: `web/__tests__/parse-decision-list.test.ts`

- [ ] **Step 1: Write failing schema tests**

Create `web/__tests__/decision-list-schemas.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { DecisionListPayloadSchema } from "@/features/decisions/decision-list-schemas";

describe("DecisionListPayloadSchema", () => {
  it("parses the strategy_decision payload fields needed by the list", () => {
    const parsed = DecisionListPayloadSchema.parse({
      thesis: "Bullish AI_STORAGE read-through for NTNX.",
      decision_summary: "candidate_ready_for_analyst",
      candidate_brief: {
        target: "NTNX",
        theme: "AI_STORAGE",
        main_thesis: "AI storage peers reported strong demand.",
      },
    });

    expect(parsed.thesis).toContain("NTNX");
    expect(parsed.decision_summary).toBe("candidate_ready_for_analyst");
    expect(parsed.candidate_brief?.target).toBe("NTNX");
  });

  it("allows missing payload detail because table columns carry the list spine", () => {
    const parsed = DecisionListPayloadSchema.parse({});

    expect(parsed).toEqual({});
  });
});
```

- [ ] **Step 2: Write failing parser tests**

Create `web/__tests__/parse-decision-list.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  badgeVariantForDecisionValue,
  formatDecisionValue,
} from "@/features/decisions/decision-list-format";
import { parseDecisionList } from "@/features/decisions/parse-decision-list";
import type { DecisionRecordRow } from "@/features/decisions/decision-list.types";

function row(overrides: Partial<DecisionRecordRow> = {}): DecisionRecordRow {
  return {
    decision_record_id: "decision-1",
    run_id: "scheduled:2026-06-01",
    decision_id: "decision-1",
    decision_index: 0,
    trading_date: "2026-06-01",
    target: "NTNX",
    theme: "AI_STORAGE",
    strategy_type: "bullish_earnings_readthrough",
    strategy_status: "candidate_ready_for_analyst",
    execution_mode: "propose_only",
    payload: {
      thesis: "Bullish AI_STORAGE read-through for NTNX.",
      decision_summary: "candidate_ready_for_analyst",
      candidate_brief: {
        target: "NTNX",
        theme: "AI_STORAGE",
        main_thesis: "AI storage peers reported strong demand.",
      },
    },
    schema_version: 1,
    created_at: "2026-06-01T14:30:00Z",
    ...overrides,
  };
}

describe("parseDecisionList", () => {
  it("maps decision_records into display rows", () => {
    const decisions = parseDecisionList([row()]);

    expect(decisions).toEqual([
      {
        decisionId: "decision-1",
        runId: "scheduled:2026-06-01",
        decisionIndex: 0,
        tradingDate: "2026-06-01",
        target: "NTNX",
        theme: "AI_STORAGE",
        strategyType: "bullish_earnings_readthrough",
        status: "candidate_ready_for_analyst",
        outcome: "pending",
        mode: "propose_only",
        thesis: "Bullish AI_STORAGE read-through for NTNX.",
      },
    ]);
  });

  it("derives no_trade outcome for rejected strategy statuses", () => {
    const decisions = parseDecisionList([
      row({ strategy_status: "rejected_with_reason" }),
    ]);

    expect(decisions[0].outcome).toBe("no_trade");
  });

  it("uses explicit payload outcome_type when present", () => {
    const decisions = parseDecisionList([
      row({ payload: { outcome_type: "risk_blocked" } }),
    ]);

    expect(decisions[0].outcome).toBe("risk_blocked");
  });
});

describe("decision list formatting", () => {
  it("uses semantic badge variants without relying on color alone", () => {
    expect(badgeVariantForDecisionValue("candidate_ready_for_analyst")).toBe("success");
    expect(badgeVariantForDecisionValue("proposed")).toBe("success");
    expect(badgeVariantForDecisionValue("risk_blocked")).toBe("danger");
    expect(badgeVariantForDecisionValue("rejected_with_reason")).toBe("danger");
    expect(badgeVariantForDecisionValue("pending")).toBe("muted");
    expect(badgeVariantForDecisionValue(null)).toBe("warning");
  });

  it("formats snake case values for table text", () => {
    expect(formatDecisionValue("bullish_earnings_readthrough")).toBe(
      "bullish earnings readthrough"
    );
    expect(formatDecisionValue(null)).toBe("unknown");
  });
});
```

- [ ] **Step 3: Run parser/schema tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list-schemas.test.ts parse-decision-list.test.ts
```

Expected: FAIL because the feature files do not exist yet.

- [ ] **Step 4: Add decision-list types**

Create `web/src/features/decisions/decision-list.types.ts`:

```typescript
import type { Database } from "@/lib/supabase/database.types";

export type RunRow = Database["prescient_storage"]["Tables"]["runs"]["Row"];
export type DecisionRecordRow =
  Database["prescient_storage"]["Tables"]["decision_records"]["Row"];

export type DecisionListItem = {
  decisionId: string;
  runId: string;
  decisionIndex: number | null;
  tradingDate: string;
  target: string;
  theme: string | null;
  strategyType: string | null;
  status: string;
  outcome: string;
  mode: string | null;
  thesis: string | null;
};

export type BadgeVariant = "muted" | "success" | "danger" | "warning";
```

- [ ] **Step 5: Add Zod schema**

Create `web/src/features/decisions/decision-list-schemas.ts`:

```typescript
import { z } from "zod";

export const DecisionListPayloadSchema = z
  .object({
    thesis: z.string().optional(),
    decision_summary: z.string().optional(),
    outcome_type: z.string().optional(),
    candidate_brief: z
      .object({
        target: z.string().optional(),
        theme: z.string().nullable().optional(),
        main_thesis: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();
```

- [ ] **Step 6: Add formatting helpers**

Create `web/src/features/decisions/decision-list-format.ts`:

```typescript
import type { BadgeVariant } from "./decision-list.types";

const SUCCESS_VALUES = new Set([
  "approved",
  "candidate_ready_for_analyst",
  "proposed",
]);

const DANGER_VALUES = new Set([
  "blocked",
  "broker_rejected",
  "rejected",
  "rejected_with_reason",
  "risk_blocked",
]);

const MUTED_VALUES = new Set([
  "no_trade",
  "pending",
  "propose_only",
]);

export function badgeVariantForDecisionValue(
  value: string | null | undefined,
): BadgeVariant {
  if (!value) return "warning";
  const normalized = value.toLowerCase();
  if (SUCCESS_VALUES.has(normalized)) return "success";
  if (DANGER_VALUES.has(normalized)) return "danger";
  if (MUTED_VALUES.has(normalized)) return "muted";
  return "warning";
}

export function formatDecisionValue(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replaceAll("_", " ");
}
```

- [ ] **Step 7: Add parser**

Create `web/src/features/decisions/parse-decision-list.ts`:

```typescript
import { DecisionListPayloadSchema } from "./decision-list-schemas";
import type { DecisionListItem, DecisionRecordRow } from "./decision-list.types";

export function parseDecisionList(rows: DecisionRecordRow[]): DecisionListItem[] {
  return rows.map((row) => {
    const payload = DecisionListPayloadSchema.safeParse(row.payload ?? {});
    const parsedPayload = payload.success ? payload.data : {};
    const status =
      row.strategy_status ??
      parsedPayload.decision_summary ??
      "unknown";

    return {
      decisionId: row.decision_id,
      runId: row.run_id,
      decisionIndex: row.decision_index,
      tradingDate: row.trading_date,
      target: row.target ?? parsedPayload.candidate_brief?.target ?? "UNKNOWN",
      theme: row.theme ?? parsedPayload.candidate_brief?.theme ?? null,
      strategyType: row.strategy_type,
      status,
      outcome: deriveListOutcome(status, parsedPayload.outcome_type),
      mode: row.execution_mode,
      thesis: parsedPayload.thesis ?? parsedPayload.candidate_brief?.main_thesis ?? null,
    };
  });
}

function deriveListOutcome(status: string, explicitOutcome?: string): string {
  if (explicitOutcome) return explicitOutcome;
  const normalized = status.toLowerCase();
  if (normalized.includes("rejected") || normalized === "no_trade") {
    return "no_trade";
  }
  return "pending";
}
```

- [ ] **Step 8: Run parser/schema tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list-schemas.test.ts parse-decision-list.test.ts
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-list.types.ts \
  web/src/features/decisions/decision-list-schemas.ts \
  web/src/features/decisions/decision-list-format.ts \
  web/src/features/decisions/parse-decision-list.ts \
  web/__tests__/decision-list-schemas.test.ts \
  web/__tests__/parse-decision-list.test.ts
git commit -m "feat(web): parse projected decision list rows"
```

---

## Task 4: Frontend Supabase fetchers and TanStack Query hooks

**Files:**
- Create: `web/src/features/decisions/fetch-latest-run.ts`
- Create: `web/src/features/decisions/use-latest-run.ts`
- Create: `web/src/features/decisions/fetch-decisions.ts`
- Create: `web/src/features/decisions/use-decisions.ts`
- Test: `web/__tests__/fetch-decision-list.test.ts`

- [ ] **Step 1: Write failing fetcher tests**

Create `web/__tests__/fetch-decision-list.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { fetchDecisions } from "@/features/decisions/fetch-decisions";
import { fetchLatestRun } from "@/features/decisions/fetch-latest-run";

type FakeResult = { data: unknown; error: { message: string } | null };

function fakeSupabase(result: FakeResult) {
  const calls: string[] = [];
  return {
    calls,
    from(table: string) {
      calls.push(`from:${table}`);
      return {
        select(columns: string) {
          calls.push(`select:${columns}`);
          return this;
        },
        eq(column: string, value: string) {
          calls.push(`eq:${column}:${value}`);
          return this;
        },
        order(column: string, options: { ascending: boolean }) {
          calls.push(`order:${column}:${options.ascending}`);
          return this;
        },
        limit(value: number) {
          calls.push(`limit:${value}`);
          return Promise.resolve(result);
        },
      };
    },
  };
}

describe("decision list fetchers", () => {
  it("fetchLatestRun queries runs newest first and returns the first row", async () => {
    const supabase = fakeSupabase({
      data: [{ run_id: "scheduled:2026-06-01" }],
      error: null,
    });

    const run = await fetchLatestRun(supabase);

    expect(run).toEqual({ run_id: "scheduled:2026-06-01" });
    expect(supabase.calls).toEqual([
      "from:runs",
      "select:*",
      "order:created_at:false",
      "limit:1",
    ]);
  });

  it("fetchLatestRun returns null when there are no runs", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await expect(fetchLatestRun(supabase)).resolves.toBeNull();
  });

  it("fetchDecisions queries decision_records for one run in decision order", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await fetchDecisions(supabase, "scheduled:2026-06-01");

    expect(supabase.calls).toEqual([
      "from:decision_records",
      "select:*",
      "eq:run_id:scheduled:2026-06-01",
      "order:decision_index:true",
      "limit:500",
    ]);
  });

  it("throws readable Supabase errors", async () => {
    const supabase = fakeSupabase({
      data: null,
      error: { message: "permission denied for table decision_records" },
    });

    await expect(fetchDecisions(supabase, "scheduled:2026-06-01")).rejects.toThrow(
      "permission denied for table decision_records",
    );
  });
});
```

- [ ] **Step 2: Run fetcher tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- fetch-decision-list.test.ts
```

Expected: FAIL because fetcher files do not exist yet.

- [ ] **Step 3: Add latest-run fetcher**

Create `web/src/features/decisions/fetch-latest-run.ts`:

```typescript
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/supabase/database.types";
import type { RunRow } from "./decision-list.types";

type PrescientSupabase = Pick<
  SupabaseClient<Database, "prescient_storage">,
  "from"
>;

export async function fetchLatestRun(
  supabase: PrescientSupabase,
): Promise<RunRow | null> {
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1);

  if (error) {
    throw new Error(`Failed to load latest run: ${error.message}`);
  }

  return ((data ?? []) as RunRow[])[0] ?? null;
}
```

- [ ] **Step 4: Add decisions fetcher**

Create `web/src/features/decisions/fetch-decisions.ts`:

```typescript
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/supabase/database.types";
import type { DecisionListItem, DecisionRecordRow } from "./decision-list.types";
import { parseDecisionList } from "./parse-decision-list";

type PrescientSupabase = Pick<
  SupabaseClient<Database, "prescient_storage">,
  "from"
>;

export async function fetchDecisions(
  supabase: PrescientSupabase,
  runId: string,
): Promise<DecisionListItem[]> {
  const { data, error } = await supabase
    .from("decision_records")
    .select("*")
    .eq("run_id", runId)
    .order("decision_index", { ascending: true })
    .limit(500);

  if (error) {
    throw new Error(`Failed to load decisions: ${error.message}`);
  }

  return parseDecisionList((data ?? []) as DecisionRecordRow[]);
}
```

- [ ] **Step 5: Add TanStack Query hooks**

Create `web/src/features/decisions/use-latest-run.ts`:

```typescript
"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import { fetchLatestRun } from "./fetch-latest-run";

export function useLatestRun() {
  const supabase = useMemo(() => createClient(), []);

  return useQuery({
    queryKey: ["latest-run"],
    queryFn: () => fetchLatestRun(supabase),
    staleTime: 30_000,
  });
}
```

Create `web/src/features/decisions/use-decisions.ts`:

```typescript
"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import { fetchDecisions } from "./fetch-decisions";

export function useDecisions(runId: string | null | undefined) {
  const supabase = useMemo(() => createClient(), []);

  return useQuery({
    queryKey: ["decisions", runId],
    queryFn: () => fetchDecisions(supabase, runId!),
    enabled: Boolean(runId),
    staleTime: 30_000,
  });
}
```

- [ ] **Step 6: Run fetcher tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- fetch-decision-list.test.ts
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/fetch-latest-run.ts \
  web/src/features/decisions/use-latest-run.ts \
  web/src/features/decisions/fetch-decisions.ts \
  web/src/features/decisions/use-decisions.ts \
  web/__tests__/fetch-decision-list.test.ts
git commit -m "feat(web): add decision list queries"
```

---

## Task 5: Decision list table UI

**Files:**
- Create: `web/src/features/decisions/decision-list.tsx`
- Test: `web/__tests__/decision-list.test.tsx`

- [ ] **Step 1: Write failing table tests**

Create `web/__tests__/decision-list.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionList } from "@/features/decisions/decision-list";

describe("DecisionList", () => {
  it("renders a dense decision table with links to detail routes", () => {
    render(
      <DecisionList
        decisions={[
          {
            decisionId: "decision-1",
            runId: "scheduled:2026-06-01",
            decisionIndex: 0,
            tradingDate: "2026-06-01",
            target: "NTNX",
            theme: "AI_STORAGE",
            strategyType: "bullish_earnings_readthrough",
            status: "candidate_ready_for_analyst",
            outcome: "pending",
            mode: "propose_only",
            thesis: "Bullish AI_STORAGE read-through for NTNX.",
          },
        ]}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Strategy" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NTNX" })).toHaveAttribute(
      "href",
      "/decisions/decision-1",
    );
    expect(screen.getByText("candidate ready for analyst")).toBeInTheDocument();
    expect(screen.getByText("propose only")).toBeInTheDocument();
  });

  it("renders unknown for missing optional fields", () => {
    render(
      <DecisionList
        decisions={[
          {
            decisionId: "decision-2",
            runId: "scheduled:2026-06-01",
            decisionIndex: null,
            tradingDate: "2026-06-01",
            target: "PSTG",
            theme: null,
            strategyType: null,
            status: "unknown",
            outcome: "pending",
            mode: null,
            thesis: null,
          },
        ]}
      />,
    );

    expect(screen.getAllByText("unknown").length).toBeGreaterThanOrEqual(2);
  });
});
```

- [ ] **Step 2: Run the table tests and verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list.test.tsx
```

Expected: FAIL because `decision-list.tsx` does not exist yet.

- [ ] **Step 3: Add the table component**

Create `web/src/features/decisions/decision-list.tsx`:

```tsx
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import type { DecisionListItem } from "./decision-list.types";
import {
  badgeVariantForDecisionValue,
  formatDecisionValue,
} from "./decision-list-format";

export function DecisionList({ decisions }: { decisions: DecisionListItem[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Target</Th>
          <Th>Theme</Th>
          <Th>Strategy</Th>
          <Th>Status</Th>
          <Th>Outcome</Th>
          <Th>Mode</Th>
        </tr>
      </thead>
      <tbody>
        {decisions.map((decision) => (
          <tr key={decision.decisionId} className="hover:bg-muted/50">
            <Td className="font-medium">
              <Link
                href={`/decisions/${encodeURIComponent(decision.decisionId)}`}
                className="underline-offset-2 hover:underline"
              >
                {decision.target}
              </Link>
            </Td>
            <Td>{formatDecisionValue(decision.theme)}</Td>
            <Td>{formatDecisionValue(decision.strategyType)}</Td>
            <Td>
              <Badge variant={badgeVariantForDecisionValue(decision.status)}>
                {formatDecisionValue(decision.status)}
              </Badge>
            </Td>
            <Td>
              <Badge variant={badgeVariantForDecisionValue(decision.outcome)}>
                {formatDecisionValue(decision.outcome)}
              </Badge>
            </Td>
            <Td>
              <Badge variant={badgeVariantForDecisionValue(decision.mode)}>
                {formatDecisionValue(decision.mode)}
              </Badge>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
```

- [ ] **Step 4: Run the table tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list.test.tsx
```

Expected: all table tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-list.tsx web/__tests__/decision-list.test.tsx
git commit -m "feat(web): render decision list table"
```

---

## Task 6: Decision list client and `/decisions` route

**Files:**
- Create: `web/src/features/decisions/decision-list-client.tsx`
- Modify: `web/src/app/(app)/decisions/page.tsx`

- [ ] **Step 1: Add the decision-list client component**

Create `web/src/features/decisions/decision-list-client.tsx`:

```tsx
"use client";

import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { DecisionList } from "./decision-list";
import { useDecisions } from "./use-decisions";
import { useLatestRun } from "./use-latest-run";

export function DecisionListClient() {
  const latestRun = useLatestRun();
  const runId = latestRun.data?.run_id ?? null;
  const decisions = useDecisions(runId);

  if (latestRun.isPending) {
    return <LoadingState label="Loading latest run..." />;
  }

  if (latestRun.error) {
    return <ErrorState title={latestRun.error.message} />;
  }

  if (!latestRun.data) {
    return <EmptyState message="No run yet today." />;
  }

  if (decisions.isPending) {
    return <LoadingState label="Loading decisions..." />;
  }

  if (decisions.error) {
    return <ErrorState title={decisions.error.message} />;
  }

  if (!decisions.data || decisions.data.length === 0) {
    return <EmptyState message="No decisions for the latest run." />;
  }

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Decisions</h1>
        <p className="text-sm text-muted-foreground">
          Latest run: {latestRun.data.run_id}
        </p>
      </div>
      <DecisionList decisions={decisions.data} />
    </section>
  );
}
```

- [ ] **Step 2: Replace the Slice 0 placeholder page**

Replace `web/src/app/(app)/decisions/page.tsx` with:

```tsx
import { DecisionListClient } from "@/features/decisions/decision-list-client";

export default function DecisionsPage() {
  return <DecisionListClient />;
}
```

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test
```

Expected: all frontend tests pass.

- [ ] **Step 4: Verify build**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run build
```

Expected: production build succeeds; `/decisions` compiles.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-list-client.tsx "web/src/app/(app)/decisions/page.tsx"
git commit -m "feat(web): wire decision list into decisions route"
```

---

## Task 7: End-to-end verification with local projected data

**Files:** none unless verification exposes a defect

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
.venv/bin/python -m pytest \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_storage_runtime.py \
  tests/test_r6_4_supabase_migration.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend focused tests and build**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test && npm run build
```

Expected: all tests pass; production build succeeds.

- [ ] **Step 3: Start local Supabase and run the storage-backed round-trip fixture**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase start
```

Then run the existing opt-in Supabase round-trip test after Slice 0 local credentials are configured. This test writes a `strategy_decision` through `SupabaseStorageAdapter`, which exercises the new `runs` and `decision_records` projections in this slice:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
PRESCIENT_SUPABASE_INTEGRATION_TESTS=1 \
PRESCIENT_TEST_SUPABASE_URL=http://127.0.0.1:54321 \
PRESCIENT_TEST_SUPABASE_SERVICE_ROLE_KEY=<SERVICE_ROLE_KEY_FROM_SUPABASE_STATUS> \
PRESCIENT_TEST_SUPABASE_SCHEMA=prescient_storage \
.venv/bin/python -m pytest tests/test_r6_4_supabase_integration_roundtrip.py -q
```

Expected: the test passes and local Supabase contains at least one `journal_records` row plus matching `runs` and `decision_records` projection rows. Do not commit secrets.

- [ ] **Step 4: Verify projection rows exist**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
psql "$(supabase status -o env | grep DB_URL | cut -d= -f2- | tr -d '\"')" \
  -c "select run_id, status from prescient_storage.runs order by created_at desc limit 3;" \
  -c "select decision_id, target, theme, strategy_status, execution_mode from prescient_storage.decision_records order by created_at desc limit 3;"
```

Expected: `runs` includes the latest projected run and `decision_records` includes at least one projected strategy decision.

- [ ] **Step 5: Manually verify `/decisions`**

Run the app:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run dev
```

In a browser:

1. Sign in as the local operator.
2. Open `http://localhost:3000/decisions`.
3. With no data, verify the empty state appears.
4. With projected local rows, verify the table shows Target, Theme, Strategy, Status, Outcome, and Mode.
5. Click a target row and verify the URL becomes `/decisions/<decision_id>`.

Expected: no trade action controls appear anywhere on the page.

- [ ] **Step 6: Final checkpoint**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add src/prescient/storage/models.py \
  src/prescient/storage/supabase.py \
  tests/test_r6_4_supabase_storage.py \
  tests/test_r6_4_storage_runtime.py \
  web/src/features/decisions/ \
  "web/src/app/(app)/decisions/page.tsx" \
  web/__tests__/
git commit -m "feat(web): complete decision list slice"
```

---

## Definition of Done (Slice 1)

- `SupabaseStorageAdapter.append_decision_journal_records()` still writes canonical `journal_records`.
- The same storage write also materializes `runs` and `decision_records` projections idempotently.
- `/decisions` no longer shows the Slice 0 placeholder.
- `useLatestRun()` reads the latest `runs` row through Supabase.
- `useDecisions(runId)` reads `decision_records` for the selected run through Supabase.
- The page renders loading, error, empty, and populated states.
- The populated table shows Target, Theme, Strategy, Status, Outcome, and Mode.
- Status/outcome/mode use semantic badges with text labels, not color-only meaning.
- Rows link to `/decisions/[decision_id]`, matching the Slice 2 plan.
- No buy, approve, edit-size, client-side Claude, or browser database write behavior exists.
- Backend focused tests pass: `tests/test_r6_4_supabase_storage.py`, `tests/test_r6_4_storage_runtime.py`, `tests/test_r6_4_supabase_migration.py`.
- Frontend tests and build pass: `npm test && npm run build`.

Slice 1 stops at the decision list. The full journal chain stays in Slice 2.
