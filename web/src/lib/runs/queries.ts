import { createClient } from "@/lib/supabase/client";
import {
  dailyHaltFromRiskRecords,
  providerErrorRowSchema,
  runRowSchema,
  storageAuditRowSchema,
} from "@/lib/runs/schemas";

export async function fetchLatestRuns(limit = 10) {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to load runs: ${error.message}`);
  }
  return runRowSchema.array().parse(data ?? []);
}

export async function fetchRecentProviderErrors(limit = 20) {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("provider_errors")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to load provider errors: ${error.message}`);
  }
  return providerErrorRowSchema.array().parse(data ?? []);
}

export async function fetchRecentStorageAudit(limit = 10) {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("storage_write_audit")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to load storage audit: ${error.message}`);
  }
  return storageAuditRowSchema.array().parse(data ?? []);
}

export async function fetchDailyHaltStatus() {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("journal_records")
    .select("journal_record_id, record_type, payload, created_at")
    .eq("record_type", "risk_decision")
    .order("created_at", { ascending: false })
    .limit(50);

  if (error) {
    throw new Error(`Failed to load risk records: ${error.message}`);
  }
  return dailyHaltFromRiskRecords(data ?? []);
}
