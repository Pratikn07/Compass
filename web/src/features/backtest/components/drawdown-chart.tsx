"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type {
  BacktestDisplayMode,
  DrawdownCurvePoint,
} from "@/features/backtest/lib/backtest-view-model";

export function DrawdownChart({
  data,
  mode,
}: {
  data: DrawdownCurvePoint[];
  mode: BacktestDisplayMode;
}) {
  const dataKey = mode === "percent" ? "drawdownPct" : "drawdownDollars";

  return (
    <Card className="grid gap-4">
      <div>
        <h2 className="text-base font-semibold">Drawdown</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Running peak-to-trough drawdown derived from strategy equity.
        </p>
      </div>
      {data.length > 1 ? (
        <div
          aria-label="Drawdown area chart derived from strategy equity"
          className="h-64"
          role="img"
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} accessibilityLayer margin={{ left: 8, right: 8 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="label"
                tickLine={false}
                tickMargin={8}
                stroke="var(--muted-foreground)"
              />
              <YAxis
                tickFormatter={(value) => formatChartValue(Number(value), mode)}
                tickLine={false}
                tickMargin={8}
                stroke="var(--muted-foreground)"
                width={72}
              />
              <Tooltip
                formatter={(value) => [
                  formatChartValue(Number(value ?? 0), mode),
                  "Drawdown",
                ]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ""}
              />
              <Area
                dataKey={dataKey}
                fill="var(--danger)"
                fillOpacity={0.18}
                name="Drawdown"
                stroke="var(--danger)"
                strokeWidth={2}
                type="monotone"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="rounded-card border border-dashed border-border p-6 text-sm text-muted-foreground">
          No evaluable drawdown observations.
        </p>
      )}
    </Card>
  );
}

function formatChartValue(value: number, mode: BacktestDisplayMode): string {
  if (mode === "percent") {
    return `${value.toFixed(2)}%`;
  }
  return `$${value.toLocaleString()}`;
}
