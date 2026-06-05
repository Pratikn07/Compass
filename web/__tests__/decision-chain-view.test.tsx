import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DecisionChainClient } from "@/features/decisions/decision-chain-client";
import { DecisionChainView } from "@/features/decisions/decision-chain-view";
import { useDecisionChain } from "@/features/decisions/use-decision-chain";
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

vi.mock("@/features/decisions/use-decision-chain", () => ({
  useDecisionChain: vi.fn(),
}));

const mockUseDecisionChain = vi.mocked(useDecisionChain);

describe("DecisionChainView", () => {
  it("renders the decision header and ordered audit chain", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    expect(
      screen.getByRole("heading", { level: 1, name: "NTNX decision chain" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Theme: AI_STORAGE")).toBeInTheDocument();
    expect(screen.getByText("Decision: decision-1")).toBeInTheDocument();
    expect(screen.getByText("Run: scheduled:2026-06-01")).toBeInTheDocument();

    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual([
      "Strategy decision",
      "Analyst review",
      "Risk decision",
      "Position sizing",
      "Execution proposal",
      "Outcome",
    ]);
  });

  it("renders header status, outcome, and mode badges", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    const badges = screen.getByTestId("decision-chain-header-badges");
    expect(within(badges).getByText("Strategy status")).toBeInTheDocument();
    expect(within(badges).getByText("candidate ready for analyst")).toBeInTheDocument();
    expect(within(badges).getByText("Latest outcome")).toBeInTheDocument();
    expect(within(badges).getByText("pending")).toBeInTheDocument();
    expect(within(badges).getByText("Mode")).toBeInTheDocument();
    expect(within(badges).getByText("propose only")).toBeInTheDocument();
  });

  it("renders enriched strategy evidence without blocked trade fields", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    expect(screen.getByText("Trigger summary")).toBeInTheDocument();
    expect(screen.getByText("Peer read-through evidence")).toBeInTheDocument();
    expect(screen.getByText("Peer scores")).toBeInTheDocument();
    expect(screen.getByText("2026-06-03")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "PSTG" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "AI storage demand" })).toBeInTheDocument();
    expect(screen.getByText("Signal score")).toBeInTheDocument();
    expect(screen.queryByText(/edge bp/i)).not.toBeInTheDocument();
  });

  it("renders analyst conviction as analyst conviction, not confidence", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    expect(screen.getByText("Analyst conviction")).toBeInTheDocument();
    expect(screen.getByText("0.68")).toBeInTheDocument();
    expect(screen.queryByText(/^Confidence$/i)).not.toBeInTheDocument();
  });

  it("makes the risk card visually dominant with semantic status text", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    const riskCard = screen.getByTestId("risk-decision-card");
    expect(riskCard.className).toContain("border-primary");
    expect(
      within(riskCard).getByText("Risk gates passed for a propose-only defined-risk setup."),
    ).toBeInTheDocument();
    expect(within(riskCard).getAllByText("risk passed")[0]).toBeInTheDocument();
    expect(within(riskCard).getByText("Broker execution allowed: No")).toBeInTheDocument();
  });

  it("labels analyst and sizing stages as advisory and read-only", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    expect(
      screen.getByText("Advisory only, not authorization."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Read-only. Quantity was code-decided."),
    ).toBeInTheDocument();
    expect(screen.getByText("Account equity")).toBeInTheDocument();
    expect(screen.getByText("Unit max loss")).toBeInTheDocument();
    expect(screen.getByText("Claude present")).toBeInTheDocument();
    expect(screen.getByText("Claude sizing override attempted")).toBeInTheDocument();
  });

  it("renders only available execution proposal leg fields", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    const executionCard = screen.getByTestId("execution-proposal-card");
    expect(within(executionCard).getByText("Available proposal legs")).toBeInTheDocument();
    expect(within(executionCard).getByRole("columnheader", { name: "Side" })).toBeInTheDocument();
    expect(within(executionCard).getByRole("columnheader", { name: "Symbol" })).toBeInTheDocument();
    expect(within(executionCard).getByRole("columnheader", { name: "Quantity" })).toBeInTheDocument();
    expect(within(executionCard).getByRole("cell", { name: "long" })).toBeInTheDocument();
    expect(
      within(executionCard).getByRole("cell", { name: "NTNX 2026-06-19 55C" }),
    ).toBeInTheDocument();
    expect(within(executionCard).getByRole("cell", { name: "4" })).toBeInTheDocument();
    expect(within(executionCard).queryByRole("columnheader", { name: "Strike" })).not.toBeInTheDocument();
    expect(within(executionCard).queryByRole("columnheader", { name: "IV" })).not.toBeInTheDocument();
    expect(within(executionCard).queryByRole("columnheader", { name: "Price" })).not.toBeInTheDocument();
    expect(within(executionCard).queryByRole("columnheader", { name: "Credit" })).not.toBeInTheDocument();
  });

  it("renders parse errors with raw JSON diagnostic detail", () => {
    const malformed = parseDecisionChain([
      journalRow({
        payload: { status: "risk_passed" },
        record_type: "risk_decision",
      }),
    ]);

    render(<DecisionChainView decisionId="decision-1" records={malformed} />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Malformed risk_decision payload",
    );
    expect(screen.getByText("Raw diagnostic detail")).toBeInTheDocument();
    expect(screen.getByText(/"status": "risk_passed"/)).toBeInTheDocument();
  });

  it("keeps citations in keyboard-accessible details with links", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    const detailsSummary = screen.getAllByText("Source citations")[0];
    expect(detailsSummary.closest("details")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Peer earnings release" })[0],
    ).toHaveAttribute("href", "https://example.test/peer-earnings");
    expect(screen.getAllByText("Evidence confidence: high")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Endpoint: /stock/earnings")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Source id: PSTG:2026-Q1")[0]).toBeInTheDocument();
    expect(
      screen.getAllByText("Peer earnings release cited stronger enterprise storage demand.")[0],
    ).toBeInTheDocument();
  });

  it("does not render interactive trading controls", () => {
    render(<DecisionChainView decisionId="decision-1" records={chainRecords()} />);

    expect(
      screen.queryByRole("button", { name: /execute|authorize|submit|trade/i }),
    ).not.toBeInTheDocument();
  });
});

