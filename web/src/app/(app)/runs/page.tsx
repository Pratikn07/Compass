"use client";

import { AlertTriangle } from "lucide-react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { ModeAuthorizationPanel } from "@/components/runs/mode-authorization-panel";
import { ProviderErrorsTable } from "@/components/runs/provider-errors-table";
import { RunsSummaryCards } from "@/components/runs/runs-summary-cards";
import { StorageAuditTable } from "@/components/runs/storage-audit-table";
import { useOperatorStatus } from "@/lib/operator/hooks";
import {
  useDailyHaltStatus,
  useLatestRuns,
  useRecentProviderErrors,
  useRecentStorageAudit,
} from "@/lib/runs/hooks";

function queryIsLoading(query: { isLoading?: boolean; isPending?: boolean }) {
  return Boolean(query.isLoading || query.isPending);
}

function errorMessage(value: unknown) {
  if (value instanceof Error) {
    return value.message;
  }
  if (typeof value === "string") {
    return value;
  }
  return undefined;
}

export default function RunsPage() {
  const runs = useLatestRuns();
  const providerErrors = useRecentProviderErrors();
  const storageAudit = useRecentStorageAudit();
  const dailyHalt = useDailyHaltStatus();
  const operatorStatus = useOperatorStatus();

  const loading =
    queryIsLoading(runs) ||
    queryIsLoading(providerErrors) ||
    queryIsLoading(storageAudit) ||
    queryIsLoading(dailyHalt) ||
    queryIsLoading(operatorStatus);

  const firstError =
    runs.error ??
    providerErrors.error ??
    storageAudit.error ??
    dailyHalt.error ??
    operatorStatus.error;

  if (loading) {
    return <LoadingState label="Loading run status..." />;
  }

  if (firstError) {
    return (
      <ErrorState
        title="Unable to load run status"
        detail={errorMessage(firstError)}
      />
    );
  }

  if (!operatorStatus.data) {
    return <ErrorState title="Operator status unavailable" />;
  }

  const latestRun = runs.data?.[0] ?? null;
  const errors = providerErrors.data ?? [];
  const audits = storageAudit.data ?? [];
  const halt = dailyHalt.data ?? {
    status: "allowed" as const,
    createdAt: null,
    record: null,
  };
  const warnings = [
    ...operatorStatus.data.warnings,
    ...operatorStatus.data.killSwitch.warnings,
  ];

  return (
    <section className="grid gap-6">
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Scheduler status, safety state, and provider health.
        </p>
      </div>

      <RunsSummaryCards
        latestRun={latestRun}
        operatorStatus={operatorStatus.data}
        dailyHalt={{ status: halt.status, createdAt: halt.createdAt }}
        providerErrorCount={errors.length}
      />

      {warnings.length ? (
        <div className="flex items-start gap-2 rounded-card border border-warning/40 border-l-4 border-l-warning bg-warning/5 p-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{warnings.join(" ")}</span>
        </div>
      ) : null}

      <ModeAuthorizationPanel
        latestModeAuthorization={operatorStatus.data.latestModeAuthorization}
      />

      {runs.data?.length ? null : <EmptyState message="No runs have been recorded yet." />}

      <div className="grid gap-6 xl:grid-cols-2">
        {errors.length ? (
          <ProviderErrorsTable errors={errors} />
        ) : (
          <EmptyState message="No recent provider errors." />
        )}
        {audits.length ? (
          <StorageAuditTable rows={audits} />
        ) : (
          <EmptyState message="No recent storage write audit rows." />
        )}
      </div>
    </section>
  );
}
