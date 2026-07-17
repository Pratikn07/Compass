"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Cascade, Rise } from "@/components/motion";
import { TrendPill } from "@/components/trend-pill";
import { CountUp } from "@/components/count-up";
import { IndexChart } from "@/components/index-chart";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";

export default function ThemeDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const { data, error, retry } = useApi(() => api.themeDetail(slug), [slug]);

  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const latest = data.state_history.at(-1) ?? null;
  const lastFlip = [...data.state_history]
    .reverse()
    .find((s) => s.days_in_state === 1);

  return (
    <Cascade className="flex flex-col gap-6">
      <Rise>
        <Link
          href="/themes"
          className="inline-flex items-center gap-1.5 text-sm text-text-3 transition-colors hover:text-text-2"
        >
          <ArrowLeft aria-hidden size={14} /> Themes
        </Link>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
          <TrendPill
            trendOn={latest?.trend_on ?? null}
            daysInState={latest?.days_in_state}
          />
        </div>
        <p className="tnum mt-1 text-sm text-text-3">
          {data.etf_ticker
            ? `Tracked via ${data.etf_ticker}`
            : "Basket only (hindsight-curated; no faithful ETF)"}
          {lastFlip && ` · last trend flip ${formatDate(lastFlip.d)}`}
        </p>
      </Rise>

      <Rise>
        <section className="glass p-5">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <p className="text-xs text-text-3">Index level</p>
              <p className="text-2xl font-semibold">
                {latest ? <CountUp value={latest.index_level} /> : "—"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-text-3">200-day average</p>
              <p className="tnum text-2xl font-semibold text-text-2">
                {latest?.sma200?.toFixed(2) ?? "—"}
              </p>
            </div>
          </div>
          <IndexChart history={data.state_history} />
          <p className="mt-3 flex items-center gap-4 text-xs text-text-3">
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="h-0.5 w-4 rounded bg-accent-a" /> Index
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="h-0.5 w-4 rounded bg-accent-b" /> SMA 200
            </span>
          </p>
        </section>
      </Rise>

      <Rise>
        <section className="glass overflow-hidden">
          <h2 className="border-b border-white/[0.06] px-5 py-3 text-sm font-medium text-text-2">
            Members ({data.members.length})
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-3">
                  <th className="px-5 py-2 font-medium">Ticker</th>
                  <th className="px-5 py-2 font-medium">Member since</th>
                  <th className="px-5 py-2 font-medium">Why it belongs</th>
                </tr>
              </thead>
              <tbody>
                {data.members.map((m) => (
                  <tr
                    key={m.ticker}
                    className="border-t border-white/[0.04] transition-colors hover:bg-white/[0.02]"
                  >
                    <td className="tnum px-5 py-2.5 font-medium">{m.ticker}</td>
                    <td className="tnum px-5 py-2.5 text-text-2">
                      {formatDate(m.member_since)}
                    </td>
                    <td className="px-5 py-2.5 text-text-3">{m.justification}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </Rise>
    </Cascade>
  );
}
