import { z } from "zod";

const executionModeSchema = z.enum(["propose_only", "paper", "live"]);

export const killSwitchSchema = z
  .object({
    status: z.enum(["inactive", "active"]),
    reason: z.string().nullable().optional(),
    activated_at: z.string().nullable().optional(),
    activated_by: z.string().nullable().optional(),
    reset_at: z.string().nullable().optional(),
    reset_by: z.string().nullable().optional(),
    warnings: z.array(z.string()).default([]),
  })
  .passthrough()
  .transform((value) => ({
    status: value.status,
    reason: value.reason ?? null,
    activatedAt: value.activated_at ?? null,
    activatedBy: value.activated_by ?? null,
    resetAt: value.reset_at ?? null,
    resetBy: value.reset_by ?? null,
    warnings: value.warnings,
  }));

export const modeAuthorizationResultSchema = z
  .object({
    status: z.enum(["accepted", "rejected"]),
    requested_mode: executionModeSchema,
    previous_mode: executionModeSchema,
    active_mode: executionModeSchema,
    actor: z.string(),
    reason: z.string(),
    created_at: z.string(),
    rejection_reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
  })
  .transform((value) => ({
    status: value.status,
    requestedMode: value.requested_mode,
    previousMode: value.previous_mode,
    activeMode: value.active_mode,
    actor: value.actor,
    reason: value.reason,
    createdAt: value.created_at,
    rejectionReasons: value.rejection_reasons,
    warnings: value.warnings,
  }));

export const operatorStatusSchema = z
  .object({
    execution_mode: executionModeSchema,
    mode_source: z.string(),
    kill_switch: killSwitchSchema,
    latest_mode_authorization: modeAuthorizationResultSchema.nullable().optional(),
    warnings: z.array(z.string()).default([]),
  })
  .transform((value) => ({
    executionMode: value.execution_mode,
    modeSource: value.mode_source,
    killSwitch: value.kill_switch,
    latestModeAuthorization: value.latest_mode_authorization ?? null,
    warnings: value.warnings,
  }));

export type ExecutionMode = z.infer<typeof executionModeSchema>;
export type ModeAuthorizationResult = z.infer<typeof modeAuthorizationResultSchema>;
export type OperatorStatus = z.infer<typeof operatorStatusSchema>;
