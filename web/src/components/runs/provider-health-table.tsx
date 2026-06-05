import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import type {
  ProviderHealthDisplayRow,
  ProviderHealthStatus,
} from "@/lib/runs/status-view-model";

export function ProviderHealthTable({
  rows,
}: {
  rows: ProviderHealthDisplayRow[];
}) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Provider health</h2>
      <Table className="min-w-[860px]">
        <thead>
          <tr>
            <Th>Provider</Th>
            <Th>Status</Th>
            <Th>Requests</Th>
            <Th>Cache hits</Th>
            <Th>Cache misses</Th>
            <Th>Retries</Th>
            <Th>Errors</Th>
            <Th>Budget</Th>
            <Th>Last success</Th>
            <Th>Warnings</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.provider}>
              <Td className="font-medium">{row.provider}</Td>
              <Td>
                <Badge dot variant={badgeForProviderHealth(row.status)}>
                  {statusLabel(row.status)}
                </Badge>
              </Td>
              <Td>{row.requests}</Td>
              <Td>{row.cacheHits}</Td>
              <Td>{row.cacheMisses}</Td>
              <Td>{row.retries}</Td>
              <Td>
                <Badge variant={row.errors > 0 ? "warning" : "success"}>
                  {row.errors}
                </Badge>
              </Td>
              <Td className="whitespace-nowrap font-mono text-xs">
                {row.budgetLabel}
              </Td>
              <Td className="whitespace-nowrap font-mono text-xs">
                {row.lastSuccessAt ?? "-"}
              </Td>
              <Td className="max-w-[220px] text-xs text-muted-foreground">
                {row.warnings.length ? row.warnings.join(" ") : "-"}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function badgeForProviderHealth(status: ProviderHealthStatus) {
  if (status === "blocked") return "danger" as const;
  if (status === "degraded") return "warning" as const;
  if (status === "healthy") return "success" as const;
  return "muted" as const;
}

function statusLabel(status: ProviderHealthStatus) {
  if (status === "blocked") return "Blocked";
  if (status === "degraded") return "Degraded";
  if (status === "healthy") return "Healthy";
  return "Unknown";
}
