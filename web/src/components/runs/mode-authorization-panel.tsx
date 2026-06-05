"use client";

import { useState } from "react";
import { KeyRound, ShieldCheck, Undo2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useModeAuthorizationMutation } from "@/lib/operator/hooks";
import type { ModeAuthorizationResult } from "@/lib/operator/schemas";

const MIN_REASON_LENGTH = 10;
const MAX_REASON_LENGTH = 1000;

export function ModeAuthorizationPanel({
  latestModeAuthorization,
}: {
  latestModeAuthorization: ModeAuthorizationResult | null;
}) {
  const [reason, setReason] = useState("");
  const mutation = useModeAuthorizationMutation();
  const trimmedReason = reason.trim();
  const disabled =
    trimmedReason.length < MIN_REASON_LENGTH ||
    trimmedReason.length > MAX_REASON_LENGTH ||
    mutation.isPending;

  function requestMode(requestedMode: "paper" | "propose_only") {
    mutation.mutate({
      requestedMode,
      reason: trimmedReason,
    });
  }

  return (
    <section
      aria-label="Mode authorization"
      className="rounded-card border border-accent/30 bg-accent/[0.03] p-5 shadow-sm ring-1 ring-accent/10"
    >
      <div className="mb-4 flex items-center gap-2 border-b border-accent/15 pb-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10 text-accent">
          <KeyRound className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-accent">
            Privileged action
          </p>
          <p className="text-xs text-muted-foreground">
            Requests are enforced by the code rails — the system decides, not the
            UI. Live mode is never available here.
          </p>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_auto]">
        <div>
          <h2 className="text-base font-semibold">Mode authorization</h2>
          {latestModeAuthorization ? (
            <p className="mt-1 text-sm text-muted-foreground">
              Last request: {latestModeAuthorization.status} by{" "}
              {latestModeAuthorization.actor}
            </p>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              No recorded mode authorization request.
            </p>
          )}
        </div>
        {latestModeAuthorization ? (
          <div className="flex items-center gap-2 xl:justify-end">
            <Badge
              variant={
                latestModeAuthorization.status === "accepted" ? "success" : "danger"
              }
            >
              {latestModeAuthorization.status}
            </Badge>
            <span className="font-mono text-sm">
              {latestModeAuthorization.activeMode}
            </span>
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_auto_auto] lg:items-end">
        <label className="grid gap-1 text-sm">
          <span className="font-medium">Reason</span>
          <textarea
            aria-label="Reason"
            value={reason}
            maxLength={MAX_REASON_LENGTH}
            onChange={(event) =>
              setReason(event.target.value.slice(0, MAX_REASON_LENGTH))
            }
            placeholder="Describe why this mode change is needed."
            rows={4}
            className="min-h-28 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20"
          />
          <span className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>Minimum 10 characters.</span>
            <span className="font-mono">
              {reason.length}/{MAX_REASON_LENGTH}
            </span>
          </span>
        </label>
        <Button
          type="button"
          disabled={disabled}
          onClick={() => requestMode("paper")}
        >
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Request paper mode
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => requestMode("propose_only")}
        >
          <Undo2 className="h-4 w-4" aria-hidden="true" />
          Return propose-only
        </Button>
      </div>

      <RequestStatusBox
        latestModeAuthorization={latestModeAuthorization}
        mutation={mutation}
      />
    </section>
  );
}

function RequestStatusBox({
  latestModeAuthorization,
  mutation,
}: {
  latestModeAuthorization: ModeAuthorizationResult | null;
  mutation: ReturnType<typeof useModeAuthorizationMutation>;
}) {
  const result = mutation.data;
  let badgeVariant: "muted" | "success" | "danger" | "warning" = "muted";
  let title = "No request submitted in this session.";
  let detail =
    latestModeAuthorization?.createdAt ??
    "Only authorized operators may submit mode changes.";

  if (mutation.isPending) {
    badgeVariant = "warning";
    title = "Request pending";
    detail = "Waiting for operator authorization response.";
  } else if (result?.status === "accepted") {
    badgeVariant = "success";
    title = "Request accepted";
    detail = `Active mode: ${result.activeMode}`;
  } else if (result?.status === "rejected") {
    badgeVariant = "danger";
    title = "Request rejected";
    detail = result.rejectionReasons.length
      ? result.rejectionReasons.join(", ")
      : "The operator endpoint rejected the request.";
  } else if (mutation.isError) {
    badgeVariant = "danger";
    title = "Request failed";
    detail =
      mutation.error instanceof Error
        ? mutation.error.message
        : "The request failed before authorization completed.";
  }

  return (
    <div className="mt-4 rounded-card border border-border bg-background p-3 text-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-medium">Request status</p>
        <Badge dot variant={badgeVariant}>
          {title}
        </Badge>
      </div>
      <p className="mt-2 text-muted-foreground">{detail}</p>
    </div>
  );
}
