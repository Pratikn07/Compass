"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { ReturnComparisonPoint } from "@/features/backtest/lib/backtest-view-model";

export function ReturnComparisonChart({
  data,
}: {
  data: ReturnComparisonPoint[];
}) {
  return (
    <Card className="grid gap-4">
      <div>
        <h2 className="text-base font-semibold">Return comparison</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Strategy, benchmark, and excess return from the persisted report.
        </p>
      </div>
      <div
        aria-label="Return comparison bar chart for strategy, buy-and-hold, and excess return"
        className="h-72"
        role="img"
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} accessibilityLayer margin={{ left: 8, right: 8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              tickLine={false}
              tickMargin={8}
              stroke="var(--muted-foreground)"
            />
            <YAxis
              tickFormatter={(value) => `${value}%`}
              tickLine={false}
              tickMargin={8}
              stroke="var(--muted-foreground)"
              width={64}
            />
            <Tooltip
              formatter={(value) => [`${Number(value ?? 0).toFixed(2)}%`, "Return"]}
            />
            <ReferenceLine stroke="var(--foreground)" strokeOpacity={0.45} y={0} />
            <Bar
              dataKey="value"
              fill="var(--primary)"
              name="Return percent"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
