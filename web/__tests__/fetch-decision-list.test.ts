import { describe, expect, it } from "vitest";
import { fetchDecisions } from "@/features/decisions/fetch-decisions";
import { fetchLatestRun } from "@/features/decisions/fetch-latest-run";
import { fetchRunHistory } from "@/features/decisions/fetch-run-history";

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

describe("decision list fetchers", () => {
  it("fetchLatestRun queries runs newest first and returns the first row", async () => {
    const supabase = fakeSupabase({
      data: [{ run_id: "scheduled:2026-06-01" }],
      error: null,
    });

    const run = await fetchLatestRun(supabase);

    expect(run).toEqual({ run_id: "scheduled:2026-06-01" });
    expect(supabase.calls).toEqual([
      "from:runs",
      "select:*",
      "order:created_at:false",
      "limit:1",
    ]);
  });

  it("fetchLatestRun returns null when there are no runs", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await expect(fetchLatestRun(supabase)).resolves.toBeNull();
  });

  it("fetchRunHistory queries runs newest first with a bounded limit", async () => {
    const supabase = fakeSupabase({
      data: [{ run_id: "scheduled:2026-06-02" }, { run_id: "scheduled:2026-06-01" }],
      error: null,
    });

    const runs = await fetchRunHistory(supabase, 30);

    expect(runs).toHaveLength(2);
    expect(supabase.calls).toEqual([
      "from:runs",
      "select:*",
      "order:created_at:false",
      "limit:30",
    ]);
  });

  it("fetchDecisions queries decision_records for one run in decision order", async () => {
    const supabase = fakeSupabase({ data: [], error: null });

    await fetchDecisions(supabase, "scheduled:2026-06-01");

    expect(supabase.calls).toEqual([
      "from:decision_records",
      "select:*",
      "eq:run_id:scheduled:2026-06-01",
      "order:decision_index:true",
      "limit:500",
    ]);
  });

  it("throws readable Supabase errors", async () => {
    const supabase = fakeSupabase({
      data: null,
      error: { message: "permission denied for table decision_records" },
    });

    await expect(
      fetchDecisions(supabase, "scheduled:2026-06-01"),
    ).rejects.toThrow("permission denied for table decision_records");
  });
});
