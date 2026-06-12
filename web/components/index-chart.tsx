"use client";

import { useReducedMotion } from "framer-motion";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ThemeState } from "@/lib/api";

/** Theme index vs its 200-day average. Gradient area + draw-in, low-contrast
 * grid, crosshair tooltip with exact values. */
export function IndexChart({ history }: { history: ThemeState[] }) {
  const reduced = useReducedMotion();
  const data = history.map((s) => ({
    d: s.d,
    level: s.index_level,
    sma: s.sma200,
  }));

  return (
    <div className="h-72 w-full" role="img" aria-label="Theme index level versus its 200-day moving average over the recent past">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="levelFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="d"
            tick={{ fill: "#7d808d", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={56}
            tickFormatter={(d: string) => d.slice(0, 7)}
          />
          <YAxis
            tick={{ fill: "#7d808d", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <Tooltip
            cursor={{ stroke: "rgba(255,255,255,0.2)", strokeDasharray: "3 3" }}
            contentStyle={{
              background: "rgba(10,11,14,0.92)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 12,
              fontSize: 12,
              color: "#f4f4f5",
            }}
            formatter={(value, name) => [
              typeof value === "number" ? value.toFixed(3) : "—",
              name === "level" ? "Index" : "SMA 200",
            ]}
          />
          <Area
            type="monotone"
            dataKey="level"
            stroke="#2dd4bf"
            strokeWidth={1.8}
            fill="url(#levelFill)"
            isAnimationActive={!reduced}
            animationDuration={900}
            animationEasing="ease-out"
          />
          <Line
            type="monotone"
            dataKey="sma"
            stroke="#8b5cf6"
            strokeWidth={1.2}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={!reduced}
            animationDuration={900}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
