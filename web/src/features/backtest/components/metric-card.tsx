import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { BacktestMetric } from "@/features/backtest/lib/backtest-view-model";

const badgeVariantByTone = {
  danger: "danger",
  muted: "muted",
  success: "success",
  warning: "warning",
} as const;

export function MetricCard({ metric }: { metric: BacktestMetric }) {
  return (
    <Card className="grid min-h-32 gap-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{metric.label}</p>
        <Badge variant={badgeVariantByTone[metric.tone]}>{metric.tone}</Badge>
      </div>
      <div>
        <p className="font-mono text-2xl font-semibold leading-none">
          {metric.value}
        </p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          {metric.detail}
        </p>
        <p className="mt-2 font-mono text-xs text-foreground">
          {metric.comparison}
        </p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {metric.verification}
        </p>
      </div>
      <Sparkline values={metric.sparkline} />
    </Card>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) {
    return (
      <div className="h-8 rounded-sm border border-dashed border-border bg-muted/20" />
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 120;
  const height = 32;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      aria-hidden="true"
      className="h-8 w-full text-primary"
      focusable="false"
      preserveAspectRatio="none"
      viewBox={`0 0 ${width} ${height}`}
    >
      <polyline
        fill="none"
        points={points}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}
