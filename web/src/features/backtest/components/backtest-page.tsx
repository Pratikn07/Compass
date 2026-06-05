"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { DrawdownChart } from "@/features/backtest/components/drawdown-chart";
import { EquityCurveChart } from "@/features/backtest/components/equity-curve-chart";
import { MetricCard } from "@/features/backtest/components/metric-card";
import { OutcomeDistributionChart } from "@/features/backtest/components/outcome-distribution-chart";
import { ReportDiagnostics } from "@/features/backtest/components/report-diagnostics";
import { ReturnComparisonChart } from "@/features/backtest/components/return-comparison-chart";
import { SetupResultsTable } from "@/features/backtest/components/setup-results-table";
import { useBacktestReport } from "@/features/backtest/hooks/use-backtest-report";
import {
  type BacktestDisplayMode,
  type BacktestViewModel,
  buildBacktestViewModel,
} from "@/features/backtest/lib/backtest-view-model";

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
  const [displayMode, setDisplayMode] = useState<BacktestDisplayMode>("percent");

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

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid min-w-0 gap-6">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-muted-foreground">
              Display performance as percent return or dollar equity.
            </p>
            <div
              aria-label="Backtest display mode"
              className="inline-flex w-fit rounded-md border border-border bg-card p-1"
              role="group"
            >
              <ModeButton
                active={displayMode === "percent"}
                label="Show percent"
                onClick={() => setDisplayMode("percent")}
              >
                %
              </ModeButton>
              <ModeButton
                active={displayMode === "dollars"}
                label="Show dollars"
                onClick={() => setDisplayMode("dollars")}
              >
                $
              </ModeButton>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {model.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
            <div className="grid gap-6">
              <EquityCurveChart data={model.equityCurve} mode={displayMode} />
              <DrawdownChart data={model.drawdownCurve} mode={displayMode} />
            </div>
            <div className="grid gap-6">
              <ReturnComparisonChart data={model.returnComparison} />
              <OutcomeDistributionChart data={model.outcomeDistribution} />
            </div>
          </div>

          <SetupResultsTable mode={displayMode} rows={model.setupRows} />
          <ReportDiagnostics diagnostics={model.diagnostics} />
        </div>

        <BacktestConsole console={model.console} />
      </div>
    </section>
  );
}

function ModeButton({
  active,
  children,
  label,
  onClick,
}: {
  active: boolean;
  children: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      aria-label={label}
      aria-pressed={active}
      className={
        active
          ? "min-h-9 px-3"
          : "min-h-9 bg-transparent px-3 text-muted-foreground shadow-none hover:bg-muted"
      }
      onClick={onClick}
      type="button"
      variant={active ? "primary" : "outline"}
    >
      {children}
    </Button>
  );
}

function BacktestConsole({
  console,
}: {
  console: BacktestViewModel["console"];
}) {
  return (
    <aside className="min-w-0">
      <Card className="sticky top-20 grid gap-5">
        <div>
          <h2 className="text-base font-semibold">Advanced console</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Read-only run scope and data-quality controls for this persisted report.
          </p>
        </div>
        <ConsoleSection items={console.runScope} title="Run scope" />
        <ConsoleSection
          items={[
            ...console.dataQuality,
            { label: "Include rejected", value: console.includeRejectedCandidates },
            { label: "Trade P&L", value: console.includeTradePnl },
          ]}
          title="Data quality"
        />
        <ConsoleSection items={console.tableControls} title="Table controls" />
      </Card>
    </aside>
  );
}

function ConsoleSection({
  items,
  title,
}: {
  items: { label: string; value: string }[];
  title: string;
}) {
  return (
    <section className="grid gap-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <dl className="grid gap-3 text-sm">
        {items.map((item) => (
          <ConsoleItem
            key={`${title}-${item.label}`}
            label={item.label}
            value={item.value}
          />
        ))}
      </dl>
    </section>
  );
}

function ConsoleItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-background px-3 py-2">
      <dt className="text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words font-mono text-foreground">{value}</dd>
    </div>
  );
}
