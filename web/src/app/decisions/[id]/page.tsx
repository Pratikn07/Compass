"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileSearch } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function DecisionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, retry } = useApi(() => api.decision(id), [id]);
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <Skeleton className="h-96 w-full" />;
  const { decision, journal } = data;

  return (
    <section className="space-y-6">
      <header>
        <Link href="/decisions" className="inline-flex items-center gap-1 text-sm text-text-3">
          <ArrowLeft aria-hidden size={14} /> Decisions
        </Link>
        <h1 className="mt-3 text-2xl font-semibold">{decision.instrument}</h1>
        <p className="tnum mt-1 text-sm text-text-3">
          {formatDate(decision.decision_date)} · {decision.action.replaceAll("_", " ")}
        </p>
      </header>
      <article className="glass p-5">
        <h2 className="flex items-center gap-2 text-sm font-medium text-text-2">
          <FileSearch aria-hidden size={16} /> Theme evidence and recommendation
        </h2>
        <pre className="mt-4 overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-text-2">
          {JSON.stringify(decision.reasoning, null, 2)}
        </pre>
      </article>
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-text-2">Journal chain</h2>
        {journal.length === 0 ? (
          <div className="glass p-6 text-sm text-text-3">No linked journal records.</div>
        ) : journal.map((record) => (
          <article key={record.journal_record_id} className="glass flex gap-3 p-4">
            <CheckCircle2 aria-hidden size={16} className="mt-0.5 text-accent-a" />
            <div>
              <p className="text-sm">{record.record_type.replaceAll("_", " ")}</p>
              <p className="tnum mt-1 text-xs text-text-3">
                {formatDate(record.trading_date)} · {record.source}
              </p>
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}
