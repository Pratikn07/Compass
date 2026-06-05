"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { DecisionList } from "./decision-list";
import { formatDecisionValue } from "./decision-list-format";
import type { RunRow } from "./decision-list.types";
import type { SystemHealthRow } from "./decision-sidebar-schemas";
import {
  buildDecisionListViewModel,
  DECISION_LIST_PAGE_SIZES,
  normalizeDecisionListParams,
  type DecisionListPageSize,
  type DecisionListQuery,
  type DecisionListViewModel,
  type DecisionEarningsWindow,
  type DecisionQuickBucket,
  type SidebarCountItem,
} from "./decision-list-view-model";
import { RunSwitcher } from "./run-switcher";
import { useDecisionSystemHealth } from "./use-decision-system-health";
import { useDecisionWatchlists } from "./use-decision-watchlists";
import { useDecisions } from "./use-decisions";
import { useLatestRun } from "./use-latest-run";
import { useRunHistory } from "./use-run-history";

export function DecisionListClient() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const latestRun = useLatestRun();
  const runHistory = useRunHistory();
  const runs = runHistory.data ?? [];
  const runParam = searchParams.get("run");
  const activeRunId = resolveActiveRunId(
    runParam,
    latestRun.data?.run_id ?? null,
    runs,
  );
  const listQuery = normalizeDecisionListParams(searchParams);

  const decisions = useDecisions(activeRunId);
  const watchlists = useDecisionWatchlists();
  const systemHealth = useDecisionSystemHealth();

  function updateSearchParams(mutator: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(searchParams.toString());
    mutator(next);
    const nextRun = next.get("run");

    if (
      activeRunId &&
      nextRun &&
      nextRun !== activeRunId &&
      !isKnownRunId(nextRun, latestRun.data?.run_id ?? null, runs)
    ) {
      next.set("run", activeRunId);
    }

    const queryString = next.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, {
      scroll: false,
    });
  }

  useEffect(() => {
    if (watchlists.isPending || watchlists.error || !listQuery.watchlist) {
      return;
    }
    const known = (watchlists.data ?? []).some(
      (watchlist) => watchlist.watchlistId === listQuery.watchlist,
    );
    if (!known) {
      updateSearchParams((next) => {
        next.delete("watchlist");
        next.delete("page");
      });
    }
  }, [listQuery.watchlist, watchlists.data, watchlists.error, watchlists.isPending]);

  if (latestRun.isPending) {
    return <LoadingState label="Loading latest run..." />;
  }

  if (latestRun.error) {
    return <ErrorState title={latestRun.error.message} />;
  }

  if (!latestRun.data) {
    return <EmptyState message="No run yet today." />;
  }

  function handleRunSelect(runId: string) {
    updateSearchParams((next) => {
      next.set("run", runId);
      next.delete("page");
    });
  }

  function handleQueryChange(value: string) {
    updateSearchParams((next) => {
      setOrDelete(next, "q", value.trim());
      next.delete("page");
    });
  }

  function handleStatusChange(value: string) {
    updateSearchParams((next) => {
      setOrDelete(next, "status", value);
      next.delete("page");
    });
  }

  function handleStrategyChange(value: string) {
    updateSearchParams((next) => {
      setOrDelete(next, "strategy", value);
      next.delete("page");
    });
  }

  function handleBucketChange(bucket: DecisionQuickBucket) {
    updateSearchParams((next) => {
      setOrDelete(next, "bucket", bucket === "all" ? "" : bucket);
      next.delete("page");
    });
  }

  function handleEarningsChange(earnings: DecisionEarningsWindow) {
    updateSearchParams((next) => {
      setOrDelete(next, "earnings", earnings === "all" ? "" : earnings);
      next.delete("page");
    });
  }

  function handleWatchlistChange(watchlistId: string) {
    updateSearchParams((next) => {
      const nextWatchlist =
        listQuery.watchlist === watchlistId ? "" : watchlistId;
      setOrDelete(next, "watchlist", nextWatchlist);
      next.delete("page");
    });
  }

  function handleClearFilters() {
    updateSearchParams((next) => {
      if (activeRunId) {
        next.set("run", activeRunId);
      }
      next.delete("q");
      next.delete("status");
      next.delete("strategy");
      next.delete("bucket");
      next.delete("earnings");
      next.delete("watchlist");
      next.delete("page");
    });
  }

  function handlePageChange(page: number) {
    updateSearchParams((next) => {
      if (page <= 1) {
        next.delete("page");
      } else {
        next.set("page", String(page));
      }
    });
  }

  function handlePageSizeChange(pageSize: DecisionListPageSize) {
    updateSearchParams((next) => {
      next.set("pageSize", String(pageSize));
      next.delete("page");
    });
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Decisions</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Active run: {activeRunId ?? latestRun.data.run_id}
          </p>
        </div>
        {runs.length > 1 && activeRunId ? (
          <RunSwitcher
            runs={runs}
            selectedRunId={activeRunId}
            onSelect={handleRunSelect}
          />
        ) : null}
      </div>

      {decisions.isPending ? (
        <LoadingState label="Loading decisions..." />
      ) : decisions.error ? (
        <ErrorState title={decisions.error.message} />
      ) : !decisions.data || decisions.data.length === 0 ? (
        <EmptyState message="No decisions for the selected run." />
      ) : (
        <DecisionListContent
          decisions={decisions.data}
          activeRunDate={activeRunDate(activeRunId, latestRun.data, runs)}
          healthRows={systemHealth.data ?? []}
          healthError={systemHealth.error ?? null}
          healthPending={systemHealth.isPending}
          listQuery={listQuery}
          onClearFilters={handleClearFilters}
          onBucketChange={handleBucketChange}
          onEarningsChange={handleEarningsChange}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
          onQueryChange={handleQueryChange}
          onRunSelect={handleRunSelect}
          onStatusChange={handleStatusChange}
          onStrategyChange={handleStrategyChange}
          onWatchlistChange={handleWatchlistChange}
          runs={runs}
          selectedRunId={activeRunId}
          watchlists={watchlists.data ?? []}
          watchlistsError={watchlists.error ?? null}
          watchlistsPending={watchlists.isPending}
        />
      )}
    </section>
  );
}

