"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/** One conductor for entrances: fade + 8px rise on a spring, with stagger
 * orchestrated by the parent. Collapses to opacity for reduced motion. */

const spring = { type: "spring" as const, stiffness: 260, damping: 24 };

export function Cascade({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
    >
      {children}
    </motion.div>
  );
}

export function Rise({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: reduced ? 0 : 8 },
        show: { opacity: 1, y: 0, transition: spring },
      }}
    >
      {children}
    </motion.div>
  );
}

export function PressScale({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div whileTap={{ scale: 0.97 }} transition={spring} className={className}>
      {children}
    </motion.div>
  );
}
