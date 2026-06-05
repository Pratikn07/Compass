import { describe, expect, it } from "vitest";
import { backtestPayload, backtestReportRow } from "./backtest-fixtures";
import { backtestLearningReportRowSchema } from "@/features/backtest/lib/backtest-report.schema";
import { buildBacktestViewModel } from "@/features/backtest/lib/backtest-view-model";

describe("backtest view model", () => {
  it("formats KPIs and chart data from a parsed report", () => {
    const report = backtestLearningReportRowSchema.parse(backtestReportRow());
    const model = buildBacktestViewModel(report);

    expect(model.metrics.find((metric) => metric.id === "winRate")?.value).toBe(
      "50.0%",
    );
    expect(model.metrics.find((metric) => metric.id === "totalReturn")?.value).toBe(
      "0.45%",
    );
    expect(model.returnComparison).toEqual([
      { label: "Strategy", value: 0.45 },
      { label: "Buy and hold", value: 0.13 },
      { label: "Excess", value: 0.32 },
    ]);
    expect(model.metrics.map((metric) => metric.label)).toEqual([
      "Win rate",
      "Total return",
      "Max drawdown",
      "Sharpe",
      "Trades",
    ]);
    expect(model.metrics.find((metric) => metric.id === "tradeCount")?.value).toBe(
      "2",
    );
    expect(
      model.metrics.find((metric) => metric.id === "totalReturn")?.comparison,
    ).toBe("Buy-and-hold 0.13%");
    expect(
      model.metrics.find((metric) => metric.id === "totalReturn")?.verification,
    ).toBe("Excess 0.32%");
    expect(
      model.metrics.find((metric) => metric.id === "maxDrawdown")?.comparison,
    ).toBe("Verified drawdown $25.00");
    expect(
      model.metrics.find((metric) => metric.id === "maxDrawdown")?.verification,
    ).toBe("3 equity points");
    expect(
      model.metrics.every((metric) => metric.sparkline.length === 3),
    ).toBe(true);
    expect(model.equityCurve.map((point) => point.strategyEquity)).toEqual([
      10000, 10070, 10045,
    ]);
    expect(model.equityCurve.map((point) => point.strategyReturnPct)).toEqual([
      0, 0.7, 0.45,
    ]);
    expect(model.drawdownCurve).toEqual([
      {
        date: "2026-01-01",
        drawdownDollars: 0,
        drawdownPct: 0,
        label: "Start",
      },
      {
        date: "2026-02-02",
        drawdownDollars: 0,
        drawdownPct: 0,
        label: "NTNX",
      },
      {
        date: "2026-02-06",
        drawdownDollars: 25,
        drawdownPct: 0.2483,
        label: "CRM",
      },
    ]);
    expect(model.outcomeDistribution.map((point) => point.count)).toEqual([
      1, 1, 0, 0,
    ]);
    expect(model.setupRows[0].netPnl).toBe("$70.00");
    expect(model.setupRows[0]).toMatchObject({
      holdingDays: 1,
      netPnlDollarLabel: "$70.00",
      netPnlPercentLabel: "58.33%",
      netPnlValue: 70,
    });
    expect(model.console).toMatchObject({
      benchmarkStatus: "evaluable",
      dateRange: "2026-01-01 - 2026-03-31",
      evaluationHorizon: "1 day",
      metricsStatus: "evaluable",
      strategyType: "bullish earnings readthrough",
    });
    expect(model.console.runScope.map((item) => item.label)).toEqual([
      "Date range",
      "Theme",
      "Strategy",
      "Evaluation horizon",
      "Starting equity",
    ]);
    expect(model.console.dataQuality.map((item) => item.label)).toEqual([
      "Benchmark status",
      "Metrics status",
      "Excluded observations",
      "Warnings",
    ]);
    expect(model.console.tableControls).toEqual([
      { label: "Sorting", value: "Target, theme, dates, holding days, realized P&L" },
      { label: "Pagination", value: "5, 10, 25, 50 rows per page" },
      { label: "Export", value: "CSV from parsed report rows" },
    ]);
  });

  it("uses honest unavailable labels for non-evaluable metrics", () => {
    const report = backtestLearningReportRowSchema.parse(
      backtestReportRow({
        payload: backtestPayload({
          summary: {
            ...backtestPayload().summary,
            win_rate: null,
            sharpe_ratio: null,
            total_return_pct: null,
            buy_hold_total_return_pct: null,
            excess_return_pct: null,
            beats_buy_and_hold: null,
            metrics_status: "not_evaluable",
          },
        }),
      }),
    );

    const model = buildBacktestViewModel(report);

    expect(model.metrics.find((metric) => metric.id === "winRate")?.value).toBe(
      "Unavailable",
    );
    expect(model.metrics.find((metric) => metric.id === "sharpe")?.tone).toBe(
      "muted",
    );
  });
});
