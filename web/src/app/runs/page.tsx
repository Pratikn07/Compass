"use client";

import { Activity } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function RunsPage() {
  const { data, error, retry } = useApi(() =>
    Promise.all([api.runs(), api.providers(), api.systemHealth()]),
  );
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <Skeleton className="h-96 w-full" />;
  const [runs, providers, health] = data;
  const expected = ["api", "database", "nightly_worker", "provider_health", "storage", "backtest_engine"];
  const byComponent = new Map(health.map((component) => [component.component, component]));

  return (
    <section className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Activity aria-hidden size={20} className="text-text-3" /> Runs
        </h1>
        <p className="mt-1 text-sm text-text-3">API, database, worker, providers, storage, and research health.</p>
      </header>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {expected.map((name) => {
          const component = byComponent.get(name);
          const status = name === "api" && !component ? "healthy" : component?.status ?? "unknown";
          return (
            <article key={name} className="glass p-4">
              <p className="text-xs uppercase tracking-wide text-text-3">{name.replaceAll("_", " ")}</p>
              <p className="mt-2 text-sm">{status}</p>
              {component?.detail && <p className="mt-1 text-xs text-text-3">{component.detail}</p>}
            </article>
          );
        })}
      </div>
      {providers.recent_errors.length > 0 && (
        <div role="alert" className="glass border-alert/30 p-4 text-sm text-alert">
          {providers.recent_errors.length} recent provider error{providers.recent_errors.length > 1 ? "s" : ""}; unaffected providers remain available.
        </div>
      )}
      <div className="glass overflow-hidden">
        {runs.items.length === 0 ? (
          <p className="p-8 text-center text-sm text-text-2">No persisted runs yet.</p>
        ) : runs.items.map((run) => (
          <article key={run.run_id} className="flex justify-between gap-4 border-b border-white/[0.06] p-4 last:border-0">
            <div><p className="text-sm">{run.run_id}</p><p className="tnum mt-1 text-xs text-text-3">{formatDate(run.scheduled_date)}</p></div>
            <span className="text-sm text-text-2">{run.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
