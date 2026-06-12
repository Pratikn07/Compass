"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight, ArrowDownRight, Check, ChevronDown } from "lucide-react";
import { api, type Recommendation } from "@/lib/api";
import { cn, formatPct } from "@/lib/utils";

/** A "consider" card — the ONLY place the accent gradient appears.
 * The base rate and the honesty line are always visible, never tucked away. */
export function RecommendationCard({ rec }: { rec: Recommendation }) {
  const [acked, setAcked] = useState(rec.acknowledged_at != null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const enter = rec.action === "consider_enter";
  const r = rec.reasoning as {
    tercile?: string;
    rank?: number;
    of?: number;
    theme_score?: number;
    etf?: string | null;
    claim?: string;
    dev_top_beats_bottom?: string;
    validation_top_beats_bottom?: string;
    as_of_quarter_end?: string;
  };

  async function ack() {
    setBusy(true);
    try {
      await api.acknowledge(rec.id);
      setAcked(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.article
      layout
      className={cn("glass accent-ring relative overflow-hidden p-5")}
      data-testid="recommendation-card"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium accent-text">
            {enter ? (
              <ArrowUpRight aria-hidden size={16} className="text-accent-a" />
            ) : (
              <ArrowDownRight aria-hidden size={16} className="text-accent-b" />
            )}
            {enter ? "Consider entering" : "Consider reducing"}
          </p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">
            {rec.instrument}
            {r.etf && (
              <span className="ml-2 text-sm font-normal text-text-3">
                via {r.etf}
              </span>
            )}
          </h3>
          <p className="mt-1 text-sm text-text-2">
            Ranked <span className="tnum">{r.rank}</span> of{" "}
            <span className="tnum">{r.of}</span> themes by reported
            fundamentals · {r.tercile} tercile
          </p>
        </div>
        <button
          onClick={ack}
          disabled={acked || busy}
          aria-label={acked ? "Acknowledged" : "Acknowledge recommendation"}
          className={cn(
            "flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-lg border px-3 text-sm transition-all duration-200 active:scale-[0.97]",
            acked
              ? "border-up/30 text-up"
              : "cursor-pointer border-white/15 text-text-2 hover:border-white/30 hover:text-text-1",
          )}
        >
          <Check aria-hidden size={14} />
          {acked ? "Seen" : "Acknowledge"}
        </button>
      </div>

      {/* the honesty line — non-negotiable, always visible */}
      <p className="mt-4 border-t border-white/[0.06] pt-3 text-[13px] leading-relaxed text-text-3">
        Base rate {formatPct(rec.base_rate)}: top beat bottom in{" "}
        {r.dev_top_beats_bottom} in development and{" "}
        {r.validation_top_beats_bottom} in validation. The edge is in average
        magnitude, not per-quarter consistency.
      </p>

      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="mt-2 flex cursor-pointer items-center gap-1 text-xs text-text-3 transition-colors hover:text-text-2"
      >
        <ChevronDown
          aria-hidden
          size={12}
          className={cn("transition-transform duration-200", open && "rotate-180")}
        />
        Full reasoning
      </button>
      {open && (
        <motion.pre
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 overflow-x-auto rounded-lg bg-black/30 p-3 text-xs leading-relaxed text-text-2"
        >
          {JSON.stringify(rec.reasoning, null, 2)}
        </motion.pre>
      )}
    </motion.article>
  );
}
