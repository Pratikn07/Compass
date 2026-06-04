import { describe, expect, it } from "vitest";
import {
  fetchDecisionChain,
  type DecisionChainSupabase,
} from "@/features/decisions/fetch-decision-chain";
import { journalRow, riskPayload } from "./decision-chain-fixtures";

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
          return Promise.resolve(result);
        },
      };
    },
  };
}

describe("fetchDecisionChain", () => {
  it("queries journal_records by decision id in created order", async () => {
    const supabase = fakeSupabase({
      data: [
        journalRow({
          payload: riskPayload,
          record_type: "risk_decision",
        }),
      ],
      error: null,
    });

    const chain = await fetchDecisionChain(
      supabase as unknown as DecisionChainSupabase,
      "decision-1",
    );

    expect(chain[0]?.recordType).toBe("risk_decision");
    expect(supabase.calls).toEqual([
      "from:journal_records",
      "select:*",
      "eq:decision_id:decision-1",
      "order:created_at:true",
    ]);
  });

  it("propagates readable Supabase errors", async () => {
    const supabase = fakeSupabase({
      data: null,
      error: { message: "permission denied for table journal_records" },
    });

    await expect(
      fetchDecisionChain(
        supabase as unknown as DecisionChainSupabase,
        "decision-1",
      ),
    ).rejects.toThrow("permission denied for table journal_records");
  });
});
