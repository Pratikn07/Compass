import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium leading-5 whitespace-nowrap",
  {
    defaultVariants: {
      variant: "muted",
    },
    variants: {
      variant: {
        danger: "border-danger/25 bg-danger/10 text-danger",
        muted: "border-border bg-muted text-muted-foreground",
        success: "border-success/25 bg-success/10 text-success",
        warning: "border-warning/25 bg-warning/10 text-warning",
      },
    },
  },
);

const dotColor: Record<string, string> = {
  danger: "bg-danger",
  muted: "bg-muted-foreground/60",
  success: "bg-success",
  warning: "bg-warning",
};

export type BadgeProps = ComponentPropsWithoutRef<"span"> &
  VariantProps<typeof badgeVariants> & {
    /** Show a leading status dot so meaning isn't conveyed by color alone. */
    dot?: boolean;
  };

export function Badge({ className, variant, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot ? (
        <span
          aria-hidden="true"
          className={cn("h-1.5 w-1.5 rounded-full", dotColor[variant ?? "muted"])}
        />
      ) : null}
      {children}
    </span>
  );
}
