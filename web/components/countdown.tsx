"use client";

import { useEffect, useState } from "react";

/** Live cooling-off countdown (HH:MM:SS, tabular). */
export function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const ms = new Date(until).getTime() - now;
  if (ms <= 0) return <span className="tnum text-up">clock elapsed</span>;

  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  const pad = (n: number) => String(n).padStart(2, "0");

  return (
    <span className="tnum" aria-label={`${h} hours ${m} minutes remaining`}>
      {pad(h)}:{pad(m)}:{pad(s)}
    </span>
  );
}
