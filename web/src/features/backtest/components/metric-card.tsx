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
      </div>
    </Card>
  );
}
