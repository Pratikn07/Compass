import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

export function Input({ className, ...props }: ComponentPropsWithoutRef<"input">) {
  return (
    <input
      className={cn(
        "min-h-11 w-full rounded-md border border-border bg-background px-3 py-2 text-base text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20",
        className,
      )}
      {...props}
    />
  );
}
