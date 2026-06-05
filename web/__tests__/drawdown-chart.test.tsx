import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { DrawdownChart } from "@/features/backtest/components/drawdown-chart";

vi.mock("recharts", () => ({
  Area: ({ dataKey }: { dataKey: string }) => (
    <div data-testid="drawdown-area" data-key={dataKey} />
  ),
  AreaChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="drawdown-area-chart">{children}</div>
  ),
  CartesianGrid: () => <div data-testid="drawdown-grid" />,
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="drawdown-responsive-container">{children}</div>
  ),
  Tooltip: () => <div data-testid="drawdown-tooltip" />,
  XAxis: () => <div data-testid="drawdown-x-axis" />,
  YAxis: () => <div data-testid="drawdown-y-axis" />,
}));

describe("DrawdownChart", () => {
  it("renders percent drawdown as an accessible chart", () => {
    render(<DrawdownChart data={drawdownData()} mode="percent" />);

    expect(
      screen.getByRole("img", {
        name: "Drawdown area chart derived from strategy equity",
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("drawdown-area")).toHaveAttribute(
      "data-key",
      "drawdownPct",
    );
  });

  it("renders dollar drawdown when dollar mode is selected", () => {
    render(<DrawdownChart data={drawdownData()} mode="dollars" />);

    expect(screen.getByTestId("drawdown-area")).toHaveAttribute(
      "data-key",
      "drawdownDollars",
    );
  });

  it("renders an honest empty state without enough observations", () => {
    render(<DrawdownChart data={[drawdownData()[0]]} mode="percent" />);

    expect(
      screen.getByText("No evaluable drawdown observations."),
    ).toBeInTheDocument();
  });
});

function drawdownData() {
  return [
    {
      date: "2026-01-01",
      drawdownDollars: 0,
      drawdownPct: 0,
      label: "Start",
    },
    {
      date: "2026-02-06",
      drawdownDollars: 25,
      drawdownPct: 0.2483,
      label: "CRM",
    },
  ];
}
