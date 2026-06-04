# Prescient Web Frontend — Slice 4 (Backtest Analytics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated `/backtest` analytics page that reads the latest persisted backtest report, validates it against the backend `BacktestRunResult` shape, and renders win rate, drawdown, Sharpe, return-vs-buy-and-hold, equity curve, outcome mix, setup rows, warnings, and exclusions.

**Architecture:** This slice stays read-only. The browser reads `prescient_storage.learning_reports` through the existing Supabase client and TanStack Query, then parses `report_type = "backtest"` payloads with Zod. A small backend storage task is included first because the table exists but the Supabase adapter does not yet provide a way to persist backtest reports; the UI never runs backtests, writes reports, calls brokers, calls Claude, or mutates trading state.

**Tech Stack:** Existing Slice 0-3 web stack: Next.js App Router + TypeScript, Tailwind CSS, shadcn-style primitives, TanStack Query v5, Supabase JS, Zod, Vitest + React Testing Library. Add Recharts 3 for responsive SVG charts. Backend additions use Python, Pydantic v2, pytest, uv, and the existing Supabase storage adapter test pattern.

**Reference spec:** `docs/superpowers/specs/2026-06-03-prescient-web-frontend-design.md`

**Backend references:** `src/prescient/backtest/models.py`, `src/prescient/analytics/models.py`, `docs/prd/09-backtest-r9-3-performance-metrics-prd.md`, `supabase/migrations/20260603063259_r6_4_storage.sql`

> **Prerequisite:** Slices 0-3 are complete. This plan assumes `web/` exists, auth/session protection is in place, the shared primitives and state components exist, `/backtest` is present in the authenticated nav, and the generated Supabase types include `prescient_storage.learning_reports`.

> **Git note:** `prescient/` was not a git repository when Slice 0 was written. If git is still not initialized, skip every `git add` / `git commit` step and treat each task as a logical checkpoint. Once git exists, the commit steps are valid as written.

---

## Source Contract

Slice 4 implements only this part of the approved frontend spec:

- Route: `/backtest`
- Source: persisted `prescient_storage.learning_reports` rows with `report_type = "backtest"`
- Payload shape: backend `BacktestRunResult`
- Metrics: win rate, max drawdown, Sharpe, total return, buy-and-hold return, excess return, beats-buy-and-hold
- First charts: equity curve, strategy-vs-buy-and-hold return comparison, outcome distribution
- Required states: loading, error, empty
- No actions: no backtest runner button, no trade action, no parameter changes, no DB writes from the browser

`learning_reports` table columns from the current migration:

```sql
learning_report_id text primary key,
run_id text,
report_date date not null,
target text,
theme text,
report_type text not null,
payload jsonb not null default '{}'::jsonb,
schema_version integer not null default 1,
created_at timestamptz not null default now()
```

`BacktestSummary` fields this page renders:

```typescript
total_setups: number;
candidate_ready_count: number;
rejected_count: number;
not_evaluable_count: number;
trade_win_count: number;
trade_loss_count: number;
trade_flat_count: number;
trade_not_evaluable_count: number;
average_net_pnl: number | null;
median_net_pnl: number | null;
by_theme: Record<string, number>;
by_ticker: Record<string, number>;
by_expression: Record<string, number>;
top_rejection_reasons: Record<string, number>;
win_rate: number | null;
max_drawdown_pct: number | null;
sharpe_ratio: number | null;
total_return_pct: number | null;
buy_hold_total_return_pct: number | null;
beats_buy_and_hold: boolean | null;
excess_return_pct: number | null;
benchmark_status: "evaluable" | "not_evaluable";
metrics_status: "evaluable" | "not_evaluable";
excluded_counts: Record<string, number>;
warnings: string[];
```

---

## File Structure

Backend persistence bridge:

```
src/prescient/backtest/reports.py                  # NEW: convert BacktestRunResult to learning_reports row
src/prescient/backtest/__init__.py                 # MODIFY: export report helper constants/functions
src/prescient/storage/supabase.py                  # MODIFY: append_learning_reports()
tests/test_r9_4_backtest_report_storage.py         # NEW: backend report-row and adapter tests
```

Frontend analytics slice:

```
web/package.json                                                   # MODIFY: add recharts
web/src/app/(app)/backtest/page.tsx                                # CREATE/MODIFY: authenticated route
web/src/features/backtest/hooks/use-backtest-report.ts             # NEW: TanStack Query hook
web/src/features/backtest/lib/backtest-report.schema.ts            # NEW: Zod parse boundary
web/src/features/backtest/lib/backtest-view-model.ts               # NEW: formatting and chart data
web/src/features/backtest/components/backtest-page.tsx             # NEW: loading/error/empty/ready composer
web/src/features/backtest/components/metric-card.tsx               # NEW: compact KPI card
web/src/features/backtest/components/return-comparison-chart.tsx   # NEW: bar chart
web/src/features/backtest/components/equity-curve-chart.tsx        # NEW: line chart
web/src/features/backtest/components/outcome-distribution-chart.tsx # NEW: bar chart
web/src/features/backtest/components/setup-results-table.tsx       # NEW: setup-level table
web/src/features/backtest/components/report-diagnostics.tsx        # NEW: warnings/exclusions panel
web/src/features/backtest/__tests__/backtest-report.schema.test.ts # NEW
web/src/features/backtest/__tests__/backtest-view-model.test.ts    # NEW
web/src/features/backtest/__tests__/use-backtest-report.test.ts    # NEW
web/src/features/backtest/__tests__/backtest-page.test.tsx         # NEW
```

---

## Task 1: Backend — persist backtest results as learning reports

**Why first:** the frontend read path is `learning_reports`, but the current Supabase adapter only writes `journal_records`. This task adds a minimal, cold-path bridge from `BacktestRunResult` to a `learning_reports` row. It does not run backtests, fetch data, place orders, or touch hot runtime code.

**Files:**
- Create: `tests/test_r9_4_backtest_report_storage.py`
- Create: `src/prescient/backtest/reports.py`
- Modify: `src/prescient/backtest/__init__.py`
- Modify: `src/prescient/storage/supabase.py`

- [ ] **Step 1: Write the failing backend tests**

