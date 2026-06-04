import { describe, expect, it } from "vitest";
import { backtestReportRow } from "./backtest-fixtures";
import {
  BACKTEST_REPORT_TYPE,
  backtestLearningReportRowSchema,
} from "@/features/backtest/lib/backtest-report.schema";

describe("backtest report schema", () => {
  it("parses persisted backtest report rows", () => {
    const parsed = backtestLearningReportRowSchema.parse(backtestReportRow());

    expect(parsed.reportType).toBe(BACKTEST_REPORT_TYPE);
    expect(parsed.payload.runId).toBe("r9-4-fixture");
    expect(parsed.payload.summary.winRate).toBe(0.5);
    expect(parsed.payload.setups[0].tradePnl?.outcome).toBe("win");
  });

  it("rejects non-backtest learning report rows", () => {
    expect(() =>
      backtestLearningReportRowSchema.parse(
        backtestReportRow({ report_type: "learning" }),
      ),
    ).toThrow();
  });

  it("throws for malformed backtest payloads", () => {
    expect(() =>
      backtestLearningReportRowSchema.parse(
        backtestReportRow({ payload: { run_id: "bad", setups: [] } }),
      ),
    ).toThrow();
  });
});