function DecisionListContent({
  activeRunDate,
  decisions,
  healthRows,
  healthError,
  healthPending,
  listQuery,
  onBucketChange,
  onClearFilters,
  onEarningsChange,
  onPageChange,
  onPageSizeChange,
  onQueryChange,
  onRunSelect,
  onStatusChange,
  onStrategyChange,
  onWatchlistChange,
  runs,
  selectedRunId,
  watchlists,
  watchlistsError,
  watchlistsPending,
}: {
  activeRunDate: string | null;
  decisions: Parameters<typeof buildDecisionListViewModel>[0];
  healthRows: SystemHealthRow[];
  healthError: Error | null;
  healthPending: boolean;
  listQuery: DecisionListQuery;
  onBucketChange: (bucket: DecisionQuickBucket) => void;
  onClearFilters: () => void;
  onEarningsChange: (earnings: DecisionEarningsWindow) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: DecisionListPageSize) => void;
  onQueryChange: (query: string) => void;
  onRunSelect: (runId: string) => void;
  onStatusChange: (status: string) => void;
  onStrategyChange: (strategy: string) => void;
  onWatchlistChange: (watchlistId: string) => void;
  runs: RunRow[];
  selectedRunId: string | null;
  watchlists: NonNullable<ReturnType<typeof useDecisionWatchlists>["data"]>;
  watchlistsError: Error | null;
  watchlistsPending: boolean;
}) {
  const view = buildDecisionListViewModel(decisions, listQuery, {
    activeRunDate,
    watchlists,
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)] lg:items-start">
      <DecisionSidebar
        healthError={healthError}
        healthPending={healthPending}
        healthRows={healthRows}
        onBucketChange={onBucketChange}
        onEarningsChange={onEarningsChange}
        onRunSelect={onRunSelect}
        onWatchlistChange={onWatchlistChange}
        runs={runs}
        selectedRunId={selectedRunId}
        view={view}
        watchlistsError={watchlistsError}
        watchlistsPending={watchlistsPending}
      />

      <div className="min-w-0 space-y-3">
        <DecisionListControls
          listQuery={listQuery}
          onClearFilters={onClearFilters}
          onQueryChange={onQueryChange}
          onStatusChange={onStatusChange}
          onStrategyChange={onStrategyChange}
          view={view}
        />

        {view.filteredCount === 0 ? (
          <div className="space-y-4">
            <EmptyState message="No decisions match the current filters." />
            {view.hasActiveFilters ? (
              <div className="flex justify-center">
                <Button type="button" variant="outline" onClick={onClearFilters}>
                  <X className="h-4 w-4" aria-hidden="true" />
                  Clear filters
                </Button>
              </div>
            ) : null}
          </div>
        ) : (
          <>
            <DecisionList decisions={view.pageItems} />
            <DecisionListPagination
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
              view={view}
            />
          </>
        )}
      </div>
    </div>
  );
}

