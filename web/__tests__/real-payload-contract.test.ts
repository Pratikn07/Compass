import { describe, expect, it } from "vitest";
import realPayload from "./real-strategy-payload.json";
import { StrategyDecisionPayloadSchema } from "@/features/decisions/decision-chain-schemas";
import { DecisionListPayloadSchema } from "@/features/decisions/decision-list-schemas";

// Contract test: a payload produced by the REAL deterministic engine
// (build_strategy_decision_record over the acceptance-test bullish fixture)
// must parse cleanly through the frontend's Zod schemas. If the engine changes
// shape, this fails loudly instead of surfacing as a malformed row in prod.
describe("engine payload <-> frontend schema contract", () => {
  const entry = (realPayload as Record<string, { payload: unknown }>)[
    Object.keys(realPayload)[0]
  ];

  it("strategy_decision payload parses under StrategyDecisionPayloadSchema", () => {
    const result = StrategyDecisionPayloadSchema.safeParse(entry.payload);
    if (!result.success) {
      // Surface the exact field mismatches for the report.
      console.error(JSON.stringify(result.error.issues, null, 2));
    }
    expect(result.success).toBe(true);
  });

  it("the same payload parses under the list schema (used for the table)", () => {
    const result = DecisionListPayloadSchema.safeParse(entry.payload);
    expect(result.success).toBe(true);
  });
});
