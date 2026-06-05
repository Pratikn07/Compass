import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import type { RecentRunDisplayRow } from "@/lib/runs/status-view-model";

function badgeForRunStatus(status: string) {
  const normalized = status.toLowerCase();
  if (["failed", "error", "halted", "blocked"].includes(normalized)) {
    return "danger" as const;
  }
  if (["completed", "recorded", "success"].includes(normalized)) {
    return "success" as const;
  }
  if (["partial", "running", "pending"].includes(normalized)) {
    return "warning" as const;
  }
  return "muted" as const;
}

export function RecentRunsTable({ rows }: { rows: RecentRunDisplayRow[] }) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Recent runs</h2>
      <Table className="min-w-[760px]">
        <thead>
          <tr>
            <Th>Run ID</Th>
            <Th>Trigger</Th>
            <Th>Start time</Th>
            <Th>Status</Th>
            <Th>Decision records</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.runId}>
              <Td className="break-all font-mono text-xs font-medium">
                {row.runId}
              </Td>
              <Td>{row.triggerType ?? "unknown"}</Td>
              <Td className="whitespace-nowrap font-mono text-xs">
                {row.createdAt}
              </Td>
              <Td>
                <Badge dot variant={badgeForRunStatus(row.status)}>
                  {row.status}
                </Badge>
              </Td>
              <Td className="font-mono text-xs">{row.decisionCountLabel}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
