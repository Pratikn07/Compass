"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { EquityCurvePoint } from "@/features/backtest/lib/backtest-view-model";

export function EquityCurveChart({ data }: { data: EquityCurvePoint[] }) {
  return (
    <Card className="grid gap-4">
      <div>
        <h2 className="text-base font-semibold">Equity curve</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Strategy equity against the matched buy-and-hold benchmark.
        </p>
      </div>
      {data.length > 1 ? (
        <div
          aria-label="Equity curve chart comparing strategy equity and buy-and-hold equity"
          className="h-72"
          role="img"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} accessibilityLayer margin={{ left: 8, right: 8 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="label"
                tickLine={false}
                tickMargin={8}
                stroke="var(--muted-foreground)"
              />
              <YAxis
                tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
                tickLine={false}
                tickMargin={8}
                stroke="var(--muted-foreground)"
                width={82}
              />
              <Tooltip
                formatter={(value, name) => [
                  `$${Number(value ?? 0).toLocaleString()}`,
                  name ?? "Value",
                ]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ""}
              />
              <Legend />
              <Line
                dataKey="strategyEquity"
                dot={{ r: 3 }}
                name="Strategy equity"
                stroke="var(--primary)"
                strokeWidth={2}
                type="monotone"
              />
              <Line
                dataKey="buyHoldEquity"
                dot={{ r: 3 }}
                name="Buy-and-hold equity"
                stroke="var(--warning)"
                strokeWidth={2}
                type="monotone"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="rounded-card border border-dashed border-border p-6 text-sm text-muted-foreground">
          No evaluable equity observations.
        </p>
      )}
    </Card>
  );
}
