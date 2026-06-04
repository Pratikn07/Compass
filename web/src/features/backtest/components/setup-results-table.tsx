import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import type { SetupRow } from "@/features/backtest/lib/backtest-view-model";

function badgeVariant(outcome: string) {
  if (outcome === "win") {
    return "success" as const;
  }
  if (outcome === "loss") {
    return "danger" as const;
  }
  if (outcome === "flat") {
    return "warning" as const;
  }
  return "muted" as const;
}

export function SetupResultsTable({ rows }: { rows: SetupRow[] }) {
  return (
    <Card className="grid gap-4 p-0">
      <div className="px-5 pt-5">
        <h2 className="text-base font-semibold">Setup results</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Setup-level outcome and P&L from the latest persisted report.
        </p>
      </div>
      <Table aria-label="Setup-level backtest outcomes">
        <thead>
          <tr>
            <Th>Target</Th>
            <Th>Theme</Th>
            <Th>Window</Th>
            <Th>Expression</Th>
            <Th>Status</Th>
            <Th>Outcome</Th>
            <Th className="text-right">Net P&L</Th>
            <Th className="text-right">Benchmark</Th>
            <Th className="text-right">Warnings</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.setupId}>
              <Td className="font-mono font-medium">{row.target}</Td>
              <Td>{row.theme}</Td>
              <Td className="font-mono text-xs">
                {row.entryDate} / {row.exitDate}
              </Td>
              <Td>{row.expression}</Td>
              <Td>{row.status}</Td>
              <Td>
                <Badge variant={badgeVariant(row.outcome)}>{row.outcome}</Badge>
              </Td>
              <Td className="text-right font-mono">{row.netPnl}</Td>
              <Td className="text-right font-mono">{row.benchmarkReturn}</Td>
              <Td className="text-right font-mono">{row.warningCount}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
