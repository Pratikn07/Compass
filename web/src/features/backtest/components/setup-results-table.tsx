"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import type {
  BacktestDisplayMode,
  SetupRow,
} from "@/features/backtest/lib/backtest-view-model";

type SortKey =
  | "entryDate"
  | "exitDate"
  | "expression"
  | "holdingDays"
  | "netPnlValue"
  | "outcome"
  | "target"
  | "theme";

const PAGE_SIZES = [5, 10, 25, 50] as const;

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

export function SetupResultsTable({
  mode,
  rows,
}: {
  mode: BacktestDisplayMode;
  rows: SetupRow[];
}) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(10);
  const [sort, setSort] = useState<{ direction: "asc" | "desc"; key: SortKey }>({
    direction: "asc",
    key: "entryDate",
  });
  const sortedRows = useMemo(() => sortRows(rows, sort), [rows, sort]);
  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const boundedPage = Math.min(page, totalPages);
  const startIndex = sortedRows.length === 0 ? 0 : (boundedPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, sortedRows.length);
  const visibleRows = sortedRows.slice(startIndex, endIndex);
  const csvHref = buildCsvHref(sortedRows);
  const pnlHeader = mode === "percent" ? "Realized P&L %" : "Realized P&L $";

  function setSortKey(key: SortKey, defaultDirection: "asc" | "desc" = "asc") {
    setSort((current) => ({
      direction:
        current.key === key
          ? current.direction === "asc"
            ? "desc"
            : "asc"
          : defaultDirection,
      key,
    }));
    setPage(1);
  }

  return (
    <Card className="grid gap-4 p-0">
      <div className="flex flex-col gap-4 px-5 pt-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-base font-semibold">Setup results</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Setup-level outcome and P&L from the latest persisted report.
          </p>
        </div>
        <a
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-border-strong bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm transition-[background-color,box-shadow,transform] duration-150 hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.98]"
          download="backtest-results.csv"
          href={csvHref}
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          Export CSV
        </a>
      </div>
      <Table aria-label="Setup-level backtest outcomes">
        <thead>
          <tr>
            <Th aria-label="Target">
              <SortButton
                label="Target"
                onClick={() => setSortKey("target")}
              />
            </Th>
            <Th aria-label="Theme">
              <SortButton
                label="Theme"
                onClick={() => setSortKey("theme")}
              />
            </Th>
            <Th aria-label="Strategy">
              <SortButton
                label="Strategy"
                onClick={() => setSortKey("expression")}
              />
            </Th>
            <Th aria-label="Entry">
              <SortButton
                label="Entry"
                onClick={() => setSortKey("entryDate")}
              />
            </Th>
            <Th aria-label="Exit">
              <SortButton
                label="Exit"
                onClick={() => setSortKey("exitDate")}
              />
            </Th>
            <Th aria-label="Holding days" className="text-right">
              <SortButton
                className="justify-end"
                label="Holding days"
                onClick={() => setSortKey("holdingDays", "desc")}
              />
            </Th>
            <Th aria-label={pnlHeader} className="text-right">
              <SortButton
                ariaLabel="Sort by realized P&L"
                className="justify-end"
                label={pnlHeader}
                onClick={() => setSortKey("netPnlValue", "desc")}
              />
            </Th>
            <Th>Outcome</Th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row) => (
            <tr key={row.setupId}>
              <Td className="font-mono font-medium">{row.target}</Td>
              <Td>{row.theme}</Td>
              <Td>{row.expression}</Td>
              <Td className="font-mono text-xs">{row.entryDate}</Td>
              <Td className="font-mono text-xs">{row.exitDate}</Td>
              <Td className="text-right font-mono">{row.holdingDays}</Td>
              <Td className="text-right font-mono">
                {mode === "percent"
                  ? row.netPnlPercentLabel
                  : row.netPnlDollarLabel}
              </Td>
              <Td>
                <Badge variant={badgeVariant(row.outcome)}>{row.outcome}</Badge>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div className="flex flex-col gap-3 px-5 pb-5 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>
          Showing {sortedRows.length === 0 ? 0 : startIndex + 1}-{endIndex} of{" "}
          {sortedRows.length} setups
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            Rows per page
            <select
              className="min-h-11 rounded-md border border-border bg-background px-3 text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              onChange={(event) => {
                setPageSize(Number(event.target.value) as (typeof PAGE_SIZES)[number]);
                setPage(1);
              }}
              value={pageSize}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-2">
            <Button
              aria-label="Previous page"
              disabled={boundedPage === 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
              variant="outline"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Previous
            </Button>
            <span className="font-mono text-xs text-foreground">
              {boundedPage}/{totalPages}
            </span>
            <Button
              aria-label="Next page"
              disabled={boundedPage === totalPages}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              type="button"
              variant="outline"
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function SortButton({
  ariaLabel,
  className,
  label,
  onClick,
}: {
  ariaLabel?: string;
  className?: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={ariaLabel}
      className={`inline-flex w-full items-center gap-1 text-left ${className ?? ""}`}
      onClick={onClick}
      type="button"
    >
      <span>{label}</span>
      <ArrowDownUp className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}

function sortRows(
  rows: SetupRow[],
  sort: { direction: "asc" | "desc"; key: SortKey },
): SetupRow[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const aValue = valueForSort(a, sort.key);
    const bValue = valueForSort(b, sort.key);
    if (typeof aValue === "number" && typeof bValue === "number") {
      return (aValue - bValue) * direction;
    }
    return String(aValue).localeCompare(String(bValue)) * direction;
  });
}

function valueForSort(row: SetupRow, key: SortKey): number | string {
  if (key === "netPnlValue") {
    return row.netPnlValue ?? Number.NEGATIVE_INFINITY;
  }
  return row[key];
}

function buildCsvHref(rows: SetupRow[]): string {
  const header = [
    "Target",
    "Theme",
    "Strategy",
    "Entry",
    "Exit",
    "Holding days",
    "Realized P&L %",
    "Realized P&L $",
    "Outcome",
  ];
  const csv = [
    header,
    ...rows.map((row) => [
      row.target,
      row.theme,
      row.expression,
      row.entryDate,
      row.exitDate,
      String(row.holdingDays),
      row.netPnlPercentLabel,
      row.netPnlDollarLabel,
      row.outcome,
    ]),
  ]
    .map((line) => line.map(csvCell).join(","))
    .join("\n");
  return `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
}

function csvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replaceAll("\"", "\"\"")}"`;
  }
  return value;
}