function DecisionSidebar({
  healthError,
  healthPending,
  healthRows,
  onBucketChange,
  onEarningsChange,
  onRunSelect,
  onWatchlistChange,
  runs,
  selectedRunId,
  view,
  watchlistsError,
  watchlistsPending,
}: {
  healthError: Error | null;
  healthPending: boolean;
  healthRows: SystemHealthRow[];
  onBucketChange: (bucket: DecisionQuickBucket) => void;
  onEarningsChange: (earnings: DecisionEarningsWindow) => void;
  onRunSelect: (runId: string) => void;
  onWatchlistChange: (watchlistId: string) => void;
  runs: RunRow[];
  selectedRunId: string | null;
  view: DecisionListViewModel;
  watchlistsError: Error | null;
  watchlistsPending: boolean;
}) {
  return (
    <aside className="overflow-hidden rounded-card border border-border bg-card shadow-sm shadow-primary/[0.03] lg:sticky lg:top-20">
      <SidebarSection title="Quick Filters">
        <SidebarButtonGroup
          items={view.sidebar.quickFilters}
          onSelect={onBucketChange}
        />
      </SidebarSection>

      <SidebarSection title="Universe">
        <SidebarButtonGroup
          items={view.sidebar.earningsWindows}
          onSelect={onEarningsChange}
        />
      </SidebarSection>

      <SidebarSection title="Watchlists">
        {watchlistsPending ? (
          <p className="text-sm text-muted-foreground">Loading watchlists...</p>
        ) : watchlistsError ? (
          <p className="text-sm text-danger">Watchlists unavailable.</p>
        ) : view.sidebar.watchlists.length ? (
          <div className="grid gap-1">
            {view.sidebar.watchlists.map((watchlist) => (
              <button
                key={watchlist.watchlistId}
                type="button"
                aria-label={`${watchlist.name} ${watchlist.count}`}
                aria-pressed={watchlist.active}
                onClick={() => onWatchlistChange(watchlist.watchlistId)}
                className={sidebarButtonClassName(watchlist.active)}
              >
                <span className="truncate">{watchlist.name}</span>
                <span className={sidebarCountClassName(watchlist.active)}>
                  {watchlist.count}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No watchlists.</p>
        )}
      </SidebarSection>

      <SidebarSection title="Recent Runs">
        <div className="grid gap-1">
          {runs.slice(0, 5).map((run) => {
            const active = run.run_id === selectedRunId;
            return (
              <button
                key={run.run_id}
                type="button"
                aria-pressed={active}
                onClick={() => onRunSelect(run.run_id)}
                className={cn(
                  sidebarButtonClassName(active),
                  "min-h-12 items-start",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate font-mono text-xs">
                    {run.run_id}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {formatRunMeta(run)}
                  </span>
                </span>
                <span className={sidebarCountClassName(active)}>
                  {runDecisionCount(run)}
                </span>
              </button>
            );
          })}
        </div>
      </SidebarSection>

      <SidebarSection title="System Status">
        <SystemHealthList
          error={healthError}
          isPending={healthPending}
          rows={healthRows}
        />
      </SidebarSection>
    </aside>
  );
}

function SidebarSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="border-b border-border px-3 py-3.5 last:border-b-0">
      <h2 className="mb-2 px-1 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/80">
        {title}
      </h2>
      {children}
    </section>
  );
}

function SidebarButtonGroup<T extends string>({
  items,
  onSelect,
}: {
  items: SidebarCountItem<T>[];
  onSelect: (key: T) => void;
}) {
  return (
    <div className="grid gap-1">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          aria-label={`${item.label} ${item.count}`}
          aria-pressed={item.active}
          onClick={() => onSelect(item.key)}
          className={sidebarButtonClassName(item.active)}
        >
          <span>{item.label}</span>
          <span className={sidebarCountClassName(item.active)}>{item.count}</span>
        </button>
      ))}
    </div>
  );
}

