import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionList } from "@/features/decisions/decision-list";
import { DecisionListClient } from "@/features/decisions/decision-list-client";
import { useDecisions } from "@/features/decisions/use-decisions";
import { useLatestRun } from "@/features/decisions/use-latest-run";
import { useRunHistory } from "@/features/decisions/use-run-history";

vi.mock("@/features/decisions/use-latest-run", () => ({
  useLatestRun: vi.fn(),
}));

vi.mock("@/features/decisions/use-decisions", () => ({
  useDecisions: vi.fn(),
}));

vi.mock("@/features/decisions/use-run-history", () => ({
  useRunHistory: vi.fn(),
}));

const mockUseLatestRun = vi.mocked(useLatestRun);
const mockUseDecisions = vi.mocked(useDecisions);
const mockUseRunHistory = vi.mocked(useRunHistory);

describe("DecisionList", () => {
  it("renders a dense decision table with links to detail routes", () => {
    render(
      <DecisionList
        decisions={[
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
        ]}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Strategy" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Mode" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NTNX" })).toHaveAttribute(
      "href",
      "/decisions/decision-1",
    );
    expect(screen.getByText("candidate ready for analyst")).toBeInTheDocument();
    expect(screen.getByText("propose only")).toBeInTheDocument();
  });

  it("surfaces a malformed row loudly with a raw-detail disclosure", () => {
    render(
      <DecisionList
        decisions={[
          {
            decisionId: "decision-bad",
            runId: "scheduled:2026-06-01",
            decisionIndex: 0,
            tradingDate: "2026-06-01",
            target: "BADROW",
            theme: null,
            strategyType: null,
            status: "malformed",
            outcome: "malformed",
            mode: null,
            thesis: null,
            malformed: true,
            rawPayload: '{"thesis":42}',
          },
        ]}
      />,
    );

    expect(screen.getAllByText("malformed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Show raw detail")).toBeInTheDocument();
    expect(screen.getByText(/"thesis":42/)).toBeInTheDocument();
  });

  it("renders unknown for missing optional fields", () => {
    render(
      <DecisionList
        decisions={[
          {
            decisionId: "decision-2",
            runId: "scheduled:2026-06-01",
            decisionIndex: null,
            tradingDate: "2026-06-01",
            target: "PSTG",
            theme: null,
            strategyType: null,
            status: "unknown",
            outcome: "pending",
            mode: null,
            thesis: null,
            malformed: false,
            rawPayload: null,
          },
        ]}
      />,
    );

    expect(screen.getAllByText("unknown").length).toBeGreaterThanOrEqual(2);
  });
});

describe("DecisionListClient", () => {
  beforeEach(() => {
    mockUseRunHistory.mockReturnValue(runHistoryState());
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

    expect(screen.getByText("No decisions for the latest run.")).toBeInTheDocument();
  });

  it("renders the populated latest-run table", () => {
    mockUseLatestRun.mockReturnValue(
      latestRunState({ data: { run_id: "scheduled:2026-06-01" } }),
    );
    mockUseDecisions.mockReturnValue(
      decisionsState({
        data: [
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
        ],
      }),
    );

    render(<DecisionListClient />);

    expect(screen.getByText("Latest run: scheduled:2026-06-01")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "NTNX" })).toBeInTheDocument();
  });
});

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
