import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { backtestReportRow } from "./backtest-fixtures";
import { backtestLearningReportRowSchema } from "@/features/backtest/lib/backtest-report.schema";
import { useBacktestReport } from "@/features/backtest/hooks/use-backtest-report";
import { BacktestPage } from "@/features/backtest/components/backtest-page";

vi.mock("@/features/backtest/hooks/use-backtest-report", () => ({
  useBacktestReport: vi.fn(),
}));

vi.mock("@/features/backtest/components/equity-curve-chart", () => ({
  EquityCurveChart: () => <div data-testid="equity-curve-chart" />,
}));

vi.mock("@/features/backtest/components/return-comparison-chart", () => ({
  ReturnComparisonChart: () => <div data-testid="return-comparison-chart" />,
}));

vi.mock("@/features/backtest/components/outcome-distribution-chart", () => ({
  OutcomeDistributionChart: () => <div data-testid="outcome-distribution-chart" />,
}));

const mockUseBacktestReport = vi.mocked(useBacktestReport);

describe("BacktestPage", () => {
  it("renders loading state", () => {
    mockUseBacktestReport.mockReturnValue(queryState({ isPending: true }));

    render(<BacktestPage />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading backtest analytics...",
    );
  });

  it("renders provider and parse errors loudly", () => {
    mockUseBacktestReport.mockReturnValue(
      queryState({ error: new Error("Malformed backtest report payload") }),
    );

    render(<BacktestPage />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to load backtest analytics",
    );
    expect(screen.getByText("Raw diagnostic detail")).toBeInTheDocument();
  });

  it("renders honest empty state when no report exists", () => {
    mockUseBacktestReport.mockReturnValue(queryState({ data: null }));

    render(<BacktestPage />);

    expect(
      screen.getByText("No persisted backtest report is available yet."),
    ).toBeInTheDocument();
  });

  it("renders ready analytics without trade actions", () => {
    mockUseBacktestReport.mockReturnValue(
      queryState({
        data: backtestLearningReportRowSchema.parse(backtestReportRow()),
      }),
    );

    render(<BacktestPage />);

    expect(screen.getByRole("heading", { name: "Backtest" })).toBeInTheDocument();
    expect(screen.getByText("Win rate")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getAllByText("NTNX").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("One setup used fallback pricing.")).toBeInTheDocument();
    expect(screen.getByTestId("equity-curve-chart")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run backtest/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sell/i })).not.toBeInTheDocument();
  });
});

function queryState(
  overrides: Record<string, unknown> = {},
): ReturnType<typeof useBacktestReport> {
  return ({
    data: undefined,
    error: null,
    isPending: false,
    isLoading: false,
    ...overrides,
  } as unknown) as ReturnType<typeof useBacktestReport>;
}
