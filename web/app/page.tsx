"use client";

import { motion } from "framer-motion";
import { AlertTriangle, MoonStar } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Cascade, Rise } from "@/components/motion";
import { RecommendationCard } from "@/components/recommendation-card";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function TodayPage() {
  const today = useApi(() => api.today());
  const health = useApi(() => api.health());

  if (today.error) return <ErrorState message={today.error} onRetry={today.retry} />;
  if (!today.data) {
    return (
      <div className="space-y-4 pt-10">
        <Skeleton className="mx-auto h-10 w-72" />
        <Skeleton className="mx-auto h-5 w-48" />
        <Skeleton className="mx-auto mt-8 h-40 w-full max-w-2xl" />
      </div>
    );
  }

  const recs = today.data.recommendations.filter((r) => r.action !== "none");
  const noneRow = today.data.recommendations.find((r) => r.hypothesis === "none");
  const nextRanking = (noneRow?.reasoning as { next_ranking_after?: string })
    ?.next_ranking_after;
  const alerts = health.data?.recent_alerts ?? [];

  return (
    <Cascade className="flex flex-col gap-6">
      {alerts.length > 0 && (
        <Rise>
          <div
            role="alert"
            className="glass flex items-center gap-3 border-alert/30 p-4 text-sm text-alert"
          >
            <AlertTriangle aria-hidden size={16} />
            {alerts.length} data alert{alerts.length > 1 ? "s" : ""} — check the
            nightly run before trusting today&apos;s numbers.
          </div>
        </Rise>
      )}

      <Rise>
        <p className="tnum pt-6 text-center text-xs uppercase tracking-[0.2em] text-text-3">
          {formatDate(today.data.d)} · data through{" "}
          {formatDate(health.data?.latest_price_date)}
        </p>
      </Rise>

      {recs.length === 0 ? (
        /* The calmest, most beautiful screen in the app — by design. */
        <Rise className="relative flex flex-col items-center py-20 text-center">
          <motion.div
            aria-hidden
            className="breathe absolute top-8 h-56 w-56 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(45,212,191,0.14), rgba(139,92,246,0.07) 60%, transparent 75%)",
            }}
          />
          <MoonStar aria-hidden size={28} className="relative text-text-3" />
          <h1 className="relative mt-6 text-4xl font-semibold tracking-tight sm:text-5xl">
            Nothing to do today
          </h1>
          <p className="relative mt-4 max-w-md text-balance text-sm leading-relaxed text-text-2">
            Every theme is being watched. The plan needs no action from you —
            and that is the strategy working, not a gap in it.
          </p>
          {nextRanking && (
            <p className="tnum relative mt-6 text-xs text-text-3">
              Next quarterly ranking after {formatDate(nextRanking)}
            </p>
          )}
        </Rise>
      ) : (
        <>
          <Rise>
            <h1 className="pt-4 text-center text-3xl font-semibold tracking-tight">
              Quarterly ranking is in
            </h1>
            <p className="mt-2 text-center text-sm text-text-2">
              {recs.length} consideration{recs.length > 1 ? "s" : ""}, ranked by
              reported fundamentals. You decide; compass only proposes.
            </p>
          </Rise>
          <div className="mx-auto grid w-full max-w-2xl gap-4">
            {recs.map((rec) => (
              <Rise key={rec.id}>
                <RecommendationCard rec={rec} />
              </Rise>
            ))}
          </div>
        </>
      )}
    </Cascade>
  );
}
