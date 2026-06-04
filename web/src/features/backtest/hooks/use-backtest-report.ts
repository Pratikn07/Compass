"use client";

import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import type { Database } from "@/lib/supabase/database.types";
import {
  BACKTEST_REPORT_TYPE,
  backtestLearningReportRowSchema,
  type BacktestLearningReport,
} from "@/features/backtest/lib/backtest-report.schema";

export type LearningReportRow =
  Database["prescient_storage"]["Tables"]["learning_reports"]["Row"];

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

export type BacktestReportSupabase = {
  from(table: "learning_reports"): SupabaseFromQuery;
};

const createBacktestReportClient = createClient as unknown as () => BacktestReportSupabase;

export async function fetchLatestBacktestReport(
  supabase?: BacktestReportSupabase,
): Promise<BacktestLearningReport | null> {
  const client = supabase ?? createBacktestReportClient();
  const { data, error } = await client
    .from("learning_reports")
    .select("*")
    .eq("report_type", BACKTEST_REPORT_TYPE)
    .order("report_date", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(1);

  if (error) {
    throw new Error(`Failed to load latest backtest report: ${error.message}`);
  }

  const rows = (data ?? []) as LearningReportRow[];
  const row = rows[0];
  if (!row) {
    return null;
  }

  return backtestLearningReportRowSchema.parse(row);
}

export function useBacktestReport() {
  return useQuery({
    queryKey: ["backtest", "latest-report"],
    queryFn: () => fetchLatestBacktestReport(),
    refetchOnWindowFocus: true,
  });
}