Create `tests/test_r9_4_backtest_report_storage.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any

from prescient.backtest import (
    BacktestOutcome,
    BacktestRunRequest,
    BacktestRunResult,
    BacktestSetupResult,
    BacktestTradeExpression,
    TradePnlOutcome,
)
from prescient.backtest.reports import (
    BACKTEST_LEARNING_REPORT_TYPE,
    backtest_result_to_learning_report_row,
)
from prescient.storage.supabase import SupabaseStorageAdapter


def test_backtest_result_maps_to_learning_report_row() -> None:
    result = _backtest_result()

    row = backtest_result_to_learning_report_row(
        result,
        report_date=date(2026, 6, 4),
        target="ntnx",
        theme="ai_storage",
    )

    assert row["learning_report_id"] == "backtest:r9-4-fixture"
    assert row["run_id"] == "r9-4-fixture"
    assert row["report_date"] == "2026-06-04"
    assert row["target"] == "NTNX"
    assert row["theme"] == "AI_STORAGE"
    assert row["report_type"] == BACKTEST_LEARNING_REPORT_TYPE
    assert row["schema_version"] == 1
    assert row["payload"]["run_id"] == "r9-4-fixture"
    assert row["payload"]["summary"]["win_rate"] == 1.0
    assert row["payload"]["summary"]["beats_buy_and_hold"] is True


def test_supabase_adapter_upserts_learning_report_rows() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")
    row = backtest_result_to_learning_report_row(
        _backtest_result(),
        report_date=date(2026, 6, 4),
    )

    result = adapter.append_learning_reports([row])

    assert result.ok is True
    assert result.records_written == 1
    assert fake_client.schema_name == "prescient_storage"
    assert fake_client.table_name == "learning_reports"
    assert fake_client.on_conflict == "learning_report_id"
    assert fake_client.rows[0]["learning_report_id"] == "backtest:r9-4-fixture"
    assert fake_client.rows[0]["report_type"] == "backtest"


def test_supabase_adapter_skips_empty_learning_report_batch() -> None:
    fake_client = FakeSupabaseClient()
    adapter = SupabaseStorageAdapter(client=fake_client, schema="prescient_storage")

    result = adapter.append_learning_reports([])

    assert result.ok is True
    assert result.records_written == 0
    assert fake_client.table_name is None


def _backtest_result() -> BacktestRunResult:
    request = BacktestRunRequest(
        run_id="r9-4-fixture",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        starting_equity=10_000.0,
    )
    setup = BacktestSetupResult(
        setup_id="setup-1",
        ticker="ntnx",
        target="ntnx",
        theme="ai_storage",
        entry_date=date(2026, 2, 1),
        exit_date=date(2026, 2, 2),
        strategy_status="candidate_ready_for_analyst",
        expression=BacktestTradeExpression.CALL_OPTION,
        recommended_expression=BacktestTradeExpression.CALL_OPTION,
        allocated_capital=120.0,
        underlying_entry_price=50.0,
        underlying_exit_price=52.0,
        trade_pnl=TradePnlOutcome(
            ticker="ntnx",
            expression=BacktestTradeExpression.CALL_OPTION,
            quantity=1,
            entry_price=1.2,
            exit_price=1.9,
            gross_pnl=70.0,
            net_pnl=70.0,
            outcome=BacktestOutcome.WIN,
        ),
    )
    return BacktestRunResult(
        run_id="r9-4-fixture",
        request=request,
        setups=[setup],
    )


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.schema_name: str | None = None
        self.table_name: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.on_conflict: str | None = None

    def schema(self, schema_name: str) -> "FakeSupabaseClient":
        self.schema_name = schema_name
        return self

    def table(self, table_name: str) -> "FakeSupabaseClient":
        self.table_name = table_name
        return self

    def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
        ignore_duplicates: bool = False,
    ) -> "FakeSupabaseClient":
        assert ignore_duplicates is False
        self.rows = rows
        self.on_conflict = on_conflict
        return self

    def execute(self) -> object:
        return type("FakeResponse", (), {"data": self.rows, "error": None})()
```

- [ ] **Step 2: Run the backend tests and verify RED**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_r9_4_backtest_report_storage.py -q
```

Expected: fails because `prescient.backtest.reports` and `append_learning_reports()` do not exist.

- [ ] **Step 3: Add the backtest report row helper**

Create `src/prescient/backtest/reports.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any

from prescient.backtest.models import BacktestRunResult


BACKTEST_LEARNING_REPORT_TYPE = "backtest"
BACKTEST_LEARNING_REPORT_SCHEMA_VERSION = 1