function SystemHealthList({
  error,
  isPending,
  rows,
}: {
  error: Error | null;
  isPending: boolean;
  rows: SystemHealthRow[];
}) {
  if (isPending) {
    return <p className="text-sm text-muted-foreground">Loading status...</p>;
  }
  if (error) {
    return <p className="text-sm text-danger">System status unavailable.</p>;
  }

  return (
    <div className="grid gap-2">
      {systemHealthComponents.map((component) => {
        const row = rows.find((item) => item.component === component.key);
        const status = row?.status ?? "unknown";
        return (
          <div
            key={component.key}
            className="grid gap-1 rounded-md border border-border bg-background px-2.5 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{component.label}</span>
              <Badge dot variant={badgeVariantForHealth(status)}>
                {formatDecisionValue(status)}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              <span>{row?.detail ?? "No backend health record."}</span>
              {row?.latencySeconds !== null && row?.latencySeconds !== undefined
                ? <span> Latency {Math.round(row.latencySeconds)}s.</span>
                : null}
            </p>
          </div>
        );
      })}
      <Link
        href="/runs"
        className="text-sm font-medium text-accent underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        Runs
      </Link>
    </div>
  );
}

const systemHealthComponents = [
  { key: "market_data", label: "Market Data" },
  { key: "pricing_engine", label: "Pricing Engine" },
  { key: "risk_engine", label: "Risk Engine" },
] as const;

