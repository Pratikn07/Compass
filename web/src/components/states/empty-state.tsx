export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex min-h-32 flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border-strong bg-muted/30 p-8 text-center text-sm text-muted-foreground">
      <span
        aria-hidden="true"
        className="h-2 w-2 rounded-full bg-muted-foreground/40"
      />
      {message}
    </div>
  );
}
