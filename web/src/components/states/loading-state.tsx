export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-32 flex-col items-center justify-center gap-3 rounded-card border border-border bg-card p-8 text-sm text-muted-foreground shadow-sm shadow-primary/[0.03]"
    >
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent"
      />
      {label}
    </div>
  );
}
