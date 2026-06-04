"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { OutcomeDistributionPoint } from "@/features/backtest/lib/backtest-view-model";

export function OutcomeDistributionChart({
  data,
}: {
  data: OutcomeDistributionPoint[];
}) {
  return (
    <Card className="grid gap-4">
      <div>
        <h2 className="text-base font-semibold">Outcome distribution</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Closed trade outcomes including non-evaluable observations.
        </p>
      </div>
      <div aria-label="Outcome distribution bar chart" className="h-72" role="img">
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
              allowDecimals={false}
              tickLine={false}
              tickMargin={8}
              stroke="var(--muted-foreground)"
              width={44}
            />
            <Tooltip formatter={(value) => [Number(value ?? 0), "Setups"]} />
            <Bar
              dataKey="count"
              fill="var(--success)"
              name="Outcome count"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
