"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, CircleHelp } from "lucide-react";
import { cn } from "@/lib/utils";

/** Trend state pill. Pulses ONCE on flip days (days_in_state === 1) — motion
 * conveys the state change, never loops. */
export function TrendPill({
  trendOn,
  daysInState,
}: {
  trendOn: boolean | null;
  daysInState?: number;
}) {
  const flipped = daysInState === 1;
  const label =
    trendOn === null ? "Unknown" : trendOn ? "In uptrend" : "Below trend";
  const Icon = trendOn === null ? CircleHelp : trendOn ? TrendingUp : TrendingDown;
  return (
    <motion.span
      initial={flipped ? { scale: 0.9 } : false}
      animate={flipped ? { scale: [0.9, 1.06, 1] } : {}}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        trendOn === null && "border-white/10 text-text-3",
        trendOn === true && "border-up/25 bg-up/[0.07] text-up",
        trendOn === false && "border-white/15 bg-white/[0.04] text-text-2",
      )}
    >
      <Icon aria-hidden size={12} />
      {label}
      {daysInState != null && (
        <span className="tnum text-text-3">· {daysInState}d</span>
      )}
    </motion.span>
  );
}
