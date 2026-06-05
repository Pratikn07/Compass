import { describe, expect, it } from "vitest";
import { DecisionListPayloadSchema } from "@/features/decisions/decision-list-schemas";
import {
  systemHealthRowSchema,
  watchlistItemRowSchema,
  watchlistRowSchema,
} from "@/features/decisions/decision-sidebar-schemas";

describe("DecisionListPayloadSchema", () => {
  it("parses the strategy_decision payload fields needed by the list", () => {
    const parsed = DecisionListPayloadSchema.parse({
      thesis: "Bullish AI_STORAGE read-through for NTNX.",
      decision_summary: "candidate_ready_for_analyst",
      candidate_brief: {
        target: "NTNX",
        theme: "AI_STORAGE",
        earnings_date: "2026-06-02",
        main_thesis: "AI storage peers reported strong demand.",
        peer_signal_score: 2.67,
        supporting_evidence: ["4 of 5 peers reported positive AI storage demand."],
      },
    });

    expect(parsed.thesis).toContain("NTNX");
    expect(parsed.decision_summary).toBe("candidate_ready_for_analyst");
    expect(parsed.candidate_brief?.target).toBe("NTNX");
    expect(parsed.candidate_brief?.earnings_date).toBe("2026-06-02");
    expect(parsed.candidate_brief?.supporting_evidence).toEqual([
      "4 of 5 peers reported positive AI storage demand.",
    ]);
    expect(parsed.candidate_brief?.peer_signal_score).toBe(2.67);
  });

  it("allows missing payload detail because table columns carry the list spine", () => {
    const parsed = DecisionListPayloadSchema.parse({});

    expect(parsed).toEqual({});
  });
});

describe("decision sidebar schemas", () => {
  it("parses read-only watchlists and items", () => {
    const watchlist = watchlistRowSchema.parse({
      watchlist_id: "theme:AI_STORAGE",
      name: "AI STORAGE",
      description: "AI data center demand",
      source: "strategy_universe",
      schema_version: 1,
      created_at: "2026-06-01T14:00:00Z",
      updated_at: "2026-06-01T14:00:00Z",
    });
    const item = watchlistItemRowSchema.parse({
      watchlist_item_id: "theme:AI_STORAGE:NTNX",
      watchlist_id: "theme:AI_STORAGE",
      ticker: "NTNX",
      theme: "AI_STORAGE",
      sort_order: 0,
      schema_version: 1,
      created_at: "2026-06-01T14:00:00Z",
    });

    expect(watchlist.watchlistId).toBe("theme:AI_STORAGE");
    expect(watchlist.source).toBe("strategy_universe");
    expect(item.ticker).toBe("NTNX");
    expect(item.theme).toBe("AI_STORAGE");
  });

  it("parses backend-owned system health rows", () => {
    const parsed = systemHealthRowSchema.parse({
      system_health_id: "scheduled:2026-06-01:market_data",
      component: "market_data",
      status: "degraded",
      detail: "Provider errors in the latest run.",
      latency_seconds: 12,
      run_id: "scheduled:2026-06-01",
      schema_version: 1,
      created_at: "2026-06-01T14:30:00Z",
    });

    expect(parsed.component).toBe("market_data");
    expect(parsed.status).toBe("degraded");
    expect(parsed.latencySeconds).toBe(12);
    expect(parsed.runId).toBe("scheduled:2026-06-01");
  });
});