function DecisionListControls({
  listQuery,
  onClearFilters,
  onQueryChange,
  onStatusChange,
  onStrategyChange,
  view,
}: {
  listQuery: DecisionListQuery;
  onClearFilters: () => void;
  onQueryChange: (query: string) => void;
  onStatusChange: (status: string) => void;
  onStrategyChange: (strategy: string) => void;
  view: DecisionListViewModel;
}) {
  const statusOptions = includeActiveOption(view.statusOptions, listQuery.status);
  const strategyOptions = includeActiveOption(
    view.strategyOptions,
    listQuery.strategy,
  );

  return (
    <div className="flex flex-col gap-3 border-b border-border pb-3 xl:flex-row xl:items-end xl:justify-between">
      <div className="grid gap-3 sm:grid-cols-[minmax(16rem,1fr)_minmax(11rem,14rem)_minmax(14rem,18rem)_auto] sm:items-end">
        <label className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Search
          </span>
          <Input
            aria-label="Search decisions"
            type="search"
            value={listQuery.query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Target, theme, thesis, evidence"
            className="h-10 min-h-10 text-sm"
          />
        </label>

        <label className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Status
          </span>
          <select
            aria-label="Filter by status"
            value={listQuery.status}
            onChange={(event) => onStatusChange(event.target.value)}
            className={selectClassName}
          >
            <option value="">All statuses</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {formatDecisionValue(status)}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Strategy
          </span>
          <select
            aria-label="Filter by strategy"
            value={listQuery.strategy}
            onChange={(event) => onStrategyChange(event.target.value)}
            className={selectClassName}
          >
            <option value="">All strategies</option>
            {strategyOptions.map((strategy) => (
              <option key={strategy} value={strategy}>
                {formatDecisionValue(strategy)}
              </option>
            ))}
          </select>
        </label>

        {view.hasActiveFilters ? (
          <Button
            type="button"
            variant="outline"
            onClick={onClearFilters}
            className="h-10 min-h-10 px-3"
          >
            <X className="h-4 w-4" aria-hidden="true" />
            Clear filters
          </Button>
        ) : null}
      </div>

      <p className="text-sm text-muted-foreground">{formatResultSummary(view)}</p>
    </div>
  );
}

function DecisionListPagination({
  onPageChange,
  onPageSizeChange,
  view,
}: {
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: DecisionListPageSize) => void;
  view: DecisionListViewModel;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        Rows per page
        <select
          aria-label="Rows per page"
          value={view.pageSize}
          onChange={(event) =>
            onPageSizeChange(Number(event.target.value) as DecisionListPageSize)
          }
          className={selectClassName}
        >
          {DECISION_LIST_PAGE_SIZES.map((pageSize) => (
            <option key={pageSize} value={pageSize}>
              {pageSize}
            </option>
          ))}
        </select>
      </label>

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          disabled={view.page <= 1}
          onClick={() => onPageChange(view.page - 1)}
          className="h-10 min-h-10 px-3"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Previous
        </Button>
        <span className="min-w-24 text-center text-sm text-muted-foreground">
          Page {view.page} of {view.pageCount}
        </span>
        <Button
          type="button"
          variant="outline"
          disabled={view.page >= view.pageCount}
          onClick={() => onPageChange(view.page + 1)}
          className="h-10 min-h-10 px-3"
        >
          Next
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function resolveActiveRunId(
  runParam: string | null,
  latestRunId: string | null,
  runs: RunRow[],
): string | null {
  if (runParam && isKnownRunId(runParam, latestRunId, runs)) {
    return runParam;
  }
  return latestRunId;
}

function isKnownRunId(
  runId: string,
  latestRunId: string | null,
  runs: RunRow[],
): boolean {
  return runId === latestRunId || runs.some((run) => run.run_id === runId);
}

function activeRunDate(
  activeRunId: string | null,
  latestRun: RunRow | null,
  runs: RunRow[],
): string | null {
  const activeRun =
    runs.find((run) => run.run_id === activeRunId) ??
    (latestRun?.run_id === activeRunId ? latestRun : null);
  return (
    activeRun?.current_date ??
    activeRun?.scheduled_date ??
    activeRun?.window_start ??
    null
  );
}

function sidebarButtonClassName(active: boolean): string {
  return cn(
    "group/sidebar-btn relative flex min-h-9 w-full items-center justify-between gap-2 rounded-md py-1.5 pl-3 pr-2 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    "before:absolute before:left-0 before:top-1/2 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:transition-colors",
    active
      ? "bg-accent/10 font-medium text-foreground before:bg-accent"
      : "text-muted-foreground before:bg-transparent hover:bg-muted hover:text-foreground",
  );
}

function sidebarCountClassName(active: boolean): string {
  return cn(
    "inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-center font-mono text-[0.6875rem] tabular-nums transition-colors",
    active
      ? "bg-accent/15 text-accent"
      : "bg-muted text-muted-foreground group-hover/sidebar-btn:bg-background",
  );
}

function badgeVariantForHealth(status: SystemHealthRow["status"] | "unknown") {
  if (status === "healthy") return "success" as const;
  if (status === "degraded") return "warning" as const;
  if (status === "blocked") return "danger" as const;
  return "muted" as const;
}

function formatRunMeta(run: RunRow): string {
  return [run.status ?? "unknown", run.current_date ?? run.scheduled_date]
    .filter(Boolean)
    .join(" · ");
}

function runDecisionCount(run: RunRow): string {
  const payload = run.payload;
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const total = payload.total_decision_count;
    if (typeof total === "number" && Number.isFinite(total)) {
      return String(total);
    }
    const recordCount = payload.record_count;
    if (typeof recordCount === "number" && Number.isFinite(recordCount)) {
      return String(recordCount);
    }
  }
  return "n/a";
}

function setOrDelete(params: URLSearchParams, key: string, value: string) {
  if (value) {
    params.set(key, value);
  } else {
    params.delete(key);
  }
}

function includeActiveOption(options: string[], active: string): string[] {
  if (!active || options.includes(active)) {
    return options;
  }
  return [active, ...options];
}

function formatResultSummary(view: DecisionListViewModel): string {
  if (view.filteredCount === 0) {
    return "Showing 0 of 0 decisions";
  }
  return `Showing ${view.from}-${view.to} of ${view.filteredCount} decisions`;
}

const selectClassName =
  "h-10 min-h-10 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
