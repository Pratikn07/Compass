import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionList } from "@/features/decisions/decision-list";
import { DecisionListClient } from "@/features/decisions/decision-list-client";
import type { DecisionListItem } from "@/features/decisions/decision-list.types";
import { useDecisionSystemHealth } from "@/features/decisions/use-decision-system-health";
import { useDecisionWatchlists } from "@/features/decisions/use-decision-watchlists";
import { useDecisions } from "@/features/decisions/use-decisions";
import { useLatestRun } from "@/features/decisions/use-latest-run";
import { useRunHistory } from "@/features/decisions/use-run-history";

const navigation = vi.hoisted(() => ({
  pathname: "/decisions",
  replace: vi.fn(),
  search: "",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({
    replace: navigation.replace,
  }),
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

vi.mock("@/features/decisions/use-latest-run", () => ({
  useLatestRun: vi.fn(),
}));

vi.mock("@/features/decisions/use-decisions", () => ({
  useDecisions: vi.fn(),
}));

vi.mock("@/features/decisions/use-run-history", () => ({
  useRunHistory: vi.fn(),
}));

vi.mock("@/features/decisions/use-decision-watchlists", () => ({
  useDecisionWatchlists: vi.fn(),
}));

vi.mock("@/features/decisions/use-decision-system-health", () => ({
  useDecisionSystemHealth: vi.fn(),
}));

const mockUseLatestRun = vi.mocked(useLatestRun);
const mockUseDecisions = vi.mocked(useDecisions);
const mockUseRunHistory = vi.mocked(useRunHistory);
const mockUseDecisionWatchlists = vi.mocked(useDecisionWatchlists);
const mockUseDecisionSystemHealth = vi.mocked(useDecisionSystemHealth);

describe("DecisionList", () => {
  it("renders a dense decision table with links to detail routes", () => {
    render(<DecisionList decisions={[decision()]} />);

    expect(screen.getByRole("columnheader", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Earnings" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Strategy" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NTNX" })).toHaveAttribute(
      "href",
      "/decisions/decision-1",
    );
    expect(screen.getByText("2026-06-02")).toBeInTheDocument();
    expect(screen.getByText("AI storage peers reported strong demand.")).toBeInTheDocument();
    expect(screen.getByText("candidate ready for analyst")).toBeInTheDocument();
    expect(screen.getByText("propose only")).toBeInTheDocument();
  });

  it("surfaces a malformed row loudly with a raw-detail disclosure", () => {
    render(
      <DecisionList
        decisions={[
          decision({
            decisionId: "decision-bad",
            target: "BADROW",
            theme: null,
            strategyType: null,
            status: "malformed",
            outcome: "malformed",
            mode: null,
            thesis: null,
            earningsDate: null,
            evidenceSummary: null,
            peerSignalScore: null,
            malformed: true,
            rawPayload: '{"thesis":42}',
          }),
        ]}
      />,
    );

    expect(screen.getAllByText("malformed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Show raw detail")).toBeInTheDocument();
    expect(screen.getByText(/"thesis":42/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "BADROW" })).not.toBeInTheDocument();
  });

  it("renders unknown for missing optional fields", () => {
    render(
      <DecisionList
        decisions={[
          decision({
            decisionId: "decision-2",
            target: "PSTG",
            theme: null,
            strategyType: null,
            status: "unknown",
            outcome: "pending",
            mode: null,
            thesis: null,
            earningsDate: null,
            evidenceSummary: null,
            peerSignalScore: null,
          }),
        ]}
      />,
    );

    expect(screen.getAllByText("unknown").length).toBeGreaterThanOrEqual(4);
  });
});

describe("DecisionListClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.pathname = "/decisions";
    navigation.search = "";
    mockUseRunHistory.mockReturnValue(runHistoryState());
    mockUseDecisionWatchlists.mockReturnValue(watchlistsState());
    mockUseDecisionSystemHealth.mockReturnValue(systemHealthState());
  });

  it("renders latest-run loading state", () => {
    mockUseLatestRun.mockReturnValue(latestRunState({ isPending: true }));
    mockUseDecisions.mockReturnValue(decisionsState());

    render(<DecisionListClient />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading latest run...");
  });

  it("renders latest-run errors", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ error: new Error("Failed to load latest run") }),
    );
    mockUseDecisions.mockReturnValue(decisionsState());

    render(<DecisionListClient />);

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load latest run");
  });

  it("renders no-run empty state", () => {
    mockUseLatestRun.mockReturnValue(latestRunState({ data: null }));
    mockUseDecisions.mockReturnValue(decisionsState());

    render(<DecisionListClient />);

    expect(screen.getByText("No run yet today.")).toBeInTheDocument();
  });

  it("renders decisions loading state after the latest run is known", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ isPending: true }));

    render(<DecisionListClient />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading decisions...");
  });

  it("renders decisions error state", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(
      decisionsState({ error: new Error("Failed to load decisions") }),
    );

    render(<DecisionListClient />);

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load decisions");
  });

  it("renders decisions empty state", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ data: [] }));

    render(<DecisionListClient />);

    expect(screen.getByText("No decisions for the selected run.")).toBeInTheDocument();
  });

  it("renders the populated active-run table", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ data: [decision()] }));

    render(<DecisionListClient />);

    expect(screen.getByText("Active run: scheduled:2026-06-01")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NTNX" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1-1 of 1 decisions")).toBeInTheDocument();
  });

  it("uses URL params for selected run, search, filters, and pagination", () => {
    navigation.search =
      "run=scheduled%3A2026-06-02&q=weak&status=rejected_with_reason&strategy=bullish_earnings_readthrough&page=2&pageSize=10";
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-03" } }),
    );
    mockUseRunHistory.mockReturnValue(
      runHistoryState({
        data: [run("scheduled:2026-06-03"), run("scheduled:2026-06-02")],
      }),
    );
    mockUseDecisions.mockReturnValue(
      decisionsState({
        data: [
          decision({ decisionId: "decision-strong", target: "NTNX" }),
          ...Array.from({ length: 11 }, (_, index) =>
            decision({
              decisionId: `decision-weak-${index}`,
              target: `NVDA${index}`,
              status: "rejected_with_reason",
              outcome: "no_trade",
              evidenceSummary: `Peer signal was too weak ${index}.`,
            }),
          ),
        ],
      }),
    );

    render(<DecisionListClient />);

    expect(mockUseDecisions).toHaveBeenCalledWith("scheduled:2026-06-02");
    expect(screen.getByLabelText("Search decisions")).toHaveValue("weak");
    expect(screen.getByLabelText("Filter by status")).toHaveValue(
      "rejected_with_reason",
    );
    expect(screen.getByLabelText("Filter by strategy")).toHaveValue(
      "bullish_earnings_readthrough",
    );
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByText("Showing 11-11 of 11 decisions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NVDA10" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "NTNX" })).not.toBeInTheDocument();
  });

  it("renders sidebar filters from URL-backed bucket, earnings, watchlist, runs, and health state", () => {
    navigation.search =
      "run=scheduled%3A2026-06-01&bucket=needs_attention&earnings=next_14d&watchlist=theme%3AAI_STORAGE";
    mockUseLatestRun.mockReturnValue(
      latestRunState({
        data: {
          run_id: "scheduled:2026-06-01",
          current_date: "2026-06-01",
          scheduled_date: "2026-06-01",
        },
      }),
    );
    mockUseRunHistory.mockReturnValue(
      runHistoryState({
        data: [
          run("scheduled:2026-06-01"),
          run("scheduled:2026-05-31", { status: "recorded" }),
        ],
      }),
    );
    mockUseDecisionWatchlists.mockReturnValue(
      watchlistsState({
        data: [
          {
            watchlistId: "theme:AI_STORAGE",
            name: "AI STORAGE",
            description: "AI data center demand",
            source: "strategy_universe",
            schemaVersion: 1,
            createdAt: "2026-06-01T14:00:00Z",
            updatedAt: "2026-06-01T14:00:00Z",
            items: [{ ticker: "NTNX", theme: "AI_STORAGE" }],
          },
        ],
      }),
    );
    mockUseDecisionSystemHealth.mockReturnValue(
      systemHealthState({
        data: [
          systemHealth("market_data", "healthy", "Provider reads completed."),
          systemHealth("pricing_engine", "degraded", "Option chain incomplete."),
          systemHealth("risk_engine", "unknown", "No risk records yet."),
        ],
      }),
    );
    mockUseDecisions.mockReturnValue(
      decisionsState({
        data: [
          decision({
            decisionId: "decision-attention",
            target: "NTNX",
            earningsDate: "2026-06-10",
            attentionStatus: "needs_attention",
            attentionReasons: ["risk_rejection: daily_halt_active"],
          }),
          decision({
            decisionId: "decision-other",
            target: "PSTG",
            earningsDate: "2026-06-20",
          }),
        ],
      }),
    );

    render(<DecisionListClient />);

    expect(screen.getByRole("button", { name: /Needs Attention 1/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Next 14d 1/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /AI STORAGE 1/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /scheduled:2026-05-31/ })).toBeInTheDocument();
    expect(screen.getByText("Market Data")).toBeInTheDocument();
    expect(screen.getByText("Provider reads completed.")).toBeInTheDocument();
    expect(screen.getByText("Pricing Engine")).toBeInTheDocument();
    expect(screen.getByText("Option chain incomplete.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: "NTNX" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "PSTG" })).not.toBeInTheDocument();
  });

  it("changes sidebar filters through URL params and resets pagination", () => {
    navigation.search = "run=scheduled%3A2026-06-01&page=3&pageSize=50";
    mockUseLatestRun.mockReturnValue(
      latestRunState({
        data: {
          run_id: "scheduled:2026-06-01",
          current_date: "2026-06-01",
          scheduled_date: "2026-06-01",
        },
      }),
    );
    mockUseDecisionWatchlists.mockReturnValue(
      watchlistsState({
        data: [
          {
            watchlistId: "theme:AI_STORAGE",
            name: "AI STORAGE",
            description: null,
            source: "strategy_universe",
            schemaVersion: 1,
            createdAt: "2026-06-01T14:00:00Z",
            updatedAt: "2026-06-01T14:00:00Z",
            items: [{ ticker: "NTNX", theme: "AI_STORAGE" }],
          },
        ],
      }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ data: [decision()] }));

    render(<DecisionListClient />);

    fireEvent.click(screen.getByRole("button", { name: /Needs Attention/ }));

    let url = lastReplacedUrl();
    expect(url.searchParams.get("bucket")).toBe("needs_attention");
    expect(url.searchParams.get("page")).toBeNull();
    expect(url.searchParams.get("pageSize")).toBe("50");

    fireEvent.click(screen.getByRole("button", { name: /AI STORAGE/ }));

    url = lastReplacedUrl();
    expect(url.searchParams.get("watchlist")).toBe("theme:AI_STORAGE");
    expect(url.searchParams.get("page")).toBeNull();
  });

  it("resets page to one when search or filters change", () => {
    navigation.search = "run=scheduled%3A2026-06-01&page=2&pageSize=50";
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ data: [decision()] }));

    render(<DecisionListClient />);

    fireEvent.change(screen.getByLabelText("Search decisions"), {
      target: { value: "NVDA" },
    });

    let url = lastReplacedUrl();
    expect(url.searchParams.get("run")).toBe("scheduled:2026-06-01");
    expect(url.searchParams.get("q")).toBe("NVDA");
    expect(url.searchParams.get("page")).toBeNull();
    expect(url.searchParams.get("pageSize")).toBe("50");

    fireEvent.change(screen.getByLabelText("Filter by status"), {
      target: { value: "candidate_ready_for_analyst" },
    });

    url = lastReplacedUrl();
    expect(url.searchParams.get("status")).toBe("candidate_ready_for_analyst");
    expect(url.searchParams.get("page")).toBeNull();
  });

  it("clears filters while preserving active run and page size", () => {
    navigation.search =
      "run=scheduled%3A2026-06-01&q=weak&status=rejected_with_reason&strategy=bullish_earnings_readthrough&page=2&pageSize=50";
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(
      decisionsState({
        data: [
          decision({
            target: "NVDA",
            status: "rejected_with_reason",
            outcome: "no_trade",
            evidenceSummary: "Peer signal was too weak.",
          }),
        ],
      }),
    );

    render(<DecisionListClient />);

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    const url = lastReplacedUrl();
    expect(url.searchParams.get("run")).toBe("scheduled:2026-06-01");
    expect(url.searchParams.get("pageSize")).toBe("50");
    expect(url.searchParams.get("q")).toBeNull();
    expect(url.searchParams.get("status")).toBeNull();
    expect(url.searchParams.get("strategy")).toBeNull();
    expect(url.searchParams.get("page")).toBeNull();
  });

  it("offers a clear action for empty filtered results", () => {
    navigation.search = "q=does-not-match";
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(decisionsState({ data: [decision()] }));

    render(<DecisionListClient />);

    expect(
      screen.getByText("No decisions match the current filters."),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Clear filters" }).length,
    ).toBeGreaterThanOrEqual(1);
  });
});

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

