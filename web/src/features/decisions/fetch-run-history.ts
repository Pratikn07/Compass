import type { RunRow } from "./decision-list.types";

type SupabaseReadResult = {
  data: unknown;
  error: { message: string } | null;
};

type SupabaseReadQuery = {
  order(column: string, options: { ascending: boolean }): SupabaseReadQuery;
  limit(value: number): PromiseLike<SupabaseReadResult>;
};

type SupabaseFromQuery = {
  select(columns: string): SupabaseReadQuery;
};

export type RunHistorySupabase = {
  from(table: "runs"): SupabaseFromQuery;
};

/** Recent runs, newest first, for the decision run/date switcher. */
export async function fetchRunHistory(
  supabase: RunHistorySupabase,
  limit = 30,
): Promise<RunRow[]> {
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to load run history: ${error.message}`);
  }

  return (data ?? []) as RunRow[];
}
