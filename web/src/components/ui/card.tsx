import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: ComponentPropsWithoutRef<"div">) {
  return (
    <div
      className={cn(
        "rounded-card border border-border bg-card p-5 shadow-sm shadow-primary/[0.03]",
        className,
      )}
      {...props}
    />
  );
}
