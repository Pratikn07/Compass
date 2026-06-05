import { describe, expect, it } from "vitest";
import {
  modeAuthorizationResultSchema,
  operatorStatusSchema,
} from "@/lib/operator/schemas";
import {
  dailyHaltFromRiskRecords,
  providerErrorRowSchema,
  runRowSchema,
  systemHealthRowSchema,
} from "@/lib/runs/schemas";

describe("operator schemas", () => {
  it("parses operator status from the Python endpoint", () => {
    const parsed = operatorStatusSchema.parse({
      execution_mode: "propose_only",
      mode_source: "default",
      kill_switch: { status: "inactive", warnings: [] },
      latest_mode_authorization: null,
      warnings: [],
    });

    expect(parsed.executionMode).toBe("propose_only");
    expect(parsed.killSwitch.status).toBe("inactive");
  });

  it("parses rejected live mode authorization loudly", () => {
    const parsed = modeAuthorizationResultSchema.parse({
      status: "rejected",
      requested_mode: "live",
      previous_mode: "propose_only",
      active_mode: "propose_only",
      actor: "operator@example.com",
      reason: "try live",
      created_at: "2026-06-04T12:00:00Z",
      rejection_reasons: ["live_mode_disabled"],
      warnings: [],
    });

    expect(parsed.status).toBe("rejected");
    expect(parsed.rejectionReasons).toContain("live_mode_disabled");
  });
});

describe("runs schemas", () => {
  it("parses latest run rows", () => {
    const parsed = runRowSchema.parse({
      run_id: "scheduled:2026-06-04",
      trigger_type: "scheduled",
      scheduled_date: "2026-06-04",
      current_date: "2026-06-04",
      window_start: "2026-06-04",
      window_end: "2026-06-06",
      status: "completed",
      payload: { total_decision_count: 3 },
      schema_version: 1,
      created_at: "2026-06-04T12:00:00Z",
    });

    expect(parsed.runId).toBe("scheduled:2026-06-04");
    expect(parsed.status).toBe("completed");
  });

  it("parses provider errors without exposing sensitive payload assumptions", () => {
    const parsed = providerErrorRowSchema.parse({
      provider_error_id: "err-1",
      provider: "finnhub",
      error_type: "rate_limited",
      run_id: "scheduled:2026-06-04",
      target: "NTNX",
      source: "earnings",
      message: "rate limit",
      payload: {},
      schema_version: 1,
      created_at: "2026-06-04T12:00:00Z",
    });

    expect(parsed.provider).toBe("finnhub");
    expect(parsed.errorType).toBe("rate_limited");
  });

  it("parses provider-health system rows with payload details", () => {
    const parsed = systemHealthRowSchema.parse({
      system_health_id: "scheduled:2026-06-04:provider_health",
      component: "provider_health",
      status: "degraded",
      detail: "1 provider issue recorded.",
      latency_seconds: null,
      run_id: "scheduled:2026-06-04",
      payload: {
        providers: {
          finnhub: {
            requests: 1,
            cache_hits: 2,
            cache_misses: 1,
            retries: 1,
            errors: 0,
            budget_used: 3,
            budget_limit: 50,
            last_success_at: "2026-06-04T12:00:00Z",
            warnings: [],
          },
        },
      },
      schema_version: 1,
      created_at: "2026-06-04T12:00:00Z",
    });

    expect(parsed.component).toBe("provider_health");
    expect(parsed.payload.providers.finnhub.cache_hits).toBe(2);
  });

  it("infers daily halt from risk-decision audit payloads", () => {
    const dailyHalt = dailyHaltFromRiskRecords([
      {
        journal_record_id: "risk-1",
        record_type: "risk_decision",
        payload: {
          status: "blocked",
          risk_gate_decision: {
            status: "blocked",
            explanation: "Daily halt is active.",
            audit_trail: { rule_name: "daily_halt", reason: "daily_halt_active" },
          },
        },
        created_at: "2026-06-04T12:00:00Z",
      },
    ]);

    expect(dailyHalt.status).toBe("halted");
  });
});
