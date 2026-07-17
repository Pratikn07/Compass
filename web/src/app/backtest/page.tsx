"use client";

import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function BacktestPage() {
  const { data, error, retry } = useApi(() => api.backtest());
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <Skeleton className="h-96 w-full" />;
  const scorecards = Object.entries(data.payload.scorecards ?? {});

  return (
    <section className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <FlaskConical aria-hidden size={20} className="text-text-3" /> Backtest
        </h1>
        <p className="mt-1 text-sm text-text-3">
          Latest read-only edge report · {formatDate(data.report_date)} · {data.payload.contexts_evaluated ?? 0} contexts
        </p>
      </header>
      {scorecards.length === 0 ? (
        <div className="glass p-10 text-center text-sm text-text-2">No evaluable backtest contexts yet.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {scorecards.map(([name, card]) => (
            <article key={name} className="glass p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-medium">{name.replaceAll("_", " ")}</h2>
                <span className="text-xs text-text-3">{card.sample_size_verdict}</span>
              </div>
              <dl className="tnum mt-4 grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs text-text-3">Events</dt><dd>{card.events_evaluable}</dd></div>
                <div><dt className="text-xs text-text-3">Directional hit</dt><dd>{card.directional_hit_rate ?? "—"}</dd></div>
                <div><dt className="text-xs text-text-3">Average return</dt><dd>{card.average_option_return_pct ?? "—"}</dd></div>
                <div><dt className="text-xs text-text-3">Survived</dt><dd>{card.survived == null ? "baseline" : card.survived ? "yes" : "no"}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      )}
      <p className="text-xs text-text-3">Research only. Execution is disabled structurally.</p>
    </section>
  );
}
