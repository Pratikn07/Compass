import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import type { StorageAuditRow } from "@/lib/runs/schemas";

export function StorageAuditTable({ rows }: { rows: StorageAuditRow[] }) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Storage writes</h2>
      <Table>
        <thead>
          <tr>
            <Th>Provider</Th>
            <Th>Table</Th>
            <Th>Attempted</Th>
            <Th>Written</Th>
            <Th>Errors</Th>
            <Th>Created</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.storageWriteAuditId}>
              <Td className="font-medium">{row.provider}</Td>
              <Td>{row.tableName}</Td>
              <Td>{row.attemptedRecordCount}</Td>
              <Td>{row.writtenRecordCount}</Td>
              <Td>
                <Badge variant={row.errorCount > 0 ? "warning" : "success"}>
                  {row.errorCount}
                </Badge>
              </Td>
              <Td className="whitespace-nowrap font-mono text-xs">{row.createdAt}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
