import { describe, expect, it } from "vitest";
import {
  AnalystReviewPayloadSchema,
  ExecutionProposalPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "@/features/decisions/decision-chain-schemas";
import {
  analystPayload,
  executionPayload,
  outcomePayload,
  positionSizingPayload,
  riskPayload,
  strategyPayload,
} from "./decision-chain-fixtures";

describe("decision chain payload schemas", () => {
  it("accepts fixed strategy decision envelopes", () => {
    const result = StrategyDecisionPayloadSchema.parse(strategyPayload);

    expect(result.strategy_decision.status).toBe(
      "candidate_ready_for_analyst",
    );
    expect(result.candidate_brief?.source_citations[0]?.citation_id).toBe(
      "citation-1",
    );
  });

  it("accepts fixed analyst review envelopes", () => {
    const result = AnalystReviewPayloadSchema.parse(analystPayload);

    expect(result.status).toBe("analyzed");
    expect(result.analysis?.recommendation).toBe("support");
  });

  it("accepts fixed risk decision envelopes", () => {
    const result = RiskDecisionPayloadSchema.parse(riskPayload);

    expect(result.risk_gate_decision.status).toBe("risk_passed");
    expect(result.broker_execution_allowed).toBe(false);
  });

  it("accepts fixed position sizing envelopes", () => {
    const result = PositionSizingPayloadSchema.parse(positionSizingPayload);

    expect(result.position_sizing_decision.approved_quantity).toBe(4);
    expect(result.projected_max_loss).toBe(1000);
  });

  it("accepts generic execution proposal objects as raw read-only data", () => {
    const result = ExecutionProposalPayloadSchema.parse(executionPayload);

    expect(result.proposal_status).toBe("proposed");
  });

  it("accepts trade outcome and outcome correction envelopes", () => {
    const result = TradeOutcomePayloadSchema.parse(outcomePayload);

    expect(result.outcome.outcome_type).toBe("pending");
    expect(result.outcome.pnl_currency).toBe("USD");
  });

  it("rejects malformed known envelopes loudly", () => {
    expect(() => RiskDecisionPayloadSchema.parse({ status: "risk_passed" })).toThrow();
  });
});
