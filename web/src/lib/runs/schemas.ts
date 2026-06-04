import { z } from "zod";

const payloadSchema = z.unknown().transform((value): Record<string, unknown> => {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
});

export const runRowSchema = z
  .object({
    run_id: z.string(),
    trigger_type: z.string().nullable(),
    scheduled_date: z.string().nullable(),
    current_date: z.string().nullable(),
    window_start: z.string().nullable(),
    window_end: z.string().nullable(),
    status: z.string().nullable(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    runId: value.run_id,
    triggerType: value.trigger_type,
    scheduledDate: value.scheduled_date,
    currentDate: value.current_date,
    windowStart: value.window_start,
    windowEnd: value.window_end,
    status: value.status ?? "unknown",
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export const providerErrorRowSchema = z
  .object({
    provider_error_id: z.string(),
    provider: z.string(),
    error_type: z.string(),
    run_id: z.string().nullable(),
    target: z.string().nullable(),
    source: z.string().nullable(),
    message: z.string(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    providerErrorId: value.provider_error_id,
    provider: value.provider,
    errorType: value.error_type,
    runId: value.run_id,
    target: value.target,
    source: value.source,
    message: value.message,
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export const storageAuditRowSchema = z
  .object({
    storage_write_audit_id: z.string(),
    provider: z.string(),
    table_name: z.string(),
    run_id: z.string().nullable(),
    attempted_record_count: z.number(),
    written_record_count: z.number(),
    error_count: z.number(),
    payload: payloadSchema,
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    storageWriteAuditId: value.storage_write_audit_id,
    provider: value.provider,
    tableName: value.table_name,
    runId: value.run_id,
    attemptedRecordCount: value.attempted_record_count,
    writtenRecordCount: value.written_record_count,
    errorCount: value.error_count,
    payload: value.payload,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

const riskJournalRecordSchema = z.object({
  journal_record_id: z.string(),
  record_type: z.literal("risk_decision"),
  payload: z
    .object({
      status: z.string().optional(),
      risk_gate_decision: z
        .object({
          status: z.string().optional(),
          explanation: z.string().optional(),
          audit_trail: z
            .object({
              rule_name: z.string().optional(),
              reason: z.string().optional(),
            })
            .passthrough()
            .optional(),
        })
        .passthrough()
        .optional(),
    })
    .passthrough(),
  created_at: z.string(),
});

export function dailyHaltFromRiskRecords(records: unknown[]) {
  const parsed = z.array(riskJournalRecordSchema).parse(records);
  const halt = parsed.find((record) => {
    const risk = record.payload.risk_gate_decision;
    const ruleName = risk?.audit_trail?.rule_name;
    const explanation = risk?.explanation?.toLowerCase() ?? "";
    return ruleName === "daily_halt" || explanation.includes("daily halt is active");
  });

  if (!halt) {
    return { status: "allowed" as const, record: null, createdAt: null };
  }

  return {
    status: "halted" as const,
    record: halt,
    createdAt: halt.created_at,
  };
}

export type RunRow = z.infer<typeof runRowSchema>;
export type ProviderErrorRow = z.infer<typeof providerErrorRowSchema>;
export type StorageAuditRow = z.infer<typeof storageAuditRowSchema>;
