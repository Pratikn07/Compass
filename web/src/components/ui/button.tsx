import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-[background-color,box-shadow,transform] duration-150 cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
  {
    defaultVariants: {
      variant: "primary",
    },
    variants: {
      variant: {
        outline:
          "border border-border-strong bg-card text-foreground shadow-sm hover:bg-muted hover:border-border-strong",
        primary:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
      },
    },
  },
);

export type ButtonProps = ComponentPropsWithoutRef<"button"> &
  VariantProps<typeof buttonVariants>;

export function Button({ className, variant, ...props }: ButtonProps) {
  return (
    <button className={cn(buttonVariants({ variant }), className)} {...props} />
  );
}
