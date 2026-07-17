"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { Cascade, Rise } from "@/components/motion";
import { TrendPill } from "@/components/trend-pill";
import { CountUp } from "@/components/count-up";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function ThemesPage() {
  const { data, error, retry } = useApi(() => api.themes());

  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </div>
    );
  }

  return (
    <Cascade className="flex flex-col gap-6">
      <Rise>
        <h1 className="text-2xl font-semibold tracking-tight">Themes</h1>
        <p className="mt-1 text-sm text-text-3">
          Trend states are information only — the word &ldquo;consider&rdquo;
          lives on the Today screen, and only when the evidence earned it.
        </p>
      </Rise>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((theme) => (
          <Rise key={theme.slug}>
            <Link
              href={`/themes/${theme.slug}`}
              className="glass glass-hover block p-5 active:scale-[0.99]"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-medium leading-snug">{theme.name}</h2>
                {theme.etf_ticker && (
                  <span className="tnum shrink-0 rounded-md border border-white/10 px-1.5 py-0.5 text-xs text-text-3">
                    {theme.etf_ticker}
                  </span>
                )}
              </div>
              <div className="mt-4 flex items-end justify-between">
                <div>
                  <p className="text-xs text-text-3">Index level</p>
                  <p className="mt-0.5 text-xl font-semibold">
                    {theme.state ? (
                      <CountUp value={theme.state.index_level} />
                    ) : (
                      "—"
                    )}
                  </p>
                </div>
                <TrendPill
                  trendOn={theme.state?.trend_on ?? null}
                  daysInState={theme.state?.days_in_state}
                />
              </div>
            </Link>
          </Rise>
        ))}
      </div>
    </Cascade>
  );
}
