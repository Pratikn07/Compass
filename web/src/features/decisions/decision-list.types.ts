import type { Database } from "@/lib/supabase/database.types";

export type RunRow = Database["prescient_storage"]["Tables"]["runs"]["Row"];
export type DecisionRecordRow =
  Database["prescient_storage"]["Tables"]["decision_records"]["Row"];

export type DecisionListItem = {
  decisionId: string;
  runId: string;
  decisionIndex: number | null;
  tradingDate: string;
  target: string;
  theme: string | null;
  strategyType: string | null;
  status: string;
  outcome: string;
  mode: string | null;
  thesis: string | null;
  /** True when the row's payload failed schema validation. */
  malformed: boolean;
  /** Raw payload JSON, retained only for malformed rows so the issue is visible. */
  rawPayload: string | null;
};

export type BadgeVariant = "muted" | "success" | "danger" | "warning";
