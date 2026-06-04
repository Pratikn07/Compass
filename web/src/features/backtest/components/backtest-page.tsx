"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { EquityCurveChart } from "@/features/backtest/components/equity-curve-chart";
import { MetricCard } from "@/features/backtest/components/metric-card";
import { OutcomeDistributionChart } from "@/features/backtest/components/outcome-distribution-chart";
import { ReportDiagnostics } from "@/features/backtest/components/report-diagnostics";
import { ReturnComparisonChart } from "@/features/backtest/components/return-comparison-chart";
import { SetupResultsTable } from "@/features/backtest/components/setup-results-table";
import { useBacktestReport } from "@/features/backtest/hooks/use-backtest-report";
import { buildBacktestViewModel } from "@/features/backtest/lib/backtest-view-model";

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

export function BacktestPage() {
  const reportQuery = useBacktestReport();

  if (queryIsLoading(reportQuery)) {
    return <LoadingState label="Loading backtest analytics..." />;
  }

  if (reportQuery.error) {
    return (
      <ErrorState
        title="Unable to load backtest analytics"
        detail={errorMessage(reportQuery.error)}
      />
    );
  }

  if (!reportQuery.data) {
    return <EmptyState message="No persisted backtest report is available yet." />;
  }

  const model = buildBacktestViewModel(reportQuery.data);

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-semibold">Backtest</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Latest persisted peer read-through backtest analytics.
          </p>
        </div>
        <dl className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2 rounded-card border border-border bg-card px-3 py-2">
            <dt>Report</dt>
            <dd className="font-mono text-foreground">{model.metadata.reportDate}</dd>
          </div>
          <div className="flex items-center gap-2 rounded-card border border-border bg-card px-3 py-2">
            <dt>Run</dt>
            <dd className="font-mono text-foreground">{model.metadata.runId}</dd>
          </div>
          <Badge variant="muted">{model.metadata.target}</Badge>
          <Badge variant="muted">{model.metadata.theme}</Badge>
        </dl>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {model.metrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <EquityCurveChart data={model.equityCurve} />
        <div className="grid gap-6">
          <ReturnComparisonChart data={model.returnComparison} />
          <OutcomeDistributionChart data={model.outcomeDistribution} />
        </div>
      </div>

      <SetupResultsTable rows={model.setupRows} />
      <ReportDiagnostics diagnostics={model.diagnostics} />
    </section>
  );
}
