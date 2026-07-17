"use client";

import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef } from "react";

/** Spring-settled count-up with tabular numerals (no width jitter). */
export function CountUp({
  value,
  decimals = 2,
  suffix = "",
  className,
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (reduced) {
      node.textContent = `${value.toFixed(decimals)}${suffix}`;
      return;
    }
    const controls = animate(0, value, {
      type: "spring",
      stiffness: 80,
      damping: 22,
      onUpdate: (v) => {
        node.textContent = `${v.toFixed(decimals)}${suffix}`;
      },
    });
    return () => controls.stop();
  }, [value, decimals, suffix, reduced]);

  return <span ref={ref} className={`tnum ${className ?? ""}`} />;
}
