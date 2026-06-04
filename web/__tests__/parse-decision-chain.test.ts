import { describe, expect, it } from "vitest";
import { parseDecisionChain } from "@/features/decisions/parse-decision-chain";
import {
  analystPayload,
  executionPayload,
  journalRow,
  outcomePayload,
  positionSizingPayload,
  riskPayload,
  strategyPayload,
} from "./decision-chain-fixtures";

describe("parseDecisionChain", () => {
  it("orders supported records by the product decision chain", () => {
    const records = parseDecisionChain([
      journalRow({
        created_at: "2026-06-01T14:35:00Z",
        journal_record_id: "journal-risk",
        payload: riskPayload,
        record_type: "risk_decision",
      }),
      journalRow({
        created_at: "2026-06-01T14:40:00Z",
        journal_record_id: "journal-sizing",
        payload: positionSizingPayload,
        record_type: "position_sizing",
      }),
      journalRow({
        created_at: "2026-06-01T14:30:00Z",
        journal_record_id: "journal-strategy",
        payload: strategyPayload,
        record_type: "strategy_decision",
      }),
      journalRow({
        created_at: "2026-06-01T14:50:00Z",
        journal_record_id: "journal-outcome",
        payload: outcomePayload,
        record_type: "trade_outcome",
      }),
      journalRow({
        created_at: "2026-06-01T14:45:00Z",
        journal_record_id: "journal-execution",
        payload: executionPayload,
        record_type: "execution_proposal",
      }),
      journalRow({
        created_at: "2026-06-01T14:33:00Z",
        journal_record_id: "journal-analyst",
        payload: analystPayload,
        record_type: "analyst_review",
      }),
    ]);

    expect(records.map((record) => record.recordType)).toEqual([
      "strategy_decision",
      "analyst_review",
      "risk_decision",
      "position_sizing",
      "execution_proposal",
      "trade_outcome",
    ]);
  });

  it("keeps malformed known payloads with raw diagnostic detail", () => {
    const [record] = parseDecisionChain([
      journalRow({
        payload: { status: "risk_passed" },
        record_type: "risk_decision",
      }),
    ]);

    expect(record?.payload.ok).toBe(false);
    expect(record?.payload).toMatchObject({
      error: expect.stringContaining("risk_decision payload did not match"),
      raw: { status: "risk_passed" },
    });
  });

  it("filters unsupported journal record types", () => {
    const records = parseDecisionChain([
      journalRow({ record_type: "provider_snapshot" }),
      journalRow({ record_type: "strategy_decision" }),
    ]);

    expect(records).toHaveLength(1);
    expect(records[0]?.recordType).toBe("strategy_decision");
  });

  it("extracts source citations from parsed payload audit trails", () => {
    const [record] = parseDecisionChain([
      journalRow({
        payload: riskPayload,
        record_type: "risk_decision",
      }),
    ]);

    expect(record?.payload.ok).toBe(true);
    if (record?.payload.ok) {
      expect(record.payload.citations).toEqual([
        expect.objectContaining({ citation_id: "citation-1" }),
      ]);
    }
  });
});
