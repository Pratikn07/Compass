# Prescient Web Frontend - Slice 2 (Decision Chain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the authenticated `/decisions/[id]` detail route so the operator can click a decision and understand the full journal chain: strategy decision, analyst review, risk decision, position sizing, execution proposal, and outcome.

**Architecture:** This slice stays read-only. It queries `prescient_storage.journal_records` by `decision_id`, orders the records chronologically, parses each rendered `payload` envelope with Zod, and renders a six-step chain with source citations and loud parse-error cards. It does not add actions, trade approval, trade sizing edits, client-side Claude calls, or database writes.

**Tech Stack:** Existing Slice 0/1 web stack: Next.js App Router + TypeScript, Tailwind CSS, existing UI primitives (`Card`, `Badge`, `Button` only if needed for navigation links), TanStack Query v5, Supabase JS client, Zod, Vitest + React Testing Library.

**Reference spec:** `docs/superpowers/specs/2026-06-03-prescient-web-frontend-design.md`

> **WARNING: Prerequisites.** This plan assumes Slice 0 and Slice 1 are already complete. `web/` does not exist in the current workspace at plan-writing time, and there is no Slice 1 plan yet. Do not execute this plan until:
> - Slice 0 has created the app shell, auth guard, Supabase client, generated database types, UI primitives, and state components.
> - Slice 1 has created `/decisions`, `useLatestRun()`, `useDecisions(runId)`, and a rendered decision table.
>
> **WARNING: Git not yet set up.** `prescient/` was not a git repository when Slice 0 was planned. Until `git init` is run here, skip every `git add` / `git commit` step and treat each task end as a logical checkpoint. Once git is initialized, commit steps become valid as written.

---

## File Structure

New and modified frontend files for Slice 2:

```
web/
  src/
    app/
      (app)/
        decisions/
          [id]/
            page.tsx                       # dynamic decision detail route
    features/
      decisions/
        decision-chain-client.tsx          # client component: hook + states + view
        decision-chain-view.tsx            # pure presentational chain view
        decision-chain-card.tsx            # per-record card rendering
        source-citations.tsx               # citation list/details rendering
        decision-chain.types.ts            # row, parse, payload, step types
        decision-chain-schemas.ts          # Zod payload schemas
        parse-decision-chain.ts            # row -> parsed chain records
        fetch-decision-chain.ts            # Supabase query function
        use-decision-chain.ts              # TanStack Query hook
        decision-chain-format.ts           # badge/label/format helpers
        decision-list.tsx                  # MODIFY from Slice 1: row links to detail route
  __tests__/
    decision-chain-schemas.test.ts
    parse-decision-chain.test.ts
    fetch-decision-chain.test.ts
    decision-chain-view.test.tsx
    decision-list-links.test.tsx           # update/create depending on Slice 1 tests
```

Backend facts this plan is grounded in:

- The database table is `prescient_storage.journal_records`.
- Important columns: `journal_record_id`, `record_type`, `run_id`, `decision_id`, `decision_index`, `trading_date`, `created_at`, `target`, `theme`, `strategy_type`, `strategy_status`, `execution_mode`, `source`, `order_id`, `payload`.
- There is no database `source_citations` column. Citations must be read from parsed payload audit trails (`strategy_decision.audit_trail`, `claude_result.audit_trail`, `risk_gate_decision.audit_trail`, `position_sizing_decision.audit_trail`, candidate/source sub-objects).
- `runtime/decision_journal.py` writes fixed payload envelopes for `strategy_decision`, `analyst_review`, `risk_decision`, `position_sizing`, and `trade_outcome`. `execution_proposal` is intentionally generic and must render as read-only raw/details data rather than guessed semantics.

---

## Task 0: Preflight - confirm Slice 0 and Slice 1 exist

**Files:** none

- [ ] **Step 1: Verify the frontend exists**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
test -d web && test -f web/src/lib/supabase/database.types.ts && test -f web/src/lib/supabase/client.ts
```

Expected: exits 0. If it fails, stop and execute Slice 0 first.

- [ ] **Step 2: Verify Slice 1 data hooks exist**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
test -f web/src/features/decisions/use-decisions.ts
test -f web/src/features/decisions/use-latest-run.ts
test -f web/src/features/decisions/decision-list.tsx
```

Expected: exits 0. If Slice 1 used different filenames, stop and update this plan or normalize Slice 1 to these file names before continuing. Do not create a second competing decision-list implementation.

