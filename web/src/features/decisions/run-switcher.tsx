"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import type { RunRow } from "./decision-list.types";

function runLabel(run: RunRow): string {
  const date = run.created_at ?? run.scheduled_date ?? "";
  return date ? `${run.run_id} · ${date}` : run.run_id;
}

/**
 * Run/date switcher. `runs` are newest-first, so the newer run is the previous
 * index and the older run is the next index.
 */
export function RunSwitcher({
  onSelect,
  runs,
  selectedRunId,
}: {
  onSelect: (runId: string) => void;
  runs: RunRow[];
  selectedRunId: string;
}) {
  const index = runs.findIndex((run) => run.run_id === selectedRunId);
  const hasNewer = index > 0;
  const hasOlder = index >= 0 && index < runs.length - 1;

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        aria-label="Newer run"
        disabled={!hasNewer}
        onClick={() => hasNewer && onSelect(runs[index - 1].run_id)}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-40",
        )}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </button>

      <label className="sr-only" htmlFor="run-switcher-select">
        Select run
      </label>
      <select
        id="run-switcher-select"
        aria-label="Select run"
        value={selectedRunId}
        onChange={(event) => onSelect(event.target.value)}
        className="h-9 min-w-56 rounded-md border border-border bg-card px-3 font-mono text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        {runs.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {runLabel(run)}
          </option>
        ))}
      </select>

      <button
        type="button"
        aria-label="Older run"
        disabled={!hasOlder}
        onClick={() => hasOlder && onSelect(runs[index + 1].run_id)}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-40",
        )}
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
