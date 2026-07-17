"use client";

import Link from "next/link";
import { ListChecks } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function DecisionsPage() {
  const { data, error, retry } = useApi(() => api.decisions());
  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <Skeleton className="h-80 w-full" />;

  return (
    <section className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <ListChecks aria-hidden size={20} className="text-text-3" /> Decisions
        </h1>
        <p className="mt-1 text-sm text-text-3">
          Theme evidence and the recommendations it produced. No execution proposals.
        </p>
      </header>
      {data.items.length === 0 ? (
        <div className="glass p-10 text-center text-sm text-text-2">No decisions have been generated yet.</div>
      ) : (
        <div className="glass overflow-hidden">
          {data.items.map((decision) => (
            <Link
              key={decision.decision_id}
              href={`/decisions/${decision.decision_id}`}
              className="flex items-center justify-between gap-4 border-b border-white/[0.06] p-4 last:border-0 hover:bg-white/[0.03]"
            >
              <div>
                <p className="font-medium">{decision.instrument}</p>
                <p className="tnum mt-1 text-xs text-text-3">
                  {formatDate(decision.decision_date)} · {decision.hypothesis}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-text-2">{decision.action.replaceAll("_", " ")}</p>
                <p className="mt-1 text-xs text-text-3">{decision.attention_status}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
