import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SetupResultsTable } from "@/features/backtest/components/setup-results-table";

describe("SetupResultsTable", () => {
  it("renders mockup-parity columns and percent/dollar display modes", () => {
    render(<SetupResultsTable mode="percent" rows={buildRows(2)} />);

    expect(screen.getByRole("columnheader", { name: "Target" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Strategy" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Entry" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Exit" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Holding days" })).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Realized P&L %" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(screen.getByText("20.00%")).toBeInTheDocument();

    render(<SetupResultsTable mode="dollars" rows={buildRows(1)} />);

    expect(screen.getAllByRole("columnheader", { name: "Realized P&L $" })[0]).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
  });

  it("sorts, paginates, and exposes a CSV export", async () => {
    const user = userEvent.setup();
    render(<SetupResultsTable mode="dollars" rows={buildRows(12)} />);

    expect(screen.getByText("Showing 1-10 of 12 setups")).toBeInTheDocument();
    expect(screen.getByText("TICK01")).toBeInTheDocument();
    expect(screen.queryByText("TICK12")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next page" }));

    expect(screen.getByText("Showing 11-12 of 12 setups")).toBeInTheDocument();
    expect(screen.getByText("TICK12")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Rows per page"), "5");

    expect(screen.getByText("Showing 1-5 of 12 setups")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sort by realized P&L" }));

    const table = screen.getByRole("table", {
      name: "Setup-level backtest outcomes",
    });
    const firstDataRow = within(table).getAllByRole("row")[1];
    expect(within(firstDataRow).getByText("TICK12")).toBeInTheDocument();

    const exportLink = screen.getByRole("link", { name: "Export CSV" });
    expect(exportLink).toHaveAttribute("download", "backtest-results.csv");
    expect(decodeURIComponent(exportLink.getAttribute("href") ?? "")).toContain(
      "Target,Theme,Strategy,Entry,Exit,Holding days,Realized P&L %,Realized P&L $,Outcome",
    );
  });
});

function buildRows(count: number) {
  return Array.from({ length: count }, (_, index) => {
    const ordinal = index + 1;
    const padded = String(ordinal).padStart(2, "0");
    return {
      benchmarkReturn: `${ordinal.toFixed(2)}%`,
      entryDate: `2026-02-${padded}`,
      exitDate: `2026-02-${String(ordinal + 1).padStart(2, "0")}`,
      expression: "CALL OPTION",
      holdingDays: 1,
      netPnl: `$${(ordinal * 10).toFixed(2)}`,
      netPnlDollarLabel: `$${(ordinal * 10).toFixed(2)}`,
      netPnlPercentLabel: `${(ordinal * 20).toFixed(2)}%`,
      netPnlValue: ordinal * 10,
      outcome: ordinal % 2 === 0 ? "loss" : "win",
      setupId: `setup-${padded}`,
      status: "candidate ready for analyst",
      target: `TICK${padded}`,
      theme: "AI_STORAGE",
      warningCount: 0,
    };
  });
}
