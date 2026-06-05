import {
  type SystemHealthRow,
  systemHealthRowSchema,
} from "./decision-sidebar-schemas";

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

export type DecisionSystemHealthSupabase = {
  from(table: "system_health"): SupabaseFromQuery;
};

export async function fetchDecisionSystemHealth(
  supabase: DecisionSystemHealthSupabase,
  limit = 20,
): Promise<SystemHealthRow[]> {
  const { data, error } = await supabase
    .from("system_health")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to load system health: ${error.message}`);
  }

  return latestByComponent(systemHealthRowSchema.array().parse(data ?? []));
}

function latestByComponent(rows: SystemHealthRow[]): SystemHealthRow[] {
  const seen = new Set<SystemHealthRow["component"]>();
  const latest: SystemHealthRow[] = [];
  for (const row of rows) {
    if (seen.has(row.component)) {
      continue;
    }
    seen.add(row.component);
    latest.push(row);
  }
  return latest;
}
