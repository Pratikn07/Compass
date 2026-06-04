import { AlertTriangle } from "lucide-react";

export function ErrorState({
  detail,
  title,
}: {
  detail?: string;
  title: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-card border border-danger/40 border-l-4 border-l-danger bg-danger/5 p-4 text-sm text-danger"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          aria-hidden="true"
          className="mt-0.5 h-4 w-4 shrink-0"
        />
        <p className="font-semibold">{title}</p>
      </div>
      {detail ? (
        <details className="mt-3">
          <summary className="cursor-pointer font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            Raw diagnostic detail
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto rounded-card border border-danger/30 bg-background p-3 font-mono text-xs text-foreground">
            {detail}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
