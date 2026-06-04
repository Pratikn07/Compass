"use client";

import { useState } from "react";
import { KeyRound, ShieldCheck, Undo2 } from "lucide-react";
import { ErrorState } from "@/components/states/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useModeAuthorizationMutation } from "@/lib/operator/hooks";
import type { ModeAuthorizationResult } from "@/lib/operator/schemas";

export function ModeAuthorizationPanel({
  latestModeAuthorization,
}: {
  latestModeAuthorization: ModeAuthorizationResult | null;
}) {
  const [reason, setReason] = useState("");
  const mutation = useModeAuthorizationMutation();
  const disabled = reason.trim().length === 0 || mutation.isPending;

  function requestMode(requestedMode: "paper" | "propose_only") {
    mutation.mutate({
      requestedMode,
      reason: reason.trim(),
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

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(12rem,1fr)_auto_auto]">
        <label className="grid gap-1 text-sm">
          <span>Reason</span>
          <Input
            aria-label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="paper validation"
          />
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

      {mutation.data?.status === "rejected" ? (
        <div className="mt-4 rounded-card border border-danger bg-danger/10 p-3 text-sm text-danger">
          Rejected: {mutation.data.rejectionReasons.join(", ")}
        </div>
      ) : null}

      {mutation.isError ? (
        <div className="mt-4">
          <ErrorState
            title="Mode request failed"
            detail={mutation.error instanceof Error ? mutation.error.message : undefined}
          />
        </div>
      ) : null}
    </section>
  );
}
