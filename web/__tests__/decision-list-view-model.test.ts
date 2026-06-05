import { describe, expect, it } from "vitest";
import {
  buildDecisionListViewModel,
  normalizeDecisionListParams,
} from "@/features/decisions/decision-list-view-model";
import type { DecisionListItem } from "@/features/decisions/decision-list.types";
import type { DecisionWatchlist } from "@/features/decisions/decision-sidebar-schemas";

function decision(overrides: Partial<DecisionListItem> = {}): DecisionListItem {
  return {
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
    earningsDate: "2026-06-02",
    evidenceSummary: "AI storage peers reported strong demand.",
    peerSignalScore: 2.67,
    attentionStatus: "normal",
    attentionReasons: [],
    malformed: false,
    rawPayload: null,
    ...overrides,
  };
}

const decisions = [
  decision(),
  decision({
    decisionId: "decision-2",
    target: "NVDA",
    theme: "AI_INFRA",
    strategyType: "bullish_earnings_readthrough",
    status: "rejected_with_reason",
    outcome: "no_trade",
    thesis: "Rejected strategy decision for NVDA.",
    earningsDate: "2026-06-04",
    evidenceSummary: "Peer signal was too weak.",
    peerSignalScore: 0.5,
  }),
  decision({
    decisionId: "decision-3",
    target: "BADROW",
    theme: null,
    strategyType: null,
    status: "malformed",
    outcome: "malformed",
    thesis: null,
    earningsDate: null,
    evidenceSummary: null,
    peerSignalScore: null,
    malformed: true,
    rawPayload: "{}",
  }),
];

describe("decision list view model", () => {
  it("normalizes invalid URL params to supported defaults", () => {
    const params = normalizeDecisionListParams(
      new URLSearchParams("q=%20%20&page=-4&pageSize=999"),
    );

    expect(params).toEqual({
      query: "",
      status: "",
      strategy: "",
      page: 1,
      pageSize: 25,
      bucket: "all",
      earnings: "all",
      watchlist: "",
    });
  });

  it("filters by search text, status, and strategy", () => {
    const view = buildDecisionListViewModel(decisions, {
      query: "weak",
      status: "rejected_with_reason",
      strategy: "bullish_earnings_readthrough",
      page: 1,
      pageSize: 25,
      bucket: "all",
      earnings: "all",
      watchlist: "",
    });

    expect(view.filteredCount).toBe(1);
    expect(view.pageItems.map((item) => item.target)).toEqual(["NVDA"]);
    expect(view.statusOptions).toEqual([
      "candidate_ready_for_analyst",
      "malformed",
      "rejected_with_reason",
    ]);
    expect(view.strategyOptions).toEqual(["bullish_earnings_readthrough"]);
  });

  it("paginates and clamps page numbers to the available range", () => {
    const paginatedDecisions = Array.from({ length: 11 }, (_, index) =>
      decision({
        decisionId: `decision-${index}`,
        target: `TARGET${index}`,
      }),
    );
    const view = buildDecisionListViewModel(paginatedDecisions, {
      query: "",
      status: "",
      strategy: "",
      page: 99,
      pageSize: 10,
      bucket: "all",
      earnings: "all",
      watchlist: "",
    });

    expect(view.page).toBe(2);
    expect(view.pageCount).toBe(2);
    expect(view.from).toBe(11);
    expect(view.to).toBe(11);
    expect(view.pageItems.map((item) => item.target)).toEqual(["TARGET10"]);
  });

  it("returns a filtered-empty view with stable counts", () => {
    const view = buildDecisionListViewModel(decisions, {
      query: "does-not-exist",
      status: "",
      strategy: "",
      page: 2,
      pageSize: 10,
      bucket: "all",
      earnings: "all",
      watchlist: "",
    });

    expect(view.totalCount).toBe(3);
    expect(view.filteredCount).toBe(0);
    expect(view.page).toBe(1);
    expect(view.pageItems).toEqual([]);
    expect(view.hasActiveFilters).toBe(true);
  });

  it("filters by quick bucket, earnings window, and read-only watchlist", () => {
    const view = buildDecisionListViewModel(
      [
        decision({
          decisionId: "decision-proposed",
          target: "NTNX",
          earningsDate: "2026-06-02",
          status: "candidate_ready_for_analyst",
        }),
        decision({
          decisionId: "decision-attention",
          target: "PSTG",
          earningsDate: "2026-06-15",
          attentionStatus: "needs_attention",
          attentionReasons: ["risk_rejection: daily_halt_active"],
        }),
        decision({
          decisionId: "decision-no-action",
          target: "NVDA",
          earningsDate: null,
          status: "no_trade",
          outcome: "no_trade",
        }),
      ],
      {
        query: "",
        status: "",
        strategy: "",
        page: 1,
        pageSize: 25,
        bucket: "proposed",
        earnings: "next_7d",
        watchlist: "theme:AI_STORAGE",
      },
      {
        activeRunDate: "2026-06-01",
        watchlists: [
          watchlist("theme:AI_STORAGE", [
            { ticker: "NTNX", theme: "AI_STORAGE" },
            { ticker: "PSTG", theme: "AI_STORAGE" },
          ]),
        ],
      },
    );

    expect(view.filteredCount).toBe(1);
    expect(view.pageItems.map((item) => item.target)).toEqual(["NTNX"]);
    expect(view.sidebar.quickFilters).toEqual([
      { key: "all", label: "All", count: 3, active: false },
      { key: "proposed", label: "Proposed", count: 1, active: true },
      { key: "needs_attention", label: "Needs Attention", count: 1, active: false },
      { key: "rejected", label: "Rejected", count: 0, active: false },
      { key: "no_action", label: "No Action", count: 1, active: false },
    ]);
    expect(view.sidebar.watchlists).toEqual([
      {
        watchlistId: "theme:AI_STORAGE",
        name: "AI STORAGE",
        count: 2,
        active: true,
      },
    ]);
  });

  it("treats malformed rows as needs attention for quick filters", () => {
    const view = buildDecisionListViewModel(
      decisions,
      {
        query: "",
        status: "",
        strategy: "",
        page: 1,
        pageSize: 25,
        bucket: "needs_attention",
        earnings: "all",
        watchlist: "",
      },
      { activeRunDate: "2026-06-01", watchlists: [] },
    );

    expect(view.filteredCount).toBe(1);
    expect(view.pageItems.map((item) => item.target)).toEqual(["BADROW"]);
  });
});

function watchlist(
  watchlistId: string,
  items: DecisionWatchlist["items"],
): DecisionWatchlist {
  return {
    watchlistId,
    name: "AI STORAGE",
    description: "AI data center demand",
    source: "strategy_universe",
    schemaVersion: 1,
    createdAt: "2026-06-01T14:00:00Z",
    updatedAt: "2026-06-01T14:00:00Z",
    items,
  };
}
