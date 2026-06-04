import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

export function Table({
  className,
  ...props
}: ComponentPropsWithoutRef<"table">) {
  return (
    <div className="w-full overflow-auto rounded-card border border-border bg-card shadow-sm shadow-primary/[0.03]">
      <table
        className={cn(
          "w-full border-collapse text-sm tabular-nums [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:nth-child(even)]:bg-muted/30",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export function Th({ className, ...props }: ComponentPropsWithoutRef<"th">) {
  return (
    <th
      className={cn(
        "sticky top-0 z-10 border-b border-border bg-muted/60 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground backdrop-blur",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: ComponentPropsWithoutRef<"td">) {
  return (
    <td
      className={cn(
        "border-b border-border px-3 py-2.5 align-middle",
        className,
      )}
      {...props}
    />
  );
}
