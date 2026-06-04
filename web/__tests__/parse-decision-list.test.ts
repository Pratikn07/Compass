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
        malformed: false,
        rawPayload: null,
      },
    ]);
  });

  it("flags a row as malformed and keeps the raw payload when the shape is unexpected", () => {
    const decisions = parseDecisionList([
      row({ payload: { thesis: 42, candidate_brief: { target: 99 } } }),
    ]);

    expect(decisions[0].malformed).toBe(true);
    expect(decisions[0].status).toBe("malformed");
    expect(decisions[0].rawPayload).toContain("42");
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
    expect(badgeVariantForDecisionValue("candidate_ready_for_analyst")).toBe(
      "success",
    );
    expect(badgeVariantForDecisionValue("proposed")).toBe("success");
    expect(badgeVariantForDecisionValue("risk_blocked")).toBe("danger");
    expect(badgeVariantForDecisionValue("rejected_with_reason")).toBe("danger");
    expect(badgeVariantForDecisionValue("pending")).toBe("muted");
    expect(badgeVariantForDecisionValue(null)).toBe("warning");
  });

  it("formats snake case values for table text", () => {
    expect(formatDecisionValue("bullish_earnings_readthrough")).toBe(
      "bullish earnings readthrough",
    );
    expect(formatDecisionValue(null)).toBe("unknown");
  });
});
