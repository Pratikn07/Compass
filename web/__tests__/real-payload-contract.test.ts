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

  it("documents strategy fields that are already usable for richer frontend views", () => {
    const result = StrategyDecisionPayloadSchema.safeParse(entry.payload);
    expect(result.success).toBe(true);
    if (!result.success) return;

    const candidate = result.data.candidate_brief;
    expect(candidate?.earnings_date).toBe("2026-06-02");
    expect(typeof candidate?.peer_signal_score).toBe("number");
    expect(candidate?.supporting_evidence.length).toBeGreaterThan(0);
    expect(candidate?.peer_scores.length).toBeGreaterThan(0);
    expect(result.data.data_snapshot.option_contract_count).toBe(1);
  });

  it("documents visual-target fields that are not stable frontend contracts yet", () => {
    const result = StrategyDecisionPayloadSchema.safeParse(entry.payload);
    expect(result.success).toBe(true);
    if (!result.success) return;

    const payload = result.data as Record<string, unknown>;
    const candidate = result.data.candidate_brief as Record<string, unknown>;
    const snapshot = result.data.data_snapshot as {
      options_chain_summary?: Array<Record<string, unknown>>;
    } & Record<string, unknown>;
    const optionSummary = snapshot.options_chain_summary?.[0] ?? {};

    for (const unavailableField of [
      "company_name",
      "edge_bp",
      "needs_attention",
      "confidence",
      "list_confidence",
      "key_drivers",
    ]) {
      expect(payload).not.toHaveProperty(unavailableField);
      expect(candidate).not.toHaveProperty(unavailableField);
      expect(snapshot).not.toHaveProperty(unavailableField);
    }

    for (const unavailableOptionLegField of [
      "strike",
      "side",
      "iv",
      "price",
      "credit",
      "breakeven",
      "breakevens",
    ]) {
      expect(optionSummary).not.toHaveProperty(unavailableOptionLegField);
    }
  });
});
