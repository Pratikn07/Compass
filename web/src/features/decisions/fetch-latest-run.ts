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

export type LatestRunSupabase = {
  from(table: "runs"): SupabaseFromQuery;
};

export async function fetchLatestRun(
  supabase: LatestRunSupabase,
): Promise<RunRow | null> {
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1);

  if (error) {
    throw new Error(`Failed to load latest run: ${error.message}`);
  }

  return ((data ?? []) as RunRow[])[0] ?? null;
}