def backtest_result_to_learning_report_row(
    result: BacktestRunResult,
    *,
    report_date: date,
    target: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    return {
        "learning_report_id": f"{BACKTEST_LEARNING_REPORT_TYPE}:{result.run_id}",
        "run_id": result.run_id,
        "report_date": report_date.isoformat(),
        "target": _normalize_optional_upper(target),
        "theme": _normalize_optional_upper(theme),
        "report_type": BACKTEST_LEARNING_REPORT_TYPE,
        "payload": result.model_dump(mode="json"),
        "schema_version": BACKTEST_LEARNING_REPORT_SCHEMA_VERSION,
    }


def _normalize_optional_upper(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned.upper() if cleaned else None
```

- [ ] **Step 4: Export the helper**

Modify `src/prescient/backtest/__init__.py` so it includes:

```python
from prescient.backtest.reports import (
    BACKTEST_LEARNING_REPORT_TYPE,
    backtest_result_to_learning_report_row,
)
```

and add these names to `__all__`:

```python
"BACKTEST_LEARNING_REPORT_TYPE",
"backtest_result_to_learning_report_row",
```

- [ ] **Step 5: Add `append_learning_reports()` to the Supabase adapter**

In `src/prescient/storage/supabase.py`, add this method to `SupabaseStorageAdapter`:

```python
    def append_learning_reports(
        self,
        reports: Iterable[dict[str, Any]],
    ) -> StorageWriteResult:
        rows = list(reports)
        if not rows:
            return StorageWriteResult(records_written=0)

        try:
            response = (
                self._client.schema(self._schema)
                .table("learning_reports")
                .upsert(rows, on_conflict="learning_report_id", ignore_duplicates=False)
                .execute()
            )
        except Exception as exc:
            return StorageWriteResult(errors=[_error_from_exception(exc)])

        response_error = getattr(response, "error", None)
        if response_error is not None:
            return StorageWriteResult(errors=[_error_from_exception(response_error)])

        return StorageWriteResult(records_written=len(rows))
```

- [ ] **Step 6: Run the backend tests and verify GREEN**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_r9_4_backtest_report_storage.py tests/test_r6_4_supabase_storage.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add src/prescient/backtest/__init__.py src/prescient/backtest/reports.py src/prescient/storage/supabase.py tests/test_r9_4_backtest_report_storage.py
git commit -m "feat(backtest): persist backtest results as learning reports"
```

---

## Task 2: Frontend — add chart dependency

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1: Install Recharts**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm install recharts@^3
```

Expected: `package.json` includes `recharts`; lockfile updates.

- [ ] **Step 2: Verify existing frontend tests still pass**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run
```

Expected: existing Slice 0-3 frontend tests pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/package.json web/package-lock.json
git commit -m "chore(web): add Recharts for backtest analytics"
```

---

## Task 3: Frontend — Zod parse boundary for backtest reports

**Files:**
- Create: `web/src/features/backtest/__tests__/backtest-report.schema.test.ts`
- Create: `web/src/features/backtest/lib/backtest-report.schema.ts`

- [ ] **Step 1: Write schema tests**

Create `web/src/features/backtest/__tests__/backtest-report.schema.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { parseBacktestReportRow } from "../lib/backtest-report.schema";

const validRow = {
  learning_report_id: "backtest:r9-4-fixture",
  run_id: "r9-4-fixture",
  report_date: "2026-06-04",
  target: null,
  theme: null,
  report_type: "backtest",
  created_at: "2026-06-04T12:00:00Z",
  schema_version: 1,
  payload: {
    run_id: "r9-4-fixture",
    request: {
      run_id: "r9-4-fixture",
      start_date: "2026-01-01",
      end_date: "2026-03-31",
      max_events: null,
      strategy_type: "bullish_earnings_readthrough",
      evaluation_horizon_days: 1,
      include_rejected_candidates: true,
      include_trade_pnl: true,
      positive_followthrough_threshold_pct: 1,
      negative_followthrough_threshold_pct: -1,
      starting_equity: 10000,
      annual_risk_free_rate: 0,
    },
    setups: [
      {
        setup_id: "setup-1",
        target: "NTNX",
        ticker: "NTNX",
        theme: "AI_STORAGE",
        earnings_date: null,
        entry_date: "2026-02-01",
        exit_date: "2026-02-02",
        strategy_status: "candidate_ready_for_analyst",
        recommended_expression: "CALL_OPTION",
        expression: "CALL_OPTION",
        allocated_capital: 120,
        underlying_entry_price: 50,
        underlying_exit_price: 52,
        underlying_outcome: null,
        trade_pnl: {
          ticker: "NTNX",
          expression: "CALL_OPTION",
          quantity: 1,
          entry_price: 1.2,
          exit_price: 1.9,
          gross_pnl: 70,
          fees: 0,
          net_pnl: 70,
          return_on_risk_pct: 58.3,
          outcome: "win",
          reason: null,
          not_evaluable_reason: null,
        },
        reported_peers: ["CRM"],
        rejection_reasons: [],
        warnings: [],
      },
    ],
    summary: {
      total_setups: 1,
      candidate_ready_count: 1,
      rejected_count: 0,
      not_evaluable_count: 0,
      underlying_win_count: 0,
      underlying_loss_count: 0,
      underlying_flat_count: 0,
      underlying_not_evaluable_count: 0,
      trade_win_count: 1,
      trade_loss_count: 0,
      trade_flat_count: 0,
      trade_not_evaluable_count: 0,
      average_underlying_return_pct: null,
      median_underlying_return_pct: null,
      average_net_pnl: 70,
      median_net_pnl: 70,
      by_theme: { AI_STORAGE: 1 },
      by_ticker: { NTNX: 1 },
      by_expression: { CALL_OPTION: 1 },
      top_rejection_reasons: {},
      win_rate: 1,
      max_drawdown_pct: 0,
      sharpe_ratio: null,
      total_return_pct: 0.7,
      buy_hold_total_return_pct: 0.044,
      beats_buy_and_hold: true,
      excess_return_pct: 0.656,
      benchmark_status: "evaluable",
      metrics_status: "evaluable",
      excluded_counts: {},
      warnings: [],
    },
    warnings: [],
  },
};

describe("parseBacktestReportRow", () => {
  it("parses a persisted backtest report row", () => {
    const report = parseBacktestReportRow(validRow);

    expect(report.learning_report_id).toBe("backtest:r9-4-fixture");
    expect(report.payload.summary.win_rate).toBe(1);
    expect(report.payload.setups[0].trade_pnl?.net_pnl).toBe(70);
  });

  it("rejects non-backtest report rows", () => {
    expect(() =>
      parseBacktestReportRow({
        ...validRow,
        report_type: "learning_report",
      }),
    ).toThrow("Expected report_type backtest");
  });

  it("rejects malformed payloads loudly", () => {
    expect(() =>
      parseBacktestReportRow({
        ...validRow,
        payload: {
          run_id: "r9-4-fixture",
          summary: {
            win_rate: 1,
          },
        },
      }),
    ).toThrow();
  });
});
```

- [ ] **Step 2: Run schema tests and verify RED**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-report.schema.test.ts
```

Expected: fails because the schema module does not exist.

- [ ] **Step 3: Implement the schema module**

Create `web/src/features/backtest/lib/backtest-report.schema.ts`:

```typescript
import { z } from "zod";

const nullableNumber = z.number().nullable();
const nullableString = z.string().nullable();

const MetricsStatusSchema = z.enum(["evaluable", "not_evaluable"]);
const BacktestOutcomeSchema = z.enum(["win", "loss", "flat", "not_evaluable"]);
const BacktestTradeExpressionSchema = z.enum(["STOCK", "CALL_OPTION"]);

const BacktestRunRequestSchema = z
  .object({
    run_id: z.string(),
    start_date: z.string(),
    end_date: z.string(),
    max_events: z.number().int().nullable(),
    strategy_type: z.string(),
    evaluation_horizon_days: z.number().int(),
    include_rejected_candidates: z.boolean(),
    include_trade_pnl: z.boolean(),
    positive_followthrough_threshold_pct: z.number(),
    negative_followthrough_threshold_pct: z.number(),
    starting_equity: z.number(),
    annual_risk_free_rate: z.number(),
  })
  .strict();

const UnderlyingOutcomeSchema = z
  .object({
    ticker: z.string(),
    evaluation_start: z.string(),
    evaluation_end: z.string(),
    entry_reference_price: nullableNumber,
    exit_reference_price: nullableNumber,
    return_pct: nullableNumber,
    expected_direction: z.string(),
    outcome: BacktestOutcomeSchema,
    reason: nullableString,
  })
  .strict();

const TradePnlSchema = z
  .object({
    ticker: z.string(),
    expression: BacktestTradeExpressionSchema,
    quantity: z.number(),
    entry_price: nullableNumber,
    exit_price: nullableNumber,
    gross_pnl: nullableNumber,
    fees: z.number(),
    net_pnl: nullableNumber,
    return_on_risk_pct: nullableNumber,
    outcome: BacktestOutcomeSchema,
    reason: nullableString,
    not_evaluable_reason: nullableString,
  })
  .strict();

export const BacktestSetupResultSchema = z
  .object({
    setup_id: z.string(),
    target: z.string(),
    ticker: z.string(),
    theme: nullableString,
    earnings_date: nullableString,
    entry_date: z.string(),
    exit_date: z.string(),
    strategy_status: z.string(),
    recommended_expression: BacktestTradeExpressionSchema.nullable(),
    expression: BacktestTradeExpressionSchema,
    allocated_capital: z.number(),
    underlying_entry_price: nullableNumber,
    underlying_exit_price: nullableNumber,
    underlying_outcome: UnderlyingOutcomeSchema.nullable(),
    trade_pnl: TradePnlSchema.nullable(),
    reported_peers: z.array(z.string()),
    rejection_reasons: z.array(z.string()),
    warnings: z.array(z.string()),
  })
  .strict();

export const BacktestSummarySchema = z
  .object({
    total_setups: z.number().int(),
    candidate_ready_count: z.number().int(),
    rejected_count: z.number().int(),
    not_evaluable_count: z.number().int(),
    underlying_win_count: z.number().int(),
    underlying_loss_count: z.number().int(),
    underlying_flat_count: z.number().int(),
    underlying_not_evaluable_count: z.number().int(),
    trade_win_count: z.number().int(),
    trade_loss_count: z.number().int(),
    trade_flat_count: z.number().int(),
    trade_not_evaluable_count: z.number().int(),
    average_underlying_return_pct: nullableNumber,
    median_underlying_return_pct: nullableNumber,
    average_net_pnl: nullableNumber,
    median_net_pnl: nullableNumber,
    by_theme: z.record(z.string(), z.number().int()),
    by_ticker: z.record(z.string(), z.number().int()),
    by_expression: z.record(z.string(), z.number().int()),
    top_rejection_reasons: z.record(z.string(), z.number().int()),
    win_rate: nullableNumber,
    max_drawdown_pct: nullableNumber,
    sharpe_ratio: nullableNumber,
    total_return_pct: nullableNumber,
    buy_hold_total_return_pct: nullableNumber,
    beats_buy_and_hold: z.boolean().nullable(),
    excess_return_pct: nullableNumber,
    benchmark_status: MetricsStatusSchema,
    metrics_status: MetricsStatusSchema,
    excluded_counts: z.record(z.string(), z.number().int()),
    warnings: z.array(z.string()),
  })
  .strict();

export const BacktestReportPayloadSchema = z
  .object({
    run_id: z.string(),
    request: BacktestRunRequestSchema.nullable(),
    setups: z.array(BacktestSetupResultSchema),
    summary: BacktestSummarySchema,
    warnings: z.array(z.string()),
  })
  .strict();

const RawBacktestReportRowSchema = z
  .object({
    learning_report_id: z.string(),
    run_id: nullableString,
    report_date: z.string(),
    target: nullableString,
    theme: nullableString,
    report_type: z.string(),
    payload: z.unknown(),
    schema_version: z.number().int(),
    created_at: z.string(),
  })
  .strict();

export type BacktestReportPayload = z.infer<typeof BacktestReportPayloadSchema>;
export type BacktestSetupResult = z.infer<typeof BacktestSetupResultSchema>;
export type BacktestSummary = z.infer<typeof BacktestSummarySchema>;

export type BacktestReportRow = Omit<
  z.infer<typeof RawBacktestReportRowSchema>,
  "payload"
> & {
  payload: BacktestReportPayload;
};

export function parseBacktestReportRow(row: unknown): BacktestReportRow {
  const parsedRow = RawBacktestReportRowSchema.parse(row);
  if (parsedRow.report_type !== "backtest") {
    throw new Error(`Expected report_type backtest, got ${parsedRow.report_type}`);
  }

  return {
    ...parsedRow,
    payload: BacktestReportPayloadSchema.parse(parsedRow.payload),
  };
}
```

- [ ] **Step 4: Run schema tests and verify GREEN**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-report.schema.test.ts
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/backtest/__tests__/backtest-report.schema.test.ts web/src/features/backtest/lib/backtest-report.schema.ts
git commit -m "feat(web): add backtest report parse boundary"
```

---

## Task 4: Frontend — view model and chart data

**Files:**
- Create: `web/src/features/backtest/__tests__/backtest-view-model.test.ts`
- Create: `web/src/features/backtest/lib/backtest-view-model.ts`

- [ ] **Step 1: Write view-model tests**

Create `web/src/features/backtest/__tests__/backtest-view-model.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import type { BacktestReportRow } from "../lib/backtest-report.schema";
import { buildBacktestViewModel } from "../lib/backtest-view-model";

describe("buildBacktestViewModel", () => {
  it("formats KPI cards and return comparison", () => {
    const viewModel = buildBacktestViewModel(reportFixture);

    expect(viewModel.metricCards).toEqual([
      { label: "Win rate", value: "50.0%", detail: "1W / 1L / 0F", tone: "neutral" },
      { label: "Total return", value: "1.5%", detail: "$150.00 net P&L", tone: "positive" },
      { label: "Max drawdown", value: "0.5%", detail: "Lower is better", tone: "neutral" },
      { label: "Sharpe", value: "1.20", detail: "Risk-adjusted return", tone: "positive" },
      { label: "Vs buy & hold", value: "+1.0%", detail: "Beat benchmark", tone: "positive" },
    ]);
    expect(viewModel.returnComparison).toEqual([
      { name: "Strategy", returnPct: 1.5 },
      { name: "Buy & hold", returnPct: 0.5 },
    ]);
  });

  it("builds an equity curve from persisted setup P&L", () => {
    const viewModel = buildBacktestViewModel(reportFixture);

    expect(viewModel.equityCurve).toEqual([
      { date: "2026-02-02", setupId: "setup-1", pnl: 200, equity: 10200 },
      { date: "2026-02-03", setupId: "setup-2", pnl: -50, equity: 10150 },
    ]);
  });

  it("keeps non-evaluable setup counts visible", () => {
    const viewModel = buildBacktestViewModel(reportFixture);

    expect(viewModel.outcomeDistribution).toEqual([
      { name: "Wins", count: 1 },
      { name: "Losses", count: 1 },
      { name: "Flat", count: 0 },
      { name: "Not evaluable", count: 1 },
    ]);
    expect(viewModel.excludedCounts).toEqual([{ reason: "missing_strategy_pnl", count: 1 }]);
  });
});

const reportFixture: BacktestReportRow = {
  learning_report_id: "backtest:r9-4-fixture",
  run_id: "r9-4-fixture",
  report_date: "2026-06-04",
  target: null,
  theme: null,
  report_type: "backtest",
  created_at: "2026-06-04T12:00:00Z",
  schema_version: 1,
  payload: {
    run_id: "r9-4-fixture",
    request: {
      run_id: "r9-4-fixture",
      start_date: "2026-01-01",
      end_date: "2026-03-31",
      max_events: null,
      strategy_type: "bullish_earnings_readthrough",
      evaluation_horizon_days: 1,
      include_rejected_candidates: true,
      include_trade_pnl: true,
      positive_followthrough_threshold_pct: 1,
      negative_followthrough_threshold_pct: -1,
      starting_equity: 10000,
      annual_risk_free_rate: 0,
    },
    setups: [
      {
        setup_id: "setup-1",
        target: "NTNX",
        ticker: "NTNX",
        theme: "AI_STORAGE",
        earnings_date: null,
        entry_date: "2026-02-01",
        exit_date: "2026-02-02",
        strategy_status: "candidate_ready_for_analyst",
        recommended_expression: "CALL_OPTION",
        expression: "CALL_OPTION",
        allocated_capital: 120,
        underlying_entry_price: 50,
        underlying_exit_price: 52,
        underlying_outcome: null,
        trade_pnl: {
          ticker: "NTNX",
          expression: "CALL_OPTION",
          quantity: 1,
          entry_price: 1.2,
          exit_price: 3.2,
          gross_pnl: 200,
          fees: 0,
          net_pnl: 200,
          return_on_risk_pct: 166.7,
          outcome: "win",
          reason: null,
          not_evaluable_reason: null,
        },
        reported_peers: ["CRM"],
        rejection_reasons: [],
        warnings: [],
      },
      {
        setup_id: "setup-2",
        target: "ADBE",
        ticker: "ADBE",
        theme: "AI_SOFTWARE",
        earnings_date: null,
        entry_date: "2026-02-02",
        exit_date: "2026-02-03",
        strategy_status: "candidate_ready_for_analyst",
        recommended_expression: "STOCK",
        expression: "STOCK",
        allocated_capital: 1000,
        underlying_entry_price: 50,
        underlying_exit_price: 49.5,
        underlying_outcome: null,
        trade_pnl: {
          ticker: "ADBE",
          expression: "STOCK",
          quantity: 100,
          entry_price: 50,
          exit_price: 49.5,
          gross_pnl: -50,
          fees: 0,
          net_pnl: -50,
          return_on_risk_pct: -5,
          outcome: "loss",
          reason: null,
          not_evaluable_reason: null,
        },
        reported_peers: ["CRM"],
        rejection_reasons: [],
        warnings: [],
      },
    ],
    summary: {
      total_setups: 3,
      candidate_ready_count: 2,
      rejected_count: 0,
      not_evaluable_count: 1,
      underlying_win_count: 0,
      underlying_loss_count: 0,
      underlying_flat_count: 0,
      underlying_not_evaluable_count: 0,
      trade_win_count: 1,
      trade_loss_count: 1,
      trade_flat_count: 0,
      trade_not_evaluable_count: 1,
      average_underlying_return_pct: null,
      median_underlying_return_pct: null,
      average_net_pnl: 75,
      median_net_pnl: 75,
      by_theme: { AI_STORAGE: 1, AI_SOFTWARE: 1 },
      by_ticker: { NTNX: 1, ADBE: 1 },
      by_expression: { CALL_OPTION: 1, STOCK: 1 },
      top_rejection_reasons: {},
      win_rate: 0.5,
      max_drawdown_pct: 0.5,
      sharpe_ratio: 1.2,
      total_return_pct: 1.5,
      buy_hold_total_return_pct: 0.5,
      beats_buy_and_hold: true,
      excess_return_pct: 1,
      benchmark_status: "evaluable",
      metrics_status: "evaluable",
      excluded_counts: { missing_strategy_pnl: 1 },
      warnings: ["one setup was not evaluable"],
    },
    warnings: [],
  },
};
```

- [ ] **Step 2: Run view-model tests and verify RED**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-view-model.test.ts
```

Expected: fails because `backtest-view-model.ts` does not exist.

- [ ] **Step 3: Implement the view model**

Create `web/src/features/backtest/lib/backtest-view-model.ts`:

```typescript
import type { BacktestReportRow, BacktestSetupResult } from "./backtest-report.schema";

export type MetricTone = "positive" | "negative" | "neutral";

export type MetricCardModel = {
  label: string;
  value: string;
  detail: string;
  tone: MetricTone;
};

export type ReturnComparisonPoint = {
  name: "Strategy" | "Buy & hold";
  returnPct: number;
};

export type EquityCurvePoint = {
  date: string;
  setupId: string;
  pnl: number;
  equity: number;
};

export type OutcomeDistributionPoint = {
  name: "Wins" | "Losses" | "Flat" | "Not evaluable";
  count: number;
};

export type CountRow = {
  reason: string;
  count: number;
};

export type BacktestViewModel = {
  title: string;
  subtitle: string;
  metricCards: MetricCardModel[];
  returnComparison: ReturnComparisonPoint[];
  equityCurve: EquityCurvePoint[];
  outcomeDistribution: OutcomeDistributionPoint[];
  setupRows: BacktestSetupResult[];
  excludedCounts: CountRow[];
  warnings: string[];
};

export function buildBacktestViewModel(report: BacktestReportRow): BacktestViewModel {
  const { payload } = report;
  const summary = payload.summary;
  const startingEquity = payload.request?.starting_equity ?? 10_000;
  const totalNetPnl = sumNetPnl(payload.setups);
  const excessReturn = summary.excess_return_pct ?? 0;

  return {
    title: "Backtest analytics",
    subtitle: `Report ${report.learning_report_id} · ${report.report_date}`,
    metricCards: [
      {
        label: "Win rate",
        value: formatRatioAsPercent(summary.win_rate),
        detail: `${summary.trade_win_count}W / ${summary.trade_loss_count}L / ${summary.trade_flat_count}F`,
        tone: "neutral",
      },
      {
        label: "Total return",
        value: formatPercent(summary.total_return_pct),
        detail: `${formatCurrency(totalNetPnl)} net P&L`,
        tone: toneForNumber(summary.total_return_pct),
      },
      {
        label: "Max drawdown",
        value: formatPercent(summary.max_drawdown_pct),
        detail: "Lower is better",
        tone: "neutral",
      },
      {
        label: "Sharpe",
        value: formatNumber(summary.sharpe_ratio),
        detail: "Risk-adjusted return",
        tone: toneForNumber(summary.sharpe_ratio),
      },
      {
        label: "Vs buy & hold",
        value: formatSignedPercent(summary.excess_return_pct),
        detail: benchmarkDetail(summary.beats_buy_and_hold),
        tone: toneForNumber(excessReturn),
      },
    ],
    returnComparison: [
      { name: "Strategy", returnPct: summary.total_return_pct ?? 0 },
      { name: "Buy & hold", returnPct: summary.buy_hold_total_return_pct ?? 0 },
    ],
    equityCurve: buildEquityCurve(payload.setups, startingEquity),
    outcomeDistribution: [
      { name: "Wins", count: summary.trade_win_count },
      { name: "Losses", count: summary.trade_loss_count },
      { name: "Flat", count: summary.trade_flat_count },
      { name: "Not evaluable", count: summary.trade_not_evaluable_count },
    ],
    setupRows: [...payload.setups].sort((a, b) => a.exit_date.localeCompare(b.exit_date)),
    excludedCounts: toCountRows(summary.excluded_counts),
    warnings: [...summary.warnings, ...payload.warnings],
  };
}

export function formatCurrency(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return `${value.toFixed(1)}%`;
}

export function formatRatioAsPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function formatSignedPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

export function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return value.toFixed(2);
}

function buildEquityCurve(
  setups: BacktestSetupResult[],
  startingEquity: number,
): EquityCurvePoint[] {
  let equity = startingEquity;
  return [...setups]
    .sort((a, b) => a.exit_date.localeCompare(b.exit_date))
    .flatMap((setup) => {
      const pnl = setup.trade_pnl?.net_pnl;
      if (pnl === null || pnl === undefined) {
        return [];
      }
      equity += pnl;
      return [
        {
          date: setup.exit_date,
          setupId: setup.setup_id,
          pnl,
          equity,
        },
      ];
    });
}

function sumNetPnl(setups: BacktestSetupResult[]): number {
  return setups.reduce((sum, setup) => sum + (setup.trade_pnl?.net_pnl ?? 0), 0);
}

function toneForNumber(value: number | null): MetricTone {
  if (value === null || value === 0 || Number.isNaN(value)) {
    return "neutral";
  }
  return value > 0 ? "positive" : "negative";
}

function benchmarkDetail(beatsBuyHold: boolean | null): string {
  if (beatsBuyHold === null) {
    return "Benchmark not evaluable";
  }
  return beatsBuyHold ? "Beat benchmark" : "Lagged benchmark";
}

function toCountRows(counts: Record<string, number>): CountRow[] {
  return Object.entries(counts)
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
}
```

- [ ] **Step 4: Run view-model tests and verify GREEN**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-view-model.test.ts
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/backtest/__tests__/backtest-view-model.test.ts web/src/features/backtest/lib/backtest-view-model.ts
git commit -m "feat(web): derive backtest analytics view model"
```

---

## Task 5: Frontend — latest backtest report query hook

**Files:**
- Create: `web/src/features/backtest/__tests__/use-backtest-report.test.ts`
- Create: `web/src/features/backtest/hooks/use-backtest-report.ts`

- [ ] **Step 1: Write query tests**

Create `web/src/features/backtest/__tests__/use-backtest-report.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";
import { fetchLatestBacktestReport } from "../hooks/use-backtest-report";

describe("fetchLatestBacktestReport", () => {
  it("queries the latest persisted backtest report", async () => {
    const supabase = new FakeSupabaseClient([validRow]);

    const report = await fetchLatestBacktestReport(supabase as never);

    expect(report?.learning_report_id).toBe("backtest:r9-4-fixture");
    expect(supabase.calls).toEqual([
      ["schema", "prescient_storage"],
      ["from", "learning_reports"],
      [
        "select",
        "learning_report_id,run_id,report_date,target,theme,report_type,payload,schema_version,created_at",
      ],
      ["eq", "report_type", "backtest"],
      ["order", "report_date", { ascending: false }],
      ["order", "created_at", { ascending: false }],
      ["limit", 1],
    ]);
  });

  it("returns null when no backtest report exists", async () => {
    const supabase = new FakeSupabaseClient([]);

    await expect(fetchLatestBacktestReport(supabase as never)).resolves.toBeNull();
  });

  it("throws provider errors for ErrorState", async () => {
    const supabase = new FakeSupabaseClient([], new Error("forbidden"));

    await expect(fetchLatestBacktestReport(supabase as never)).rejects.toThrow(
      "Unable to load backtest report: forbidden",
    );
  });

  it("throws parse errors for malformed payloads", async () => {
    const supabase = new FakeSupabaseClient([{ ...validRow, payload: { run_id: "bad" } }]);

    await expect(fetchLatestBacktestReport(supabase as never)).rejects.toThrow();
  });
});

class FakeSupabaseClient {
  calls: unknown[][] = [];

  constructor(
    private readonly rows: unknown[],
    private readonly error: Error | null = null,
  ) {}

  schema(value: string): this {
    this.calls.push(["schema", value]);
    return this;
  }

  from(value: string): this {
    this.calls.push(["from", value]);
    return this;
  }

  select(value: string): this {
    this.calls.push(["select", value]);
    return this;
  }

  eq(column: string, value: string): this {
    this.calls.push(["eq", column, value]);
    return this;
  }

  order(column: string, options: { ascending: boolean }): this {
    this.calls.push(["order", column, options]);
    return this;
  }

  limit(value: number): Promise<{ data: unknown[]; error: Error | null }> {
    this.calls.push(["limit", value]);
    return Promise.resolve({ data: this.rows, error: this.error });
  }
}

const validRow = {
  learning_report_id: "backtest:r9-4-fixture",
  run_id: "r9-4-fixture",
  report_date: "2026-06-04",
  target: null,
  theme: null,
  report_type: "backtest",
  created_at: "2026-06-04T12:00:00Z",
  schema_version: 1,
  payload: {
    run_id: "r9-4-fixture",
    request: null,
    setups: [],
    summary: {
      total_setups: 0,
      candidate_ready_count: 0,
      rejected_count: 0,
      not_evaluable_count: 0,
      underlying_win_count: 0,
      underlying_loss_count: 0,
      underlying_flat_count: 0,
      underlying_not_evaluable_count: 0,
      trade_win_count: 0,
      trade_loss_count: 0,
      trade_flat_count: 0,
      trade_not_evaluable_count: 0,
      average_underlying_return_pct: null,
      median_underlying_return_pct: null,
      average_net_pnl: null,
      median_net_pnl: null,
      by_theme: {},
      by_ticker: {},
      by_expression: {},
      top_rejection_reasons: {},
      win_rate: null,
      max_drawdown_pct: null,
      sharpe_ratio: null,
      total_return_pct: null,
      buy_hold_total_return_pct: null,
      beats_buy_and_hold: null,
      excess_return_pct: null,
      benchmark_status: "not_evaluable",
      metrics_status: "not_evaluable",
      excluded_counts: {},
      warnings: [],
    },
    warnings: [],
  },
};
```

- [ ] **Step 2: Run query tests and verify RED**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/use-backtest-report.test.ts
```

Expected: fails because the hook module does not exist.

- [ ] **Step 3: Implement query hook**

Create `web/src/features/backtest/hooks/use-backtest-report.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import {
  type BacktestReportRow,
  parseBacktestReportRow,
} from "../lib/backtest-report.schema";

const BACKTEST_REPORT_COLUMNS =
  "learning_report_id,run_id,report_date,target,theme,report_type,payload,schema_version,created_at";

type SupabaseLike = {
  schema(schema: string): {
    from(table: string): {
      select(columns: string): {
        eq(column: string, value: string): {
          order(
            column: string,
            options: { ascending: boolean },
          ): {
            order(
              column: string,
              options: { ascending: boolean },
            ): {
              limit(
                value: number,
              ): Promise<{ data: unknown[] | null; error: { message?: string } | null }>;
            };
          };
        };
      };
    };
  };
};

export async function fetchLatestBacktestReport(
  supabase: SupabaseLike = createClient() as unknown as SupabaseLike,
): Promise<BacktestReportRow | null> {
  const { data, error } = await supabase
    .schema("prescient_storage")
    .from("learning_reports")
    .select(BACKTEST_REPORT_COLUMNS)
    .eq("report_type", "backtest")
    .order("report_date", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(1);

  if (error) {
    throw new Error(`Unable to load backtest report: ${error.message ?? "unknown error"}`);
  }

  const row = data?.[0];
  if (!row) {
    return null;
  }

  return parseBacktestReportRow(row);
}

export function useLatestBacktestReport() {
  return useQuery({
    queryKey: ["backtest-report", "latest"],
    queryFn: () => fetchLatestBacktestReport(),
    refetchOnWindowFocus: true,
  });
}
```

- [ ] **Step 4: Run query tests and verify GREEN**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/use-backtest-report.test.ts
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/backtest/__tests__/use-backtest-report.test.ts web/src/features/backtest/hooks/use-backtest-report.ts
git commit -m "feat(web): load latest backtest report"
```

---

## Task 6: Frontend — metric cards and chart components

**Files:**
- Create: `web/src/features/backtest/components/metric-card.tsx`
- Create: `web/src/features/backtest/components/return-comparison-chart.tsx`
- Create: `web/src/features/backtest/components/equity-curve-chart.tsx`
- Create: `web/src/features/backtest/components/outcome-distribution-chart.tsx`

- [ ] **Step 1: Create the metric card**

Create `web/src/features/backtest/components/metric-card.tsx`:

```tsx
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { MetricCardModel } from "../lib/backtest-view-model";

export function MetricCard({ metric }: { metric: MetricCardModel }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-muted-foreground">{metric.label}</div>
      <div
        className={cn(
          "mt-2 text-2xl font-semibold",
          metric.tone === "positive" && "text-success",
          metric.tone === "negative" && "text-danger",
        )}
      >
        {metric.value}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{metric.detail}</div>
    </Card>
  );
}
```

- [ ] **Step 2: Create the return comparison chart**

Create `web/src/features/backtest/components/return-comparison-chart.tsx`:

```tsx
"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { ReturnComparisonPoint } from "../lib/backtest-view-model";

export function ReturnComparisonChart({
  data,
}: {
  data: ReturnComparisonPoint[];
}) {
  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium">Return comparison</h2>
      <div className="mt-4 h-64" data-testid="return-comparison-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis tickFormatter={(value) => `${value}%`} />
            <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
            <Bar dataKey="returnPct" fill="hsl(var(--success))" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

- [ ] **Step 3: Create the equity curve chart**

Create `web/src/features/backtest/components/equity-curve-chart.tsx`:

```tsx
"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { EquityCurvePoint } from "../lib/backtest-view-model";

export function EquityCurveChart({ data }: { data: EquityCurvePoint[] }) {
  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium">Equity curve</h2>
      <div className="mt-4 h-72" data-testid="equity-curve-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis tickFormatter={(value) => `$${Number(value).toLocaleString()}`} />
            <Tooltip
              formatter={(value, name) =>
                name === "equity"
                  ? `$${Number(value).toLocaleString()}`
                  : Number(value).toLocaleString()
              }
            />
            <Line
              type="monotone"
              dataKey="equity"
              stroke="hsl(var(--foreground))"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Create the outcome distribution chart**

Create `web/src/features/backtest/components/outcome-distribution-chart.tsx`:

```tsx
"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { OutcomeDistributionPoint } from "../lib/backtest-view-model";

export function OutcomeDistributionChart({
  data,
}: {
  data: OutcomeDistributionPoint[];
}) {
  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium">Outcome mix</h2>
      <div className="mt-4 h-64" data-testid="outcome-distribution-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" fill="hsl(var(--muted-foreground))" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
```

- [ ] **Step 5: Run typecheck through build**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/backtest/components/metric-card.tsx web/src/features/backtest/components/return-comparison-chart.tsx web/src/features/backtest/components/equity-curve-chart.tsx web/src/features/backtest/components/outcome-distribution-chart.tsx
git commit -m "feat(web): add backtest metric and chart components"
```

---

## Task 7: Frontend — setup table and diagnostics

**Files:**
- Create: `web/src/features/backtest/components/setup-results-table.tsx`
- Create: `web/src/features/backtest/components/report-diagnostics.tsx`

- [ ] **Step 1: Create setup results table**

Create `web/src/features/backtest/components/setup-results-table.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import {
  Table,
  Td,
  Th,
} from "@/components/ui/table";
import type { BacktestSetupResult } from "../lib/backtest-report.schema";
import { formatCurrency, formatPercent } from "../lib/backtest-view-model";

export function SetupResultsTable({ setups }: { setups: BacktestSetupResult[] }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium">Setup results</h2>
      <Table>
        <thead>
          <tr>
            <Th>Exit</Th>
            <Th>Target</Th>
            <Th>Theme</Th>
            <Th>Expression</Th>
            <Th>Outcome</Th>
            <Th className="text-right">Net P&L</Th>
            <Th className="text-right">Return on risk</Th>
          </tr>
        </thead>
        <tbody>
          {setups.map((setup) => (
            <tr key={setup.setup_id}>
              <Td>{setup.exit_date}</Td>
              <Td className="font-medium">{setup.target}</Td>
              <Td>{setup.theme ?? "n/a"}</Td>
              <Td>{setup.expression}</Td>
              <Td>
                <OutcomeBadge outcome={setup.trade_pnl?.outcome ?? "not_evaluable"} />
              </Td>
              <Td className="text-right">
                {formatCurrency(setup.trade_pnl?.net_pnl ?? null)}
              </Td>
              <Td className="text-right">
                {formatPercent(setup.trade_pnl?.return_on_risk_pct ?? null)}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </section>
  );
}

function OutcomeBadge({
  outcome,
}: {
  outcome: "win" | "loss" | "flat" | "not_evaluable";
}) {
  const variant =
    outcome === "win"
      ? "success"
      : outcome === "loss"
        ? "danger"
        : outcome === "flat"
          ? "muted"
          : "warning";
  return <Badge variant={variant}>{outcome}</Badge>;
}
```

- [ ] **Step 2: Create diagnostics component**

Create `web/src/features/backtest/components/report-diagnostics.tsx`:

```tsx
import { Card } from "@/components/ui/card";
import type { CountRow } from "../lib/backtest-view-model";

export function ReportDiagnostics({
  warnings,
  excludedCounts,
}: {
  warnings: string[];
  excludedCounts: CountRow[];
}) {
  if (!warnings.length && !excludedCounts.length) {
    return null;
  }

  return (
    <Card className="p-4">
      <h2 className="text-sm font-medium">Report diagnostics</h2>
      {warnings.length ? (
        <div className="mt-3">
          <h3 className="text-xs font-medium text-muted-foreground">Warnings</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {excludedCounts.length ? (
        <div className="mt-4">
          <h3 className="text-xs font-medium text-muted-foreground">Excluded observations</h3>
          <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            {excludedCounts.map((row) => (
              <div key={row.reason} className="contents">
                <dt>{row.reason}</dt>
                <dd className="font-medium tabular-nums">{row.count}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 3: Run build**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/backtest/components/setup-results-table.tsx web/src/features/backtest/components/report-diagnostics.tsx
git commit -m "feat(web): add backtest setup table and diagnostics"
```

---

## Task 8: Frontend — `/backtest` page and state handling

**Files:**
- Create: `web/src/features/backtest/__tests__/backtest-page.test.tsx`
- Create: `web/src/features/backtest/components/backtest-page.tsx`
- Create/Modify: `web/src/app/(app)/backtest/page.tsx`

- [ ] **Step 1: Write page tests**

Create `web/src/features/backtest/__tests__/backtest-page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BacktestPage } from "../components/backtest-page";

vi.mock("../hooks/use-backtest-report", () => ({
  useLatestBacktestReport: vi.fn(),
}));

vi.mock("../components/return-comparison-chart", () => ({
  ReturnComparisonChart: () => <div data-testid="return-comparison-chart" />,
}));

vi.mock("../components/equity-curve-chart", () => ({
  EquityCurveChart: () => <div data-testid="equity-curve-chart" />,
}));

vi.mock("../components/outcome-distribution-chart", () => ({
  OutcomeDistributionChart: () => <div data-testid="outcome-distribution-chart" />,
}));

import { useLatestBacktestReport } from "../hooks/use-backtest-report";

const mockedUseLatestBacktestReport = vi.mocked(useLatestBacktestReport);

describe("BacktestPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders loading state", () => {
    mockedUseLatestBacktestReport.mockReturnValue({
      isLoading: true,
      isError: false,
      error: null,
      data: undefined,
    } as never);

    render(<BacktestPage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders empty state when no report exists", () => {
    mockedUseLatestBacktestReport.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      data: null,
    } as never);

    render(<BacktestPage />);

    expect(screen.getByText("No backtest report available yet.")).toBeInTheDocument();
  });

  it("renders loud error state", () => {
    mockedUseLatestBacktestReport.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("payload did not match expected shape"),
      data: undefined,
    } as never);

    render(<BacktestPage />);

    expect(screen.getByText("Backtest report could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("payload did not match expected shape")).toBeInTheDocument();
  });

  it("renders populated analytics", () => {
    mockedUseLatestBacktestReport.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      data: reportFixture,
    } as never);

    render(<BacktestPage />);

    expect(screen.getByRole("heading", { name: "Backtest analytics" })).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getByTestId("return-comparison-chart")).toBeInTheDocument();
    expect(screen.getByTestId("equity-curve-chart")).toBeInTheDocument();
    expect(screen.getByTestId("outcome-distribution-chart")).toBeInTheDocument();
    expect(screen.getByText("Setup results")).toBeInTheDocument();
  });
});

const reportFixture = {
  learning_report_id: "backtest:r9-4-fixture",
  run_id: "r9-4-fixture",
  report_date: "2026-06-04",
  target: null,
  theme: null,
  report_type: "backtest",
  created_at: "2026-06-04T12:00:00Z",
  schema_version: 1,
  payload: {
    run_id: "r9-4-fixture",
    request: null,
    setups: [],
    summary: {
      total_setups: 1,
      candidate_ready_count: 1,
      rejected_count: 0,
      not_evaluable_count: 0,
      underlying_win_count: 0,
      underlying_loss_count: 0,
      underlying_flat_count: 0,
      underlying_not_evaluable_count: 0,
      trade_win_count: 1,
      trade_loss_count: 1,
      trade_flat_count: 0,
      trade_not_evaluable_count: 0,
      average_underlying_return_pct: null,
      median_underlying_return_pct: null,
      average_net_pnl: 75,
      median_net_pnl: 75,
      by_theme: {},
      by_ticker: {},
      by_expression: {},
      top_rejection_reasons: {},
      win_rate: 0.5,
      max_drawdown_pct: 0.5,
      sharpe_ratio: 1.2,
      total_return_pct: 1.5,
      buy_hold_total_return_pct: 0.5,
      beats_buy_and_hold: true,
      excess_return_pct: 1,
      benchmark_status: "evaluable",
      metrics_status: "evaluable",
      excluded_counts: {},
      warnings: [],
    },
    warnings: [],
  },
};
```

- [ ] **Step 2: Run page tests and verify RED**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-page.test.tsx
```

Expected: fails because `backtest-page.tsx` does not exist.

- [ ] **Step 3: Implement page composer**

Create `web/src/features/backtest/components/backtest-page.tsx`:

```tsx
"use client";

import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { useLatestBacktestReport } from "../hooks/use-backtest-report";
import { buildBacktestViewModel } from "../lib/backtest-view-model";
import { EquityCurveChart } from "./equity-curve-chart";
import { MetricCard } from "./metric-card";
import { OutcomeDistributionChart } from "./outcome-distribution-chart";
import { ReportDiagnostics } from "./report-diagnostics";
import { ReturnComparisonChart } from "./return-comparison-chart";
import { SetupResultsTable } from "./setup-results-table";

export function BacktestPage() {
  const reportQuery = useLatestBacktestReport();

  if (reportQuery.isLoading) {
    return <LoadingState label="Loading backtest analytics." />;
  }

  if (reportQuery.isError) {
    const message =
      reportQuery.error instanceof Error
        ? reportQuery.error.message
        : "Unknown backtest report error.";
    return (
      <ErrorState
        title="Backtest report could not be loaded"
        detail={message}
      />
    );
  }

  if (!reportQuery.data) {
    return <EmptyState message="No backtest report available yet." />;
  }

  const viewModel = buildBacktestViewModel(reportQuery.data);

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{viewModel.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{viewModel.subtitle}</p>
      </header>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {viewModel.metricCards.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <EquityCurveChart data={viewModel.equityCurve} />
        <ReturnComparisonChart data={viewModel.returnComparison} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <OutcomeDistributionChart data={viewModel.outcomeDistribution} />
        <ReportDiagnostics
          warnings={viewModel.warnings}
          excludedCounts={viewModel.excludedCounts}
        />
      </div>

      <SetupResultsTable setups={viewModel.setupRows} />
    </section>
  );
}
```

- [ ] **Step 4: Add the route**

Create or replace `web/src/app/(app)/backtest/page.tsx`:

```tsx
import { BacktestPage } from "@/features/backtest/components/backtest-page";

export default function Page() {
  return <BacktestPage />;
}
```

- [ ] **Step 5: Run page tests and verify GREEN**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest/__tests__/backtest-page.test.tsx
```

Expected: tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add "web/src/app/(app)/backtest/page.tsx" web/src/features/backtest/components/backtest-page.tsx web/src/features/backtest/__tests__/backtest-page.test.tsx
git commit -m "feat(web): add backtest analytics page"
```

---

## Task 9: Frontend — full verification

**Files:** none unless failures require fixes.

- [ ] **Step 1: Run focused frontend tests**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run src/features/backtest
```

Expected: all Slice 4 frontend tests pass.

- [ ] **Step 2: Run full frontend tests and build**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- --run
npm run build
```

Expected: all frontend tests pass; production build succeeds.

- [ ] **Step 3: Run backend regression tests touched by this slice**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run pytest tests/test_r9_4_backtest_report_storage.py tests/test_r9_3_performance_metrics.py tests/test_r6_4_supabase_storage.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 4: Run lint gates**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
uv run ruff check .
cd web
npm run lint
```

Expected: Python and frontend lint pass.

- [ ] **Step 5: Manual browser verification**

Start local dependencies:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
supabase start
cd web
npm run dev
```

Open `http://localhost:3000/backtest` while authenticated.

Expected without a persisted `backtest` learning report:

- `/backtest` loads inside the authenticated layout.
- It shows `No backtest report available yet.`
- There is no button or control that runs a backtest or writes data.

Expected with a persisted `backtest` learning report:

- KPI cards render win rate, total return, max drawdown, Sharpe, and benchmark comparison.
- Equity curve, return comparison, and outcome mix charts are visible and nonblank.
- Setup results table renders setup-level outcomes and P&L.
- Warnings and exclusions render when present.
- Parse/provider failures render `Backtest report could not be loaded`.

- [ ] **Step 6: Commit any final cleanup**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add -A
git commit -m "chore(web): verify backtest analytics slice"
```

---

## Definition of Done (Slice 4)

- Backend has a tested helper that converts `BacktestRunResult` to a `learning_reports` row with `report_type = "backtest"`.
- Supabase storage adapter can upsert learning report rows through `append_learning_reports()`.
- `/backtest` is authenticated through the existing `(app)` layout.
- The page queries only `prescient_storage.learning_reports`; it does not run backtests or perform writes from the browser.
- Zod parser rejects malformed backtest payloads loudly and routes those failures to `<ErrorState>`.
- Loading, error, and empty states are all tested.
- Ready state renders KPI cards, first charts, setup table, warnings, and exclusions.
- `npm test -- --run`, `npm run build`, focused backend pytest checks, `uv run ruff check .`, and `npm run lint` pass.

No mode authorization, kill switch, trade approval, trade sizing, parameter tuning, or live execution behavior is built in this slice.
