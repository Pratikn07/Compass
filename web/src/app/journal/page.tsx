"use client";

import { BookOpen, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Cascade, Rise } from "@/components/motion";
import { OverrideForm } from "@/components/override-form";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function JournalPage() {
  const { data, error, retry } = useApi(() => api.journal());
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) {
    return <div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-72" /></div>;
  }

  return (
    <Cascade className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="flex flex-col gap-4">
        <Rise>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BookOpen aria-hidden size={20} className="text-text-3" /> Journal
          </h1>
          <p className="mt-1 text-sm text-text-3">
            Evidence, recommendations, acknowledgements, overrides, and rule changes.
          </p>
        </Rise>
        {data.records.length === 0 && data.overrides.length === 0 ? (
          <Rise><div className="glass p-8 text-center text-sm text-text-2">No journal records yet.</div></Rise>
        ) : (
          <>
            {data.records.map((record) => (
              <Rise key={record.journal_record_id}>
                <article className="glass p-4">
                  <p className="tnum text-xs text-text-3">
                    {formatDate(record.trading_date)} · {record.record_type}
                  </p>
                  <p className="mt-1 text-sm">{record.target ?? record.theme ?? "Compass"}</p>
                  <p className="mt-1 text-xs text-text-3">Source: {record.source}</p>
                </article>
              </Rise>
            ))}
            {data.overrides.map((override) => (
              <Rise key={`override-${override.id}`}>
                <article className="glass border-l-2 border-l-accent-b/40 p-4">
                  <p className="tnum flex items-center gap-2 text-xs text-text-3">
                    <ShieldAlert aria-hidden size={12} /> Override · {formatDate(override.ts)}
                  </p>
                  <p className="mt-1 text-sm">{override.what}</p>
                  <p className="mt-1 text-xs italic text-text-3">“{override.reason}”</p>
                </article>
              </Rise>
            ))}
          </>
        )}
      </div>
      <Rise><OverrideForm onCreated={retry} /></Rise>
    </Cascade>
  );
}