describe("DecisionChainClient", () => {
  it("renders loading, error, empty, and populated states", () => {
    mockUseDecisionChain.mockReturnValue(chainState({ isPending: true }));
    const { rerender } = render(<DecisionChainClient decisionId="decision-1" />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading decision chain...",
    );

    mockUseDecisionChain.mockReturnValue(
      chainState({ error: new Error("Failed to load decision chain") }),
    );
    rerender(<DecisionChainClient decisionId="decision-1" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Failed to load decision chain",
    );

    mockUseDecisionChain.mockReturnValue(chainState({ data: [] }));
    rerender(<DecisionChainClient decisionId="decision-1" />);
    expect(
      screen.getByText("No journal records for this decision."),
    ).toBeInTheDocument();

    mockUseDecisionChain.mockReturnValue(chainState({ data: chainRecords() }));
    rerender(<DecisionChainClient decisionId="decision-1" />);
    expect(
      screen.getByRole("heading", { level: 1, name: "NTNX decision chain" }),
    ).toBeInTheDocument();
  });
});

function chainRecords() {
  return parseDecisionChain([
    journalRow({
      created_at: "2026-06-01T14:30:00Z",
      journal_record_id: "journal-strategy",
      payload: strategyPayload,
      record_type: "strategy_decision",
    }),
    journalRow({
      created_at: "2026-06-01T14:33:00Z",
      journal_record_id: "journal-analyst",
      payload: analystPayload,
      record_type: "analyst_review",
    }),
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
      created_at: "2026-06-01T14:45:00Z",
      journal_record_id: "journal-execution",
      payload: executionPayload,
      record_type: "execution_proposal",
    }),
    journalRow({
      created_at: "2026-06-01T14:50:00Z",
      journal_record_id: "journal-outcome",
      payload: outcomePayload,
      record_type: "trade_outcome",
    }),
  ]);
}

function chainState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useDecisionChain> {
  return ({
    data: undefined,
    error: null,
    isPending: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useDecisionChain>;
}
