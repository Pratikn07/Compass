"use client";

import { useState } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { DecisionList } from "./decision-list";
import { RunSwitcher } from "./run-switcher";
import { useDecisions } from "./use-decisions";
import { useLatestRun } from "./use-latest-run";
import { useRunHistory } from "./use-run-history";

export function DecisionListClient() {
  const latestRun = useLatestRun();
  const runHistory = useRunHistory();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // Default to the latest run until the operator picks another from the switcher.
  const activeRunId = selectedRunId ?? latestRun.data?.run_id ?? null;
  const decisions = useDecisions(activeRunId);

  if (latestRun.isPending) {
    return <LoadingState label="Loading latest run..." />;
  }

  if (latestRun.error) {
    return <ErrorState title={latestRun.error.message} />;
  }

  if (!latestRun.data) {
    return <EmptyState message="No run yet today." />;
  }

  const runs = runHistory.data ?? [];

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Decisions</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Latest run: {latestRun.data.run_id}
          </p>
        </div>
        {runs.length > 1 && activeRunId ? (
          <RunSwitcher
            runs={runs}
            selectedRunId={activeRunId}
            onSelect={setSelectedRunId}
          />
        ) : null}
      </div>

      {decisions.isPending ? (
        <LoadingState label="Loading decisions..." />
      ) : decisions.error ? (
        <ErrorState title={decisions.error.message} />
      ) : !decisions.data || decisions.data.length === 0 ? (
        <EmptyState message="No decisions for the latest run." />
      ) : (
        <DecisionList decisions={decisions.data} />
      )}
    </section>
  );
}
