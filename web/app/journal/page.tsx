"use client";

import { BookOpen, Check, ShieldAlert } from "lucide-react";
import { api, type Override, type Recommendation } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Cascade, Rise } from "@/components/motion";
import { OverrideForm } from "@/components/override-form";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

type Entry =
  | { kind: "rec"; date: string; rec: Recommendation }
  | { kind: "override"; date: string; override: Override };

export default function JournalPage() {
  const { data, error, retry } = useApi(() => api.journal());

  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  const entries: Entry[] = [
    ...data.recommendations.map((rec) => ({
      kind: "rec" as const,
      date: rec.d,
      rec,
    })),
    ...data.overrides.map((override) => ({
      kind: "override" as const,
      date: override.ts.slice(0, 10),
      override,
    })),
  ].sort((a, b) => (a.date < b.date ? 1 : -1));

  return (
    <Cascade className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="flex flex-col gap-4">
        <Rise>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BookOpen aria-hidden size={20} className="text-text-3" />
            Journal
          </h1>
          <p className="mt-1 text-sm text-text-3">
            Last {entries.length} entries · what compass said, what you saw,
            what you did.
          </p>
        </Rise>

        {entries.length === 0 ? (
          <Rise>
            <div className="glass p-8 text-center">
              <p className="text-sm text-text-2">No overrides recorded.</p>
              <p className="mt-1 text-xs text-text-3">
                The plan is being followed. That is the firewall holding.
              </p>
            </div>
          </Rise>
        ) : (
          entries.map((entry) => (
            <Rise
              key={
                entry.kind === "rec"
                  ? `r-${entry.rec.id}`
                  : `o-${entry.override.id}`
              }
            >
              {entry.kind === "rec" ? (
                <div className="glass flex items-start justify-between gap-4 p-4">
                  <div>
                    <p className="tnum text-xs text-text-3">
                      {formatDate(entry.date)}
                    </p>
                    <p className="mt-1 text-sm">
                      {entry.rec.action === "none" ? (
                        <span className="text-text-2">
                          Nothing to do — recorded, on purpose
                        </span>
                      ) : (
                        <>
                          <span className="font-medium">
                            {entry.rec.action === "consider_enter"
                              ? "Consider entering"
                              : "Consider reducing"}
                          </span>{" "}
                          {entry.rec.instrument}
                        </>
                      )}
                    </p>
                  </div>
                  {entry.rec.acknowledged_at ? (
                    <span className="flex items-center gap-1 text-xs text-up">
                      <Check aria-hidden size={12} /> seen
                    </span>
                  ) : (
                    <span className="text-xs text-text-3">unseen</span>
                  )}
                </div>
              ) : (
                <div className="glass border-l-2 border-l-accent-b/40 p-4">
                  <p className="tnum flex items-center gap-2 text-xs text-text-3">
                    <ShieldAlert aria-hidden size={12} />
                    Override · {formatDate(entry.date)}
                  </p>
                  <p className="mt-1 text-sm">{entry.override.what}</p>
                  <p className="mt-1 text-xs italic text-text-3">
                    &ldquo;{entry.override.reason}&rdquo;
                  </p>
                </div>
              )}
            </Rise>
          ))
        )}
      </div>

      <Rise>
        <OverrideForm onCreated={retry} />
      </Rise>
    </Cascade>
  );
}
