"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { ModeAuthorizationPanel } from "@/components/runs/mode-authorization-panel";
import { ProviderErrorsTable } from "@/components/runs/provider-errors-table";
import { ProviderHealthTable } from "@/components/runs/provider-health-table";
import { RecentRunsTable } from "@/components/runs/recent-runs-table";
import { RunsSummaryCards } from "@/components/runs/runs-summary-cards";
import { StorageAuditTable } from "@/components/runs/storage-audit-table";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useOperatorStatus } from "@/lib/operator/hooks";
import {
  useDailyHaltStatus,
  useLatestRuns,
  useRecentProviderErrors,
  useRecentStorageAudit,
  useRecentSystemHealth,
} from "@/lib/runs/hooks";
import {
  buildRunsStatusViewModel,
  type OperationalStatus,
  type RunsStatusViewModel,
} from "@/lib/runs/status-view-model";

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
  const systemHealth = useRecentSystemHealth();
  const dailyHalt = useDailyHaltStatus();
  const operatorStatus = useOperatorStatus();

  const loading =
    queryIsLoading(runs) ||
    queryIsLoading(providerErrors) ||
    queryIsLoading(storageAudit) ||
    queryIsLoading(systemHealth) ||
    queryIsLoading(dailyHalt) ||
    queryIsLoading(operatorStatus);

  const firstError =
    runs.error ??
    providerErrors.error ??
    storageAudit.error ??
    systemHealth.error ??
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
  const view = buildRunsStatusViewModel({
    runs: runs.data ?? [],
    providerErrors: errors,
    storageAudit: audits,
    systemHealth: systemHealth.data ?? [],
    dailyHalt: { status: halt.status, createdAt: halt.createdAt },
    operatorStatus: operatorStatus.data,
  });

  return (
    <section className="grid gap-6">
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Scheduler status, safety state, and provider health.
        </p>
      </div>

      <OperationalStatusStrip view={view} />

      <RunsSummaryCards
        latestRun={view.latestRun}
        operatorStatus={operatorStatus.data}
        dailyHalt={{ status: halt.status, createdAt: halt.createdAt }}
        providerErrorCount={view.providerErrorCount}
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

      {view.recentRunRows.length ? (
        <RecentRunsTable rows={view.recentRunRows} />
      ) : (
        <EmptyState message="No runs have been recorded yet." />
      )}

      {view.providerHealthRows.length ? (
        <ProviderHealthTable rows={view.providerHealthRows} />
      ) : (
        <EmptyState message="No provider health recorded." />
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        {errors.length ? (
          <ProviderErrorsTable errors={errors} />
        ) : (
          <EmptyState message="No recent provider errors." />
        )}
        {view.storageAuditRows.length ? (
          <StorageAuditTable rows={view.storageAuditRows} />
        ) : (
          <EmptyState message="No recent storage write audit rows." />
        )}
      </div>
    </section>
  );
}

function OperationalStatusStrip({ view }: { view: RunsStatusViewModel }) {
  const variant = badgeVariantForOperationalStatus(view.operationalStatus);
  const Icon = view.operationalStatus === "clear" ? CheckCircle2 : AlertTriangle;

  return (
    <Card className="grid gap-3 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Operational status
            </p>
            <div className="mt-1 flex items-center gap-2">
              <Badge dot variant={variant}>
                {view.operationalLabel}
              </Badge>
              <span className="text-sm text-muted-foreground">
                Derived from current run, safety, provider, and storage records.
              </span>
            </div>
          </div>
        </div>
      </div>
      <ul className="grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
        {view.operationalReasons.map((reason) => (
          <li key={reason} className="flex items-start gap-2">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/60" />
            <span>{reason}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function badgeVariantForOperationalStatus(status: OperationalStatus) {
  if (status === "blocked") return "danger" as const;
  if (status === "attention") return "warning" as const;
  return "success" as const;
}
