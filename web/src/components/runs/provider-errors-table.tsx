import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import type { ProviderErrorRow } from "@/lib/runs/schemas";

export function ProviderErrorsTable({ errors }: { errors: ProviderErrorRow[] }) {
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold">Provider errors</h2>
      <Table>
        <thead>
          <tr>
            <Th>Provider</Th>
            <Th>Type</Th>
            <Th>Target</Th>
            <Th>Message</Th>
            <Th>Created</Th>
          </tr>
        </thead>
        <tbody>
          {errors.map((error) => (
            <tr key={error.providerErrorId}>
              <Td className="font-medium">{error.provider}</Td>
              <Td>
                <Badge variant="warning">{error.errorType}</Badge>
              </Td>
              <Td>{error.target ?? "-"}</Td>
              <Td>{error.message}</Td>
              <Td className="whitespace-nowrap font-mono text-xs">{error.createdAt}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
