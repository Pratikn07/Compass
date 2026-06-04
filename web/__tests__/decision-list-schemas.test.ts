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
