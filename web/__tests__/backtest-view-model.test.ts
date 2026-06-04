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
    expect(model.equityCurve.map((point) => point.strategyEquity)).toEqual([
      10000, 10070, 10045,
    ]);
    expect(model.outcomeDistribution.map((point) => point.count)).toEqual([
      1, 1, 0, 0,
    ]);
    expect(model.setupRows[0].netPnl).toBe("$70.00");
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
