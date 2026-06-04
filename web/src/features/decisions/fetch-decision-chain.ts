import type { DecisionChainRecord, JournalRecordRow } from "./decision-chain.types";
import { parseDecisionChain } from "./parse-decision-chain";

type SupabaseReadResult = {
  data: unknown;
  error: { message: string } | null;
};

type SupabaseReadQuery = {
  eq(column: string, value: string): SupabaseReadQuery;
  order(column: string, options: { ascending: boolean }): PromiseLike<SupabaseReadResult>;
};

type SupabaseFromQuery = {
  select(columns: string): SupabaseReadQuery;
};

export type DecisionChainSupabase = {
  from(table: "journal_records"): SupabaseFromQuery;
};

export async function fetchDecisionChain(
  supabase: DecisionChainSupabase,
  decisionId: string,
): Promise<DecisionChainRecord[]> {
  const { data, error } = await supabase
    .from("journal_records")
    .select("*")
    .eq("decision_id", decisionId)
    .order("created_at", { ascending: true });

  if (error) {
    throw new Error(`Failed to load decision chain: ${error.message}`);
  }

  return parseDecisionChain((data ?? []) as JournalRecordRow[]);
}
