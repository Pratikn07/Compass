import {
  modeAuthorizationResultSchema,
  operatorStatusSchema,
  type ExecutionMode,
} from "@/lib/operator/schemas";

async function parseJson(response: Response) {
  return response.json().catch(() => ({
    error: "Endpoint returned malformed JSON",
  }));
}

export async function fetchOperatorStatus() {
  const response = await fetch("/api/operator/status", { cache: "no-store" });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? "Unable to load operator status");
  }
  return operatorStatusSchema.parse(payload);
}

export async function requestModeAuthorization(input: {
  requestedMode: Exclude<ExecutionMode, "live">;
  reason: string;
}) {
  const response = await fetch("/api/operator/mode-authorization", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requested_mode: input.requestedMode,
      reason: input.reason,
    }),
    cache: "no-store",
  });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload.error ?? "Unable to request mode authorization");
  }
  return modeAuthorizationResultSchema.parse(payload);
}
