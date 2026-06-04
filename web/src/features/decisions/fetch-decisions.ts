import type { DecisionListItem, DecisionRecordRow } from "./decision-list.types";
import { parseDecisionList } from "./parse-decision-list";

type SupabaseReadResult = {
  data: unknown;
  error: { message: string } | null;
};

type SupabaseReadQuery = {
  eq(column: string, value: string): SupabaseReadQuery;
  order(column: string, options: { ascending: boolean }): SupabaseReadQuery;
  limit(value: number): PromiseLike<SupabaseReadResult>;
};

type SupabaseFromQuery = {
  select(columns: string): SupabaseReadQuery;
};

export type DecisionsSupabase = {
  from(table: "decision_records"): SupabaseFromQuery;
};

export async function fetchDecisions(
  supabase: DecisionsSupabase,
  runId: string,
): Promise<DecisionListItem[]> {
  const { data, error } = await supabase
    .from("decision_records")
    .select("*")
    .eq("run_id", runId)
    .order("decision_index", { ascending: true })
    .limit(500);

  if (error) {
    throw new Error(`Failed to load decisions: ${error.message}`);
  }

  return parseDecisionList((data ?? []) as DecisionRecordRow[]);
}