function run(runId: string, overrides: Record<string, unknown> = {}) {
  return {
    created_at: `${runId}:created`,
    current_date: "2026-06-01",
    payload: { record_count: 1 },
    run_id: runId,
    scheduled_date: null,
    status: "recorded",
    ...overrides,
  };
}

function systemHealth(
  component: "market_data" | "pricing_engine" | "risk_engine",
  status: "healthy" | "degraded" | "blocked" | "unknown",
  detail: string,
) {
  return {
    systemHealthId: `scheduled:2026-06-01:${component}`,
    component,
    status,
    detail,
    latencySeconds: component === "market_data" ? 3 : null,
    runId: "scheduled:2026-06-01",
    schemaVersion: 1,
    createdAt: "2026-06-01T14:30:00Z",
  };
}

function lastReplacedUrl(): URL {
  const call = navigation.replace.mock.calls.at(-1);
  expect(call).toBeDefined();
  return new URL(call?.[0] as string, "http://localhost");
}

function latestRunState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useLatestRun> {
  return ({
    data: undefined,
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useLatestRun>;
}

function decisionsState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useDecisions> {
  return ({
    data: undefined,
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useDecisions>;
}

function runHistoryState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useRunHistory> {
  return ({
    data: [],
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useRunHistory>;
}

function watchlistsState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useDecisionWatchlists> {
  return ({
    data: [],
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useDecisionWatchlists>;
}

function systemHealthState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useDecisionSystemHealth> {
  return ({
    data: [],
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useDecisionSystemHealth>;
}
