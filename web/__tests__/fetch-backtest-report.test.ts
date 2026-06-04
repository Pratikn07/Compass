import { describe, expect, it } from "vitest";
import { backtestReportRow } from "./backtest-fixtures";
import { fetchLatestBacktestReport } from "@/features/backtest/hooks/use-backtest-report";

type FakeResult = { data: unknown; error: { message: string } | null };

function fakeSupabase(result: FakeResult) {
  const calls: string[] = [];
  return {
    calls,
    from(table: string) {
      calls.push(`from:${table}`);
      return {
        select(columns: string) {
          calls.push(`select:${columns}`);
          return this;
        },
        eq(column: string, value: string) {
          calls.push(`eq:${column}:${value}`);
          return this;
        },
        order(column: string, options: { ascending: boolean }) {
          calls.push(`order:${column}:${options.ascending}`);
          return this;
        },
        limit(value: number) {
          calls.push(`limit:${value}`);
          return Promise.resolve(result);
        },
      };
    },
  };
}

describe("fetchLatestBacktestReport", () => {
  it("queries the latest persisted backtest report and parses it", async () => {
    const supabase = fakeSupabase({ data: [backtestReportRow()], error: null });

    const report = await fetchLatestBacktestReport(supabase);

    expect(report?.learningReportId).toBe("backtest:r9-4-fixture");
    expect(report?.payload.summary.beatsBuyAndHold).toBe(true);
    expect(supabase.calls).toEqual([
      "from:learning_reports",
      "select:*",
      "eq:report_type:backtest",
      "order:report_date:false",
      "order:created_at:false",
      "limit:1",
    ]);
  });

  it("returns null when no backtest report has been persisted", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await expect(fetchLatestBacktestReport(supabase)).resolves.toBeNull();
  });

  it("throws provider errors", async () => {
    const supabase = fakeSupabase({
      data: null,
      error: { message: "permission denied for table learning_reports" },
    });

    await expect(fetchLatestBacktestReport(supabase)).rejects.toThrow(
      "permission denied for table learning_reports",
    );
  });

  it("throws parse errors for malformed stored payloads", async () => {
    const supabase = fakeSupabase({
      data: [backtestReportRow({ payload: { run_id: "bad" } })],
      error: null,
    });

    await expect(fetchLatestBacktestReport(supabase)).rejects.toThrow();
  });
});
