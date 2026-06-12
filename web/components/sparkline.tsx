"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId, useMemo } from "react";

/** Pure-SVG sparkline with a draw-in stroke and gradient area fill.
 * Decorative (aria-hidden); the figures next to it carry the meaning. */
export function Sparkline({
  values,
  width = 120,
  height = 36,
  positive = true,
}: {
  values: number[];
  width?: number;
  height?: number;
  positive?: boolean;
}) {
  const id = useId();
  const reduced = useReducedMotion();

  const { line, area } = useMemo(() => {
    if (values.length < 2) return { line: "", area: "" };
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const pts = values.map((v, i) => [
      (i / (values.length - 1)) * width,
      height - 3 - ((v - min) / span) * (height - 6),
    ]);
    const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const area = `${line} L${width},${height} L0,${height} Z`;
    return { line, area };
  }, [values, width, height]);

  if (!line) return <div style={{ width, height }} aria-hidden />;

  const stroke = positive ? "var(--up)" : "var(--text-3)";

  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.18} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id}-fill)`} />
      <motion.path
        d={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.9, ease: "easeOut" }}
      />
    </svg>
  );
}
