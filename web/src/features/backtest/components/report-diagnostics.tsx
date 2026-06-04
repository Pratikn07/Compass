import { AlertTriangle, CircleCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { BacktestViewModel } from "@/features/backtest/lib/backtest-view-model";

export function ReportDiagnostics({
  diagnostics,
}: {
  diagnostics: BacktestViewModel["diagnostics"];
}) {
  const hasDiagnostics =
    diagnostics.warnings.length > 0 || diagnostics.excluded.length > 0;

  return (
    <Card className="grid gap-4">
      <div>
        <h2 className="text-base font-semibold">Diagnostics</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Warnings and excluded observations reported by the backtest run.
        </p>
      </div>
      {hasDiagnostics ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <section aria-labelledby="backtest-warnings-heading" className="grid gap-2">
            <h3
              className="flex items-center gap-2 text-sm font-semibold"
              id="backtest-warnings-heading"
            >
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              Warnings
            </h3>
            {diagnostics.warnings.length ? (
              <ul className="grid gap-2 text-sm text-muted-foreground">
                {diagnostics.warnings.map((warning) => (
                  <li key={warning} className="rounded-card border border-border p-3">
                    {warning}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No warnings reported.</p>
            )}
          </section>
          <section aria-labelledby="backtest-excluded-heading" className="grid gap-2">
            <h3
              className="flex items-center gap-2 text-sm font-semibold"
              id="backtest-excluded-heading"
            >
              <CircleCheck className="h-4 w-4" aria-hidden="true" />
              Excluded observations
            </h3>
            {diagnostics.excluded.length ? (
              <ul className="grid gap-2 text-sm text-muted-foreground">
                {diagnostics.excluded.map((item) => (
                  <li
                    key={item.label}
                    className="flex items-center justify-between gap-3 rounded-card border border-border p-3"
                  >
                    <span>{item.label}</span>
                    <span className="font-mono text-foreground">{item.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No excluded observations reported.
              </p>
            )}
          </section>
        </div>
      ) : (
        <p className="rounded-card border border-dashed border-border p-6 text-sm text-muted-foreground">
          No warnings or excluded observations reported.
        </p>
      )}
    </Card>
  );
}
