import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { backtestReportRow } from "./backtest-fixtures";
import { backtestLearningReportRowSchema } from "@/features/backtest/lib/backtest-report.schema";
import { useBacktestReport } from "@/features/backtest/hooks/use-backtest-report";
import { BacktestPage } from "@/features/backtest/components/backtest-page";

vi.mock("@/features/backtest/hooks/use-backtest-report", () => ({
  useBacktestReport: vi.fn(),
}));

vi.mock("@/features/backtest/components/equity-curve-chart", () => ({
  EquityCurveChart: ({ mode }: { mode: string }) => (
    <div data-testid="equity-curve-chart">equity mode: {mode}</div>
  ),
}));

vi.mock("@/features/backtest/components/drawdown-chart", () => ({
  DrawdownChart: ({ mode }: { mode: string }) => (
    <div data-testid="drawdown-chart">drawdown mode: {mode}</div>
  ),
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

  it("renders ready analytics with KPI parity, sidebar, and no trade actions", () => {
    mockUseBacktestReport.mockReturnValue(
      queryState({
        data: backtestLearningReportRowSchema.parse(backtestReportRow()),
      }),
    );

    render(<BacktestPage />);

    expect(screen.getByRole("heading", { name: "Backtest" })).toBeInTheDocument();
    expect(screen.getByText("Win rate")).toBeInTheDocument();
    expect(screen.getByText("Total return")).toBeInTheDocument();
    expect(screen.getByText("Max drawdown")).toBeInTheDocument();
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("Trades")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getByText("Buy-and-hold 0.13%")).toBeInTheDocument();
    expect(screen.getByText("Excess 0.32%")).toBeInTheDocument();
    expect(screen.getByText("Verified drawdown $25.00")).toBeInTheDocument();
    expect(screen.getByText("3 equity points")).toBeInTheDocument();
    expect(screen.getAllByText("NTNX").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("One setup used fallback pricing.")).toBeInTheDocument();
    expect(screen.getByTestId("equity-curve-chart")).toBeInTheDocument();
    expect(screen.getByTestId("drawdown-chart")).toBeInTheDocument();
    expect(screen.getByText("Advanced console")).toBeInTheDocument();
    expect(screen.getByText("Run scope")).toBeInTheDocument();
    expect(screen.getByText("Data quality")).toBeInTheDocument();
    expect(screen.getByText("Table controls")).toBeInTheDocument();
    expect(screen.getByText("Date range")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2026-03-31")).toBeInTheDocument();
    expect(screen.getByText("Benchmark status")).toBeInTheDocument();
    expect(screen.getByText("Metrics status")).toBeInTheDocument();
    expect(screen.getByText("5, 10, 25, 50 rows per page")).toBeInTheDocument();
    expect(screen.getByText("CSV from parsed report rows")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run backtest/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sell/i })).not.toBeInTheDocument();
  });

  it("toggles analytics between percent and dollar display", async () => {
    const user = userEvent.setup();
    mockUseBacktestReport.mockReturnValue(
      queryState({
        data: backtestLearningReportRowSchema.parse(backtestReportRow()),
      }),
    );

    render(<BacktestPage />);

    expect(screen.getByTestId("equity-curve-chart")).toHaveTextContent(
      "equity mode: percent",
    );
    expect(screen.getByTestId("drawdown-chart")).toHaveTextContent(
      "drawdown mode: percent",
    );

    await user.click(screen.getByRole("button", { name: "Show dollars" }));

    expect(screen.getByTestId("equity-curve-chart")).toHaveTextContent(
      "equity mode: dollars",
    );
    expect(screen.getByTestId("drawdown-chart")).toHaveTextContent(
      "drawdown mode: dollars",
    );
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
