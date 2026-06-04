import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  Shield,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { OperatorStatus } from "@/lib/operator/schemas";
import type { RunRow } from "@/lib/runs/schemas";

function badgeForState(state: string) {
  if (["active", "blocked", "halted", "failed"].includes(state)) {
    return "danger" as const;
  }
  if (["completed", "inactive", "allowed", "accepted"].includes(state)) {
    return "success" as const;
  }
  if (["paper", "warning", "partial"].includes(state)) {
    return "warning" as const;
  }
  return "muted" as const;
}

function SummaryCard({
  children,
  icon,
  label,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted text-muted-foreground">
          {icon}
        </span>
        <span>{label}</span>
      </div>
      <div className="mt-3 grid gap-2">{children}</div>
    </Card>
  );
}

export function RunsSummaryCards({
  dailyHalt,
  latestRun,
  operatorStatus,
  providerErrorCount,
}: {
  dailyHalt: { status: "allowed" | "halted"; createdAt: string | null };
  latestRun: RunRow | null;
  operatorStatus: OperatorStatus;
  providerErrorCount: number;
}) {
  const killSwitchActive = operatorStatus.killSwitch.status === "active";

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <SummaryCard
        icon={
          killSwitchActive ? (
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          )
        }
        label="Kill switch"
      >
        <Badge variant={badgeForState(operatorStatus.killSwitch.status)}>
          {operatorStatus.killSwitch.status}
        </Badge>
        <p className="text-xs text-muted-foreground">
          {operatorStatus.killSwitch.reason ?? "No active kill switch reason"}
        </p>
      </SummaryCard>

      <SummaryCard
        icon={<Shield className="h-4 w-4" aria-hidden="true" />}
        label="Execution mode"
      >
        <span className="font-mono text-base font-semibold text-foreground">
          {operatorStatus.executionMode}
        </span>
        <p className="text-xs text-muted-foreground">
          Source: {operatorStatus.modeSource}
        </p>
      </SummaryCard>

      <SummaryCard
        icon={
          dailyHalt.status === "halted" ? (
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          )
        }
        label="Daily halt"
      >
        <Badge variant={badgeForState(dailyHalt.status)}>{dailyHalt.status}</Badge>
        <p className="text-xs text-muted-foreground">
          {dailyHalt.createdAt ?? "No halt record found"}
        </p>
      </SummaryCard>

      <SummaryCard icon={<Clock className="h-4 w-4" aria-hidden="true" />} label="Latest run">
        <span className="break-all font-mono text-sm">
          {latestRun?.runId ?? "No runs yet"}
        </span>
        <div className="flex items-center gap-2">
          <Badge variant={badgeForState(latestRun?.status ?? "empty")}>
            {latestRun?.status ?? "empty"}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {latestRun?.createdAt ?? "No timestamp"}
          </span>
        </div>
      </SummaryCard>

      <div className="md:col-span-2 xl:col-span-4">
        <div className="flex items-center gap-2 rounded-card border border-border bg-card px-4 py-3 text-sm">
          <Database className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <span className="font-medium">Recent provider errors</span>
          <Badge variant={providerErrorCount > 0 ? "warning" : "success"}>
            {providerErrorCount}
          </Badge>
        </div>
      </div>
    </div>
  );
}