- [ ] **Step 3: Verify the current frontend gate is green**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test && npm run build
```

Expected: all existing tests pass and production build succeeds.

---

## Task 1: Add payload schemas for decision-chain records

**Files:**
- Create: `web/src/features/decisions/decision-chain.types.ts`
- Create: `web/src/features/decisions/decision-chain-schemas.ts`
- Test: `web/__tests__/decision-chain-schemas.test.ts`

- [ ] **Step 1: Write the failing schema tests**

Create `web/__tests__/decision-chain-schemas.test.ts`:

```tsx
import { describe, expect, it } from "vitest";
import {
  AnalystReviewPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "@/features/decisions/decision-chain-schemas";

describe("decision chain payload schemas", () => {
  it("parses the strategy_decision payload envelope written by runtime/decision_journal.py", () => {
    const parsed = StrategyDecisionPayloadSchema.parse({
      thesis: "Bullish AI_STORAGE read-through for NTNX.",
      decision_summary: "candidate_ready_for_analyst",
      strategy_decision: {
        status: "candidate_ready_for_analyst",
        candidate: {
          target: "NTNX",
          theme: "AI_STORAGE",
          earnings_date: "2026-06-03",
          report_time: "AMC",
          direction: "bullish",
          peer_signal_score: 2.7,
          positive_peer_ratio: 0.75,
          reported_peers: ["NTAP", "PSTG", "WDC"],
          peer_scores: [],
          main_thesis: "AI storage peers reported strong demand.",
          supporting_evidence: ["NTAP guide improved"],
          contradictions: [],
          recommended_expression: "CALL_OPTION",
          technical_indicators: null,
          strategy_status: "candidate_ready_for_analyst",
          peer_summaries: [],
          source_citations: [
            {
              citation_id: "cit-peer",
              provider: "fixture",
              source_type: "earnings_result",
              confidence: "high",
            },
          ],
        },
        rejection_reasons: [],
        rejection_details: [],
        audit: {},
        claude_analysis_allowed: true,
        audit_trail: {
          source_citations: [
            {
              citation_id: "cit-audit",
              provider: "prescient",
              source_type: "strategy_rule",
            },
          ],
          citation_unavailable_reasons: [],
          rule_facts: [],
        },
      },
      candidate_brief: {
        target: "NTNX",
        theme: "AI_STORAGE",
        earnings_date: "2026-06-03",
        report_time: "AMC",
        direction: "bullish",
        peer_signal_score: 2.7,
        positive_peer_ratio: 0.75,
        reported_peers: ["NTAP", "PSTG", "WDC"],
        peer_scores: [],
        main_thesis: "AI storage peers reported strong demand.",
        supporting_evidence: ["NTAP guide improved"],
        contradictions: [],
        recommended_expression: "CALL_OPTION",
        technical_indicators: null,
        strategy_status: "candidate_ready_for_analyst",
        peer_summaries: [],
        source_citations: [],
      },
      rejection_reasons: [],
      rejection_details: [],
      warnings: [],
      data_snapshot: {},
      settings_snapshot: {},
      missing_data: [],
      source_events: [],
    });

    expect(parsed.candidate_brief?.target).toBe("NTNX");
    expect(parsed.strategy_decision.audit_trail.source_citations[0].citation_id).toBe(
      "cit-audit",
    );
  });

  it("requires risk_decision status and rejection reasons", () => {
    expect(() => RiskDecisionPayloadSchema.parse({ risk_gate_decision: {} })).toThrow();

    const parsed = RiskDecisionPayloadSchema.parse({
      risk_gate_decision: {
        target: "NTNX",
        theme: "AI_STORAGE",
        strategy_status: "candidate_ready_for_analyst",
        status: "blocked",
        rejection_reasons: ["missing_order_proposal"],
        explanation: "Risk gate requires an order proposal.",
        broker_execution_allowed: false,
        claude_present: true,
        claude_override_attempted: false,
        audit_trail: {
          source_citations: [],
          citation_unavailable_reasons: [],
          rule_facts: [
            {
              rule_name: "missing_order_proposal",
              passed: false,
              reason: "No structured order proposal.",
              citation_ids: [],
            },
          ],
        },
      },
      status: "blocked",
      rejection_reasons: ["missing_order_proposal"],
      broker_execution_allowed: false,
    });

    expect(parsed.status).toBe("blocked");
  });

  it("parses analyst, sizing, and outcome envelopes", () => {
    const analyst = AnalystReviewPayloadSchema.parse({
      claude_result: {
        status: "analyzed",
        analysis: {
          recommendation: "go",
          thesis: "Peer demand is supportive.",
          reasoning: "Multiple peers cited AI demand.",
          conviction_score: 71,
          missing_context: [],
          contradictions: [],
          suggested_expression: "CALL_OPTION",
          cited_citation_ids: ["cit-peer"],
        },
        error_message: null,
        audit_trail: {
          source_citations: [],
          citation_unavailable_reasons: [],
          rule_facts: [],
        },
      },
      status: "analyzed",
      analysis: null,
      error_message: null,
    });

    const sizing = PositionSizingPayloadSchema.parse({
      position_sizing_decision: {
        status: "sized",
        target: "NTNX",
        theme: "AI_STORAGE",
        strategy_status: "candidate_ready_for_analyst",
        expression: "CALL_OPTION",
        account_equity: 15000,
        risk_budget: 150,
        unit_max_loss: 50,
        approved_quantity: 3,
        projected_max_loss: 150,
        entry_cost_required: 300,
        rejection_reasons: [],
        warnings: [],
        explanation: "Sized within the configured risk budget.",
        claude_present: true,
        claude_sizing_override_attempted: false,
        audit_trail: {
          source_citations: [],
          citation_unavailable_reasons: [],
          rule_facts: [],
        },
      },
      status: "sized",
      approved_quantity: 3,
      projected_max_loss: 150,
      entry_cost_required: 300,
      rejection_reasons: [],
    });

    const outcome = TradeOutcomePayloadSchema.parse({
      outcome: {
        outcome_type: "pending",
        net_realized_pnl: null,
        gross_realized_pnl: null,
        fees: null,
        pnl_currency: "USD",
        open_quantity: null,
        closed_quantity: null,
        outcome_reasons: [],
        ambiguous: false,
      },
    });

    expect(analyst.status).toBe("analyzed");
    expect(sizing.approved_quantity).toBe(3);
    expect(outcome.outcome.outcome_type).toBe("pending");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-chain-schemas.test.ts
```

Expected: FAIL because `decision-chain-schemas.ts` does not exist.

- [ ] **Step 3: Create the shared decision-chain types**

Create `web/src/features/decisions/decision-chain.types.ts`:

```typescript
import type { z } from "zod";
import type { Database } from "@/lib/supabase/database.types";
import type {
  AnalystReviewPayloadSchema,
  ExecutionProposalPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "./decision-chain-schemas";

export type JournalRecordRow =
  Database["prescient_storage"]["Tables"]["journal_records"]["Row"];

export type DecisionChainRecordType =
  | "strategy_decision"
  | "analyst_review"
  | "risk_decision"
  | "position_sizing"
  | "execution_proposal"
  | "trade_outcome"
  | "outcome_correction";

export type SourceCitation = {
  citation_id: string;
  provider: string;
  source_type: string;
  title?: string | null;
  url?: string | null;
  source_endpoint?: string | null;
  source_id?: string | null;
  as_of?: string | null;
  retrieved_at?: string | null;
  excerpt?: string | null;
  confidence?: string;
};

export type StrategyDecisionPayload = z.infer<typeof StrategyDecisionPayloadSchema>;
export type AnalystReviewPayload = z.infer<typeof AnalystReviewPayloadSchema>;
export type RiskDecisionPayload = z.infer<typeof RiskDecisionPayloadSchema>;
export type PositionSizingPayload = z.infer<typeof PositionSizingPayloadSchema>;
export type ExecutionProposalPayload = z.infer<typeof ExecutionProposalPayloadSchema>;
export type TradeOutcomePayload = z.infer<typeof TradeOutcomePayloadSchema>;

export type ParsedPayload =
  | StrategyDecisionPayload
  | AnalystReviewPayload
  | RiskDecisionPayload
  | PositionSizingPayload
  | ExecutionProposalPayload
  | TradeOutcomePayload;

export type PayloadParseResult =
  | { ok: true; data: ParsedPayload; citations: SourceCitation[] }
  | { ok: false; error: string; raw: unknown };

export type DecisionChainRecord = {
  row: JournalRecordRow;
  recordType: DecisionChainRecordType;
  label: string;
  order: number;
  payload: PayloadParseResult;
};
```

- [ ] **Step 4: Create the Zod payload schemas**

Create `web/src/features/decisions/decision-chain-schemas.ts`:

```typescript
import { z } from "zod";

const JsonObjectSchema = z.record(z.string(), z.unknown());

export const SourceCitationSchema = z
  .object({
    citation_id: z.string().min(1),
    provider: z.string().min(1),
    source_type: z.string().min(1),
    title: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    source_endpoint: z.string().nullable().optional(),
    source_id: z.string().nullable().optional(),
    as_of: z.string().nullable().optional(),
    retrieved_at: z.string().nullable().optional(),
    excerpt: z.string().nullable().optional(),
    confidence: z.string().optional(),
  })
  .passthrough();

const RuleFactSchema = z
  .object({
    rule_name: z.string(),
    passed: z.boolean().nullable().optional(),
    threshold: z.union([z.string(), z.number(), z.boolean()]).nullable().optional(),
    observed_value: z
      .union([z.string(), z.number(), z.boolean()])
      .nullable()
      .optional(),
    reason: z.string().nullable().optional(),
    citation_ids: z.array(z.string()).default([]),
  })
  .passthrough();

export const AuditTrailSchema = z
  .object({
    source_citations: z.array(SourceCitationSchema),
    citation_unavailable_reasons: z.array(z.string()),
    rule_facts: z.array(RuleFactSchema),
  })
  .passthrough();

const RejectionDetailSchema = z
  .object({
    reason: z.string(),
    stage: z.string(),
    message: z.string(),
  })
  .passthrough();

const PeerScoreSchema = z
  .object({
    ticker: z.string(),
    score: z.number(),
    positive_factors: z.array(z.string()).default([]),
    negative_factors: z.array(z.string()).default([]),
    missing_factors: z.array(z.string()).default([]),
  })
  .passthrough();

const CandidateBriefSchema = z
  .object({
    target: z.string(),
    theme: z.string(),
    earnings_date: z.string(),
    report_time: z.string(),
    direction: z.literal("bullish"),
    peer_signal_score: z.number(),
    positive_peer_ratio: z.number(),
    reported_peers: z.array(z.string()),
    peer_scores: z.array(PeerScoreSchema),
    main_thesis: z.string(),
    supporting_evidence: z.array(z.string()),
    contradictions: z.array(z.string()),
    recommended_expression: z.string(),
    technical_indicators: z.unknown().nullable(),
    strategy_status: z.string(),
    peer_summaries: z.array(z.unknown()),
    source_citations: z.array(SourceCitationSchema),
  })
  .passthrough();

export const StrategyDecisionPayloadSchema = z
  .object({
    thesis: z.string(),
    decision_summary: z.string(),
    strategy_decision: z
      .object({
        status: z.string(),
        candidate: CandidateBriefSchema.nullable(),
        rejection_reasons: z.array(z.string()),
        rejection_details: z.array(RejectionDetailSchema),
        audit: JsonObjectSchema,
        claude_analysis_allowed: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    candidate_brief: CandidateBriefSchema.nullable(),
    rejection_reasons: z.array(z.string()),
    rejection_details: z.array(RejectionDetailSchema),
    warnings: z.array(z.unknown()),
    data_snapshot: JsonObjectSchema,
    settings_snapshot: JsonObjectSchema,
    missing_data: z.array(z.string()),
    source_events: z.array(z.unknown()),
  })
  .passthrough();

const ClaudeStrategyAnalysisSchema = z
  .object({
    recommendation: z.string(),
    thesis: z.string(),
    reasoning: z.string(),
    conviction_score: z.number(),
    missing_context: z.array(z.string()),
    contradictions: z.array(z.string()),
    suggested_expression: z.string(),
    cited_citation_ids: z.array(z.string()),
  })
  .passthrough();

export const AnalystReviewPayloadSchema = z
  .object({
    claude_result: z
      .object({
        status: z.string(),
        analysis: ClaudeStrategyAnalysisSchema.nullable(),
        error_message: z.string().nullable(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    analysis: ClaudeStrategyAnalysisSchema.nullable(),
    error_message: z.string().nullable(),
  })
  .passthrough();

export const RiskDecisionPayloadSchema = z
  .object({
    risk_gate_decision: z
      .object({
        target: z.string(),
        theme: z.string().nullable(),
        strategy_status: z.string(),
        status: z.string(),
        rejection_reasons: z.array(z.string()),
        explanation: z.string(),
        broker_execution_allowed: z.boolean(),
        claude_present: z.boolean(),
        claude_override_attempted: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    rejection_reasons: z.array(z.string()),
    broker_execution_allowed: z.boolean(),
  })
  .passthrough();

export const PositionSizingPayloadSchema = z
  .object({
    position_sizing_decision: z
      .object({
        status: z.string(),
        target: z.string(),
        theme: z.string().nullable(),
        strategy_status: z.string(),
        expression: z.string().nullable(),
        account_equity: z.number().nullable(),
        risk_budget: z.number().nullable(),
        unit_max_loss: z.number().nullable(),
        approved_quantity: z.number(),
        projected_max_loss: z.number().nullable(),
        entry_cost_required: z.number().nullable(),
        rejection_reasons: z.array(z.string()),
        warnings: z.array(z.string()),
        explanation: z.string(),
        claude_present: z.boolean(),
        claude_sizing_override_attempted: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    approved_quantity: z.number(),
    projected_max_loss: z.number().nullable(),
    entry_cost_required: z.number().nullable(),
    rejection_reasons: z.array(z.string()),
  })
  .passthrough();

export const ExecutionProposalPayloadSchema = JsonObjectSchema;

export const DecisionOutcomeSchema = z
  .object({
    outcome_type: z.string(),
    net_realized_pnl: z.number().nullable(),
    gross_realized_pnl: z.number().nullable(),
    fees: z.number().nullable(),
    pnl_currency: z.string(),
    open_quantity: z.number().nullable(),
    closed_quantity: z.number().nullable(),
    outcome_reasons: z.array(z.string()),
    ambiguous: z.boolean(),
  })
  .passthrough();

export const TradeOutcomePayloadSchema = z
  .object({
    outcome: DecisionOutcomeSchema,
  })
  .passthrough();
```

- [ ] **Step 5: Run the schema tests to verify they pass**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-chain-schemas.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-chain.types.ts \
  web/src/features/decisions/decision-chain-schemas.ts \
  web/__tests__/decision-chain-schemas.test.ts
git commit -m "feat(web): add decision chain payload schemas"
```

---

## Task 2: Parse journal rows into ordered chain records

**Files:**
- Create: `web/src/features/decisions/decision-chain-format.ts`
- Create: `web/src/features/decisions/parse-decision-chain.ts`
- Test: `web/__tests__/parse-decision-chain.test.ts`

- [ ] **Step 1: Write the failing parser tests**

Create `web/__tests__/parse-decision-chain.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { parseDecisionChain } from "@/features/decisions/parse-decision-chain";
import type { JournalRecordRow } from "@/features/decisions/decision-chain.types";

function row(overrides: Partial<JournalRecordRow>): JournalRecordRow {
  return {
    journal_record_id: "journal-1",
    record_type: "strategy_decision",
    run_id: "scheduled:2026-06-03",
    decision_id: "decision-1",
    decision_index: 0,
    trading_date: "2026-06-03",
    created_at: "2026-06-03T15:00:00Z",
    target: "NTNX",
    theme: "AI_STORAGE",
    strategy_type: "bullish_earnings_readthrough",
    strategy_status: "candidate_ready_for_analyst",
    execution_mode: "propose_only",
    source: "prescient.runtime",
    provider: null,
    order_id: null,
    parent_record_id: null,
    duplicate_of_record_id: null,
    payload: {},
    schema_version: 1,
    ...overrides,
  };
}

describe("parseDecisionChain", () => {
  it("orders known chain records by product order, then created_at", () => {
    const parsed = parseDecisionChain([
      row({
        journal_record_id: "risk",
        record_type: "risk_decision",
        created_at: "2026-06-03T15:02:00Z",
        payload: {
          risk_gate_decision: {
            target: "NTNX",
            theme: "AI_STORAGE",
            strategy_status: "candidate_ready_for_analyst",
            status: "approved",
            rejection_reasons: [],
            explanation: "Risk checks passed.",
            broker_execution_allowed: false,
            claude_present: true,
            claude_override_attempted: false,
            audit_trail: {
              source_citations: [],
              citation_unavailable_reasons: [],
              rule_facts: [],
            },
          },
          status: "approved",
          rejection_reasons: [],
          broker_execution_allowed: false,
        },
      }),
      row({
        journal_record_id: "strategy",
        record_type: "strategy_decision",
        created_at: "2026-06-03T15:00:00Z",
        payload: {
          thesis: "Bullish read-through.",
          decision_summary: "candidate_ready_for_analyst",
          strategy_decision: {
            status: "candidate_ready_for_analyst",
            candidate: null,
            rejection_reasons: [],
            rejection_details: [],
            audit: {},
            claude_analysis_allowed: true,
            audit_trail: {
              source_citations: [],
              citation_unavailable_reasons: [],
              rule_facts: [],
            },
          },
          candidate_brief: null,
          rejection_reasons: [],
          rejection_details: [],
          warnings: [],
          data_snapshot: {},
          settings_snapshot: {},
          missing_data: [],
          source_events: [],
        },
      }),
    ]);

    expect(parsed.map((record) => record.recordType)).toEqual([
      "strategy_decision",
      "risk_decision",
    ]);
  });

  it("keeps malformed payloads as loud parse errors", () => {
    const parsed = parseDecisionChain([
      row({
        record_type: "risk_decision",
        payload: { status: "blocked" },
      }),
    ]);

    expect(parsed[0].payload.ok).toBe(false);
    if (!parsed[0].payload.ok) {
      expect(parsed[0].payload.error).toMatch(/payload/i);
      expect(parsed[0].payload.raw).toEqual({ status: "blocked" });
    }
  });

  it("drops unsupported record types from the six-step product chain", () => {
    const parsed = parseDecisionChain([
      row({
        record_type: "trade_notification",
        payload: { delivery_status: "sent" },
      }),
    ]);

    expect(parsed).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- parse-decision-chain.test.ts
```

Expected: FAIL because `parse-decision-chain.ts` does not exist.

- [ ] **Step 3: Add format/order helpers**

Create `web/src/features/decisions/decision-chain-format.ts`:

```typescript
import type { DecisionChainRecordType } from "./decision-chain.types";

export const CHAIN_STEP: Record<
  DecisionChainRecordType,
  { order: number; label: string }
> = {
  strategy_decision: { order: 10, label: "Strategy decision" },
  analyst_review: { order: 20, label: "Analyst review" },
  risk_decision: { order: 30, label: "Risk decision" },
  position_sizing: { order: 40, label: "Position sizing" },
  execution_proposal: { order: 50, label: "Execution proposal" },
  trade_outcome: { order: 60, label: "Outcome" },
  outcome_correction: { order: 61, label: "Outcome correction" },
};

export function isDecisionChainRecordType(
  value: string,
): value is DecisionChainRecordType {
  return value in CHAIN_STEP;
}

export function badgeVariantForStatus(
  status: string | null | undefined,
): "success" | "danger" | "warning" | "muted" {
  if (!status) return "muted";
  if (
    [
      "approved",
      "analyzed",
      "candidate_ready_for_analyst",
      "sized",
      "proposed",
      "filled",
      "closed_win",
    ].includes(status)
  ) {
    return "success";
  }
  if (
    [
      "blocked",
      "rejected",
      "failed",
      "risk_blocked",
      "broker_rejected",
      "closed_loss",
    ].includes(status)
  ) {
    return "danger";
  }
  if (["not_evaluable", "needs_more_context", "pending"].includes(status)) {
    return "warning";
  }
  return "muted";
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatList(values: string[]): string {
  return values.length ? values.join(", ") : "-";
}
```

- [ ] **Step 4: Add the parser**

Create `web/src/features/decisions/parse-decision-chain.ts`:

```typescript
import {
  AnalystReviewPayloadSchema,
  ExecutionProposalPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  SourceCitationSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "./decision-chain-schemas";
import {
  type DecisionChainRecord,
  type DecisionChainRecordType,
  type JournalRecordRow,
  type PayloadParseResult,
  type SourceCitation,
} from "./decision-chain.types";
import { CHAIN_STEP, isDecisionChainRecordType } from "./decision-chain-format";

export function parseDecisionChain(rows: JournalRecordRow[]): DecisionChainRecord[] {
  return rows
    .filter((row) => isDecisionChainRecordType(row.record_type))
    .map((row) => {
      const recordType = row.record_type as DecisionChainRecordType;
      const step = CHAIN_STEP[recordType];
      return {
        row,
        recordType,
        label: step.label,
        order: step.order,
        payload: parsePayload(recordType, row.payload),
      };
    })
    .sort((a, b) => {
      if (a.order !== b.order) return a.order - b.order;
      return String(a.row.created_at).localeCompare(String(b.row.created_at));
    });
}

function parsePayload(
  recordType: DecisionChainRecordType,
  raw: unknown,
): PayloadParseResult {
  const schema = schemaFor(recordType);
  const result = schema.safeParse(raw);
  if (!result.success) {
    return {
      ok: false,
      error: `Decision ${recordType} payload did not match expected shape: ${result.error.message}`,
      raw,
    };
  }
  return {
    ok: true,
    data: result.data,
    citations: extractCitations(recordType, result.data),
  };
}

function schemaFor(recordType: DecisionChainRecordType) {
  switch (recordType) {
    case "strategy_decision":
      return StrategyDecisionPayloadSchema;
    case "analyst_review":
      return AnalystReviewPayloadSchema;
    case "risk_decision":
      return RiskDecisionPayloadSchema;
    case "position_sizing":
      return PositionSizingPayloadSchema;
    case "execution_proposal":
      return ExecutionProposalPayloadSchema;
    case "trade_outcome":
    case "outcome_correction":
      return TradeOutcomePayloadSchema;
  }
}

function extractCitations(
  recordType: DecisionChainRecordType,
  data: unknown,
): SourceCitation[] {
  const citations: unknown[] = [];

  if (recordType === "strategy_decision") {
    const payload = StrategyDecisionPayloadSchema.parse(data);
    citations.push(
      ...payload.strategy_decision.audit_trail.source_citations,
      ...(payload.candidate_brief?.source_citations ?? []),
    );
  }

  if (recordType === "analyst_review") {
    const payload = AnalystReviewPayloadSchema.parse(data);
    citations.push(...payload.claude_result.audit_trail.source_citations);
  }

  if (recordType === "risk_decision") {
    const payload = RiskDecisionPayloadSchema.parse(data);
    citations.push(...payload.risk_gate_decision.audit_trail.source_citations);
  }

  if (recordType === "position_sizing") {
    const payload = PositionSizingPayloadSchema.parse(data);
    citations.push(
      ...payload.position_sizing_decision.audit_trail.source_citations,
    );
  }

  const unique = new Map<string, SourceCitation>();
  for (const citation of citations) {
    const parsed = SourceCitationSchema.safeParse(citation);
    if (parsed.success) {
      unique.set(parsed.data.citation_id, parsed.data);
    }
  }
  return [...unique.values()];
}
```

- [ ] **Step 5: Run parser tests to verify they pass**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- parse-decision-chain.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-chain-format.ts \
  web/src/features/decisions/parse-decision-chain.ts \
  web/__tests__/parse-decision-chain.test.ts
git commit -m "feat(web): parse decision journal records into chain steps"
```

---

## Task 3: Add Supabase fetcher and TanStack Query hook

**Files:**
- Create: `web/src/features/decisions/fetch-decision-chain.ts`
- Create: `web/src/features/decisions/use-decision-chain.ts`
- Test: `web/__tests__/fetch-decision-chain.test.ts`

- [ ] **Step 1: Write the failing fetcher tests**

Create `web/__tests__/fetch-decision-chain.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { fetchDecisionChain } from "@/features/decisions/fetch-decision-chain";

function fakeSupabase(result: { data: unknown[] | null; error: { message: string } | null }) {
  const calls: string[] = [];
  return {
    calls,
    from(table: string) {
      calls.push(`from:${table}`);
      return {
        select(columns: string) {
          calls.push(`select:${columns}`);
          return {
            eq(column: string, value: string) {
              calls.push(`eq:${column}:${value}`);
              return {
                order(column: string, options: { ascending: boolean }) {
                  calls.push(`order:${column}:${options.ascending}`);
                  return Promise.resolve(result);
                },
              };
            },
          };
        },
      };
    },
  };
}

describe("fetchDecisionChain", () => {
  it("queries journal_records by decision_id in chronological order", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await fetchDecisionChain(supabase as never, "decision-1");

    expect(supabase.calls).toEqual([
      "from:journal_records",
      "select:*",
      "eq:decision_id:decision-1",
      "order:created_at:true",
    ]);
  });

  it("throws a readable error when Supabase returns an error", async () => {
    const supabase = fakeSupabase({
      data: null,
      error: { message: "RLS blocked request" },
    });

    await expect(fetchDecisionChain(supabase as never, "decision-1")).rejects.toThrow(
      "RLS blocked request",
    );
  });
});
```

- [ ] **Step 2: Run the fetcher tests to verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- fetch-decision-chain.test.ts
```

Expected: FAIL because `fetch-decision-chain.ts` does not exist.

- [ ] **Step 3: Create the fetcher**

Create `web/src/features/decisions/fetch-decision-chain.ts`:

```typescript
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/supabase/database.types";
import type { DecisionChainRecord, JournalRecordRow } from "./decision-chain.types";
import { parseDecisionChain } from "./parse-decision-chain";

type PrescientSupabase = Pick<
  SupabaseClient<Database, "prescient_storage">,
  "from"
>;

export async function fetchDecisionChain(
  supabase: PrescientSupabase,
  decisionId: string,
): Promise<DecisionChainRecord[]> {
  const { data, error } = await supabase
    .from("journal_records")
    .select("*")
    .eq("decision_id", decisionId)
    .order("created_at", { ascending: true });

  if (error) {
    throw new Error(`Failed to load decision chain: ${error.message}`);
  }

  return parseDecisionChain((data ?? []) as JournalRecordRow[]);
}
```

- [ ] **Step 4: Create the TanStack Query hook**

Create `web/src/features/decisions/use-decision-chain.ts`:

```typescript
"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import { fetchDecisionChain } from "./fetch-decision-chain";

export function useDecisionChain(decisionId: string) {
  const supabase = useMemo(() => createClient(), []);

  return useQuery({
    queryKey: ["decision-chain", decisionId],
    queryFn: () => fetchDecisionChain(supabase, decisionId),
    enabled: decisionId.length > 0,
  });
}
```

- [ ] **Step 5: Run the fetcher tests to verify they pass**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- fetch-decision-chain.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/fetch-decision-chain.ts \
  web/src/features/decisions/use-decision-chain.ts \
  web/__tests__/fetch-decision-chain.test.ts
git commit -m "feat(web): add decision chain query hook"
```

---

## Task 4: Build read-only chain components

**Files:**
- Create: `web/src/features/decisions/source-citations.tsx`
- Create: `web/src/features/decisions/decision-chain-card.tsx`
- Create: `web/src/features/decisions/decision-chain-view.tsx`
- Test: `web/__tests__/decision-chain-view.test.tsx`

- [ ] **Step 1: Write the failing component tests**

Create `web/__tests__/decision-chain-view.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionChainView } from "@/features/decisions/decision-chain-view";
import type { DecisionChainRecord } from "@/features/decisions/decision-chain.types";

function baseRecord(overrides: Partial<DecisionChainRecord>): DecisionChainRecord {
  return {
    recordType: "risk_decision",
    label: "Risk decision",
    order: 30,
    row: {
      journal_record_id: "risk",
      record_type: "risk_decision",
      run_id: "scheduled:2026-06-03",
      decision_id: "decision-1",
      decision_index: 0,
      trading_date: "2026-06-03",
      created_at: "2026-06-03T15:02:00Z",
      target: "NTNX",
      theme: "AI_STORAGE",
      strategy_type: "bullish_earnings_readthrough",
      strategy_status: "candidate_ready_for_analyst",
      execution_mode: "propose_only",
      source: "prescient.runtime",
      provider: null,
      order_id: null,
      parent_record_id: null,
      duplicate_of_record_id: null,
      payload: {},
      schema_version: 1,
    },
    payload: {
      ok: true,
      citations: [],
      data: {
        risk_gate_decision: {
          target: "NTNX",
          theme: "AI_STORAGE",
          strategy_status: "candidate_ready_for_analyst",
          status: "blocked",
          rejection_reasons: ["missing_order_proposal"],
          explanation: "Risk gate requires a structured order proposal.",
          broker_execution_allowed: false,
          claude_present: true,
          claude_override_attempted: false,
          audit_trail: {
            source_citations: [],
            citation_unavailable_reasons: [],
            rule_facts: [],
          },
        },
        status: "blocked",
        rejection_reasons: ["missing_order_proposal"],
        broker_execution_allowed: false,
      },
    },
    ...overrides,
  };
}

describe("DecisionChainView", () => {
  it("renders risk as the visually dominant rails card", () => {
    render(<DecisionChainView decisionId="decision-1" records={[baseRecord({})]} />);

    expect(screen.getByRole("heading", { name: /risk decision/i })).toBeInTheDocument();
    expect(screen.getByText("blocked")).toBeInTheDocument();
    expect(screen.getByText(/structured order proposal/i)).toBeInTheDocument();
    expect(screen.getByText("missing_order_proposal")).toBeInTheDocument();
  });

  it("labels analyst review as advisory only", () => {
    render(
      <DecisionChainView
        decisionId="decision-1"
        records={[
          baseRecord({
            recordType: "analyst_review",
            label: "Analyst review",
            order: 20,
            payload: {
              ok: true,
              citations: [],
              data: {
                claude_result: {
                  status: "analyzed",
                  analysis: {
                    recommendation: "go",
                    thesis: "Peer demand is supportive.",
                    reasoning: "Multiple peers cited AI demand.",
                    conviction_score: 71,
                    missing_context: [],
                    contradictions: [],
                    suggested_expression: "CALL_OPTION",
                    cited_citation_ids: [],
                  },
                  error_message: null,
                  audit_trail: {
                    source_citations: [],
                    citation_unavailable_reasons: [],
                    rule_facts: [],
                  },
                },
                status: "analyzed",
                analysis: null,
                error_message: null,
              },
            },
          }),
        ]}
      />,
    );

    expect(screen.getByText(/advisory only/i)).toBeInTheDocument();
    expect(screen.getByText(/not authorization/i)).toBeInTheDocument();
  });

  it("shows malformed payloads with ErrorState and raw detail", () => {
    render(
      <DecisionChainView
        decisionId="decision-1"
        records={[
          baseRecord({
            payload: {
              ok: false,
              error: "Decision risk_decision payload did not match expected shape",
              raw: { status: "blocked" },
            },
          }),
        ]}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/did not match/i);
    expect(screen.getByText(/"status": "blocked"/)).toBeInTheDocument();
  });

  it("does not render trading action controls", () => {
    render(<DecisionChainView decisionId="decision-1" records={[baseRecord({})]} />);

    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /size/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the component tests to verify they fail**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-chain-view.test.tsx
```

Expected: FAIL because the chain components do not exist.

- [ ] **Step 3: Create source citation rendering**

Create `web/src/features/decisions/source-citations.tsx`:

```tsx
import type { SourceCitation } from "./decision-chain.types";

export function SourceCitations({ citations }: { citations: SourceCitation[] }) {
  if (citations.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No source citations recorded for this step.
      </p>
    );
  }

  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-sm font-medium">
        Sources ({citations.length})
      </summary>
      <ul className="mt-2 space-y-2 text-sm">
        {citations.map((citation) => (
          <li key={citation.citation_id} className="rounded-md bg-muted p-2">
            <div className="font-medium">
              {citation.title || citation.citation_id}
            </div>
            <div className="text-xs text-muted-foreground">
              {citation.provider} / {citation.source_type}
              {citation.confidence ? ` / ${citation.confidence}` : ""}
            </div>
            {citation.url ? (
              <a
                href={citation.url}
                className="text-xs underline"
                target="_blank"
                rel="noreferrer"
              >
                {citation.url}
              </a>
            ) : null}
            {citation.excerpt ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {citation.excerpt}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
```

- [ ] **Step 4: Create the per-record card**

Create `web/src/features/decisions/decision-chain-card.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/states/error-state";
import type {
  AnalystReviewPayload,
  DecisionChainRecord,
  ExecutionProposalPayload,
  PositionSizingPayload,
  RiskDecisionPayload,
  StrategyDecisionPayload,
  TradeOutcomePayload,
} from "./decision-chain.types";
import {
  badgeVariantForStatus,
  formatList,
  formatMoney,
} from "./decision-chain-format";
import { SourceCitations } from "./source-citations";

export function DecisionChainCard({ record }: { record: DecisionChainRecord }) {
  const isRisk = record.recordType === "risk_decision";

  return (
    <Card
      className={
        isRisk
          ? "border-danger bg-danger/5"
          : "border-border bg-card"
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{record.label}</h2>
          <p className="text-xs text-muted-foreground">
            {record.row.created_at} / {record.row.source}
          </p>
        </div>
        <Badge variant="muted">{record.recordType}</Badge>
      </div>

      <div className="mt-4">
        {!record.payload.ok ? (
          <ErrorState
            title={record.payload.error}
            detail={JSON.stringify(record.payload.raw, null, 2)}
          />
        ) : (
          <>
            <PayloadBody record={record} />
            <SourceCitations citations={record.payload.citations} />
          </>
        )}
      </div>
    </Card>
  );
}

function PayloadBody({ record }: { record: DecisionChainRecord }) {
  if (!record.payload.ok) return null;

  switch (record.recordType) {
    case "strategy_decision":
      return <StrategyBody payload={record.payload.data as StrategyDecisionPayload} />;
    case "analyst_review":
      return <AnalystBody payload={record.payload.data as AnalystReviewPayload} />;
    case "risk_decision":
      return <RiskBody payload={record.payload.data as RiskDecisionPayload} />;
    case "position_sizing":
      return <SizingBody payload={record.payload.data as PositionSizingPayload} />;
    case "execution_proposal":
      return (
        <RawReadOnlyBody
          label="Read-only execution proposal"
          payload={record.payload.data as ExecutionProposalPayload}
        />
      );
    case "trade_outcome":
    case "outcome_correction":
      return <OutcomeBody payload={record.payload.data as TradeOutcomePayload} />;
  }
}

function StrategyBody({ payload }: { payload: StrategyDecisionPayload }) {
  const candidate = payload.candidate_brief;
  return (
    <div className="space-y-3">
      <p>{payload.thesis}</p>
      <Badge variant={badgeVariantForStatus(payload.decision_summary)}>
        {payload.decision_summary}
      </Badge>
      {candidate ? (
        <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <Field label="Target" value={candidate.target} />
          <Field label="Theme" value={candidate.theme} />
          <Field label="Expression" value={candidate.recommended_expression} />
          <Field
            label="Reported peers"
            value={formatList(candidate.reported_peers)}
          />
        </dl>
      ) : null}
      {payload.rejection_reasons.length ? (
        <ReasonList title="Strategy rejections" values={payload.rejection_reasons} />
      ) : null}
    </div>
  );
}

function AnalystBody({ payload }: { payload: AnalystReviewPayload }) {
  const analysis = payload.claude_result.analysis;
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-warning bg-warning/10 p-3 text-sm">
        Claude analyst review is advisory only, not authorization.
      </div>
      <Badge variant={badgeVariantForStatus(payload.status)}>{payload.status}</Badge>
      {analysis ? (
        <div className="space-y-2 text-sm">
          <p className="font-medium">{analysis.thesis}</p>
          <p>{analysis.reasoning}</p>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="Recommendation" value={analysis.recommendation} />
            <Field
              label="Conviction"
              value={`${analysis.conviction_score}/100`}
            />
            <Field label="Suggested expression" value={analysis.suggested_expression} />
            <Field
              label="Cited IDs"
              value={formatList(analysis.cited_citation_ids)}
            />
          </dl>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {payload.error_message || "No analyst reasoning was recorded."}
        </p>
      )}
    </div>
  );
}

function RiskBody({ payload }: { payload: RiskDecisionPayload }) {
  const risk = payload.risk_gate_decision;
  return (
    <div className="space-y-3">
      <Badge variant={badgeVariantForStatus(risk.status)}>{risk.status}</Badge>
      <p className="font-medium">{risk.explanation}</p>
      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <Field
          label="Broker execution"
          value={risk.broker_execution_allowed ? "allowed" : "blocked"}
        />
        <Field label="Claude present" value={risk.claude_present ? "yes" : "no"} />
        <Field
          label="Claude override"
          value={risk.claude_override_attempted ? "attempted" : "none"}
        />
      </dl>
      <ReasonList title="Risk reasons" values={risk.rejection_reasons} />
    </div>
  );
}

function SizingBody({ payload }: { payload: PositionSizingPayload }) {
  const sizing = payload.position_sizing_decision;
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-muted p-3 text-sm">
        Position sizing is read-only. It is code-decided and never editable here.
      </div>
      <Badge variant={badgeVariantForStatus(sizing.status)}>{sizing.status}</Badge>
      <p>{sizing.explanation}</p>
      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <Field label="Expression" value={sizing.expression || "-"} />
        <Field label="Approved quantity" value={String(sizing.approved_quantity)} />
        <Field
          label="Projected max loss"
          value={formatMoney(sizing.projected_max_loss)}
        />
        <Field
          label="Entry cost required"
          value={formatMoney(sizing.entry_cost_required)}
        />
      </dl>
      <ReasonList title="Sizing reasons" values={sizing.rejection_reasons} />
    </div>
  );
}

function OutcomeBody({ payload }: { payload: TradeOutcomePayload }) {
  const outcome = payload.outcome;
  return (
    <div className="space-y-3">
      <Badge variant={badgeVariantForStatus(outcome.outcome_type)}>
        {outcome.outcome_type}
      </Badge>
      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <Field label="Net P&L" value={formatMoney(outcome.net_realized_pnl)} />
        <Field label="Gross P&L" value={formatMoney(outcome.gross_realized_pnl)} />
        <Field label="Fees" value={formatMoney(outcome.fees)} />
        <Field label="Ambiguous" value={outcome.ambiguous ? "yes" : "no"} />
      </dl>
      <ReasonList title="Outcome reasons" values={outcome.outcome_reasons} />
    </div>
  );
}

function RawReadOnlyBody({
  label,
  payload,
}: {
  label: string;
  payload: ExecutionProposalPayload;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-muted p-3 text-sm">
        {label}. No action is available from this screen.
      </div>
      <details>
        <summary className="cursor-pointer text-sm font-medium">
          Raw proposal payload
        </summary>
        <pre className="mt-2 overflow-auto rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function ReasonList({ title, values }: { title: string; values: string[] }) {
  if (!values.length) {
    return <p className="text-sm text-muted-foreground">{title}: none</p>;
  }
  return (
    <div>
      <p className="text-sm font-medium">{title}</p>
      <ul className="mt-1 list-disc pl-5 text-sm">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Create the chain view**

Create `web/src/features/decisions/decision-chain-view.tsx`:

```tsx
import { EmptyState } from "@/components/states/empty-state";
import type { DecisionChainRecord } from "./decision-chain.types";
import { DecisionChainCard } from "./decision-chain-card";

export function DecisionChainView({
  decisionId,
  records,
}: {
  decisionId: string;
  records: DecisionChainRecord[];
}) {
  if (records.length === 0) {
    return (
      <EmptyState message={`No journal records found for decision ${decisionId}.`} />
    );
  }

  const first = records[0].row;

  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <p className="text-sm text-muted-foreground">Decision chain</p>
        <h1 className="text-2xl font-semibold">
          {first.target || "Unknown target"} / {first.theme || "Unknown theme"}
        </h1>
        <p className="text-sm text-muted-foreground">
          {decisionId} / run {first.run_id}
        </p>
      </header>

      <div className="space-y-4">
        {records.map((record) => (
          <DecisionChainCard
            key={record.row.journal_record_id}
            record={record}
          />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 6: Run component tests to verify they pass**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-chain-view.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/source-citations.tsx \
  web/src/features/decisions/decision-chain-card.tsx \
  web/src/features/decisions/decision-chain-view.tsx \
  web/__tests__/decision-chain-view.test.tsx
git commit -m "feat(web): render read-only decision chain cards"
```

---

## Task 5: Add the `/decisions/[id]` route

**Files:**
- Create: `web/src/features/decisions/decision-chain-client.tsx`
- Create: `web/src/app/(app)/decisions/[id]/page.tsx`

- [ ] **Step 1: Create the client container**

Create `web/src/features/decisions/decision-chain-client.tsx`:

```tsx
"use client";

import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { DecisionChainView } from "./decision-chain-view";
import { useDecisionChain } from "./use-decision-chain";

export function DecisionChainClient({ decisionId }: { decisionId: string }) {
  const query = useDecisionChain(decisionId);

  if (query.isLoading) {
    return <LoadingState label="Loading decision chain..." />;
  }

  if (query.isError) {
    return (
      <ErrorState
        title="Could not load decision chain"
        detail={query.error instanceof Error ? query.error.message : String(query.error)}
      />
    );
  }

  return (
    <DecisionChainView decisionId={decisionId} records={query.data ?? []} />
  );
}
```

- [ ] **Step 2: Create the dynamic route**

Create `web/src/app/(app)/decisions/[id]/page.tsx`:

```tsx
import { DecisionChainClient } from "@/features/decisions/decision-chain-client";

export default async function DecisionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DecisionChainClient decisionId={decodeURIComponent(id)} />;
}
```

- [ ] **Step 3: Verify typecheck and build**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npx tsc --noEmit
npm run build
```

Expected: both commands pass; `/decisions/[id]` is included in the build.

- [ ] **Step 4: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add "web/src/app/(app)/decisions/[id]/page.tsx" \
  web/src/features/decisions/decision-chain-client.tsx
git commit -m "feat(web): add decision chain detail route"
```

---

## Task 6: Link Slice 1 decision rows to the chain route

**Files:**
- Modify: `web/src/features/decisions/decision-list.tsx`
- Test: `web/__tests__/decision-list-links.test.tsx`

> If Slice 1 implemented the decision table in a different file, first normalize it into `web/src/features/decisions/decision-list.tsx`. Do not keep two separate decision tables.

- [ ] **Step 1: Write or update the failing row-link test**

Create or update `web/__tests__/decision-list-links.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionList } from "@/features/decisions/decision-list";

describe("DecisionList links", () => {
  it("links each decision row to its decision chain detail route", () => {
    render(
      <DecisionList
        decisions={[
          {
            decision_record_id: "decision-record-1",
            run_id: "scheduled:2026-06-03",
            decision_id: "decision-1",
            decision_index: 0,
            trading_date: "2026-06-03",
            target: "NTNX",
            theme: "AI_STORAGE",
            strategy_type: "bullish_earnings_readthrough",
            strategy_status: "candidate_ready_for_analyst",
            execution_mode: "propose_only",
            payload: {
              status: "proposed",
              outcome_type: "pending",
            },
            schema_version: 1,
            created_at: "2026-06-03T15:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: /NTNX/i })).toHaveAttribute(
      "href",
      "/decisions/decision-1",
    );
  });
});
```

- [ ] **Step 2: Run the row-link test to verify it fails**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list-links.test.tsx
```

Expected: FAIL until the target cell/row is a link.

- [ ] **Step 3: Update the decision list target cell**

In `web/src/features/decisions/decision-list.tsx`, import `Link`:

```tsx
import Link from "next/link";
```

Render the target cell as a link:

```tsx
<Link
  href={`/decisions/${encodeURIComponent(decision.decision_id)}`}
  className="font-medium underline-offset-2 hover:underline"
>
  {decision.target || "Unknown target"}
</Link>
```

Use the existing `decision` variable from the Slice 1 table row. Do not add any action buttons in this table.

- [ ] **Step 4: Run the row-link test to verify it passes**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test -- decision-list-links.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add web/src/features/decisions/decision-list.tsx \
  web/__tests__/decision-list-links.test.tsx
git commit -m "feat(web): link decisions to chain detail route"
```

---

## Task 7: Full verification and safety audit

**Files:** none, unless verification finds a real issue

- [ ] **Step 1: Run the frontend test suite**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm test
```

Expected: all frontend tests pass, including Slice 0, Slice 1, and Slice 2 tests.

- [ ] **Step 2: Run typecheck and production build**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npx tsc --noEmit
npm run build
```

Expected: both commands pass.

- [ ] **Step 3: Search for forbidden frontend action language**

Run:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
rg -n "buy|approve|place order|size trade|edit size|Claude\\(" src __tests__ || true
```

Expected: no matches that represent UI actions. Acceptable matches include test assertions proving forbidden buttons are absent and static "advisory only" copy.

- [ ] **Step 4: Manual browser verification**

Run the dev server:

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient/web
npm run dev
```

Expected: dev server starts, usually at `http://localhost:3000`.

Then verify:

1. Open `http://localhost:3000/decisions` while signed in.
2. Click a decision target link.
3. Confirm the route changes to `/decisions/<decision_id>`.
4. Confirm the page shows the chain cards in this order when records exist: Strategy decision, Analyst review, Risk decision, Position sizing, Execution proposal, Outcome.
5. Confirm malformed payloads show the loud `ErrorState` with raw detail.
6. Confirm there is no buy, approve, edit-size, or client-Claude action.

- [ ] **Step 5: Final commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/prescient
git add -A
git commit -m "chore(web): verify decision chain slice end-to-end"
```

---

## Definition of Done (Slice 2)

- `/decisions/[id]` is authenticated through the existing `(app)` layout guard.
- `/decisions` rows link to `/decisions/[decision_id]`.
- `useDecisionChain(decisionId)` fetches `journal_records` from Supabase through the existing typed client and TanStack Query.
- The chain renders known record types in product order: strategy decision, analyst review, risk decision, position sizing, execution proposal, trade outcome/outcome correction.
- `strategy_decision`, `analyst_review`, `risk_decision`, `position_sizing`, and `trade_outcome` payloads are parsed with Zod before rendering.
- Malformed payloads render a loud `ErrorState` with raw details, never a blank or guessed card.
- Source citations render from parsed payload audit trails where present.
- Analyst review is explicitly labeled advisory-only and not authorization.
- Position sizing is explicitly read-only and never editable.
- No trade action UI exists: no buy, approve, place-order, size-trade, or client-side Claude call.
- `npm test`, `npx tsc --noEmit`, and `npm run build` pass.

Core loop is shippable after this slice: the operator can log in, see decisions, click one, and understand what the engine proposed and why.
