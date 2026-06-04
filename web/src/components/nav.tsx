"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

const items = [
  { href: "/decisions", label: "Decisions" },
  { href: "/runs", label: "Runs" },
  { href: "/backtest", label: "Backtest" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur supports-[backdrop-filter]:bg-card/70">
      <nav
        aria-label="Primary"
        className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-3 text-sm"
      >
        <Link
          href="/decisions"
          className="flex items-center gap-2 font-semibold tracking-tight text-foreground focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
        >
          <span
            aria-hidden="true"
            className="inline-block h-4 w-4 rounded-[5px] bg-primary"
          />
          Prescient
        </Link>
        <div className="flex items-center gap-1">
          {items.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-md px-3 py-1.5 font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  active
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
              >
                {item.label}
                {active ? (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-3 -bottom-3 h-0.5 rounded-full bg-accent"
                  />
                ) : null}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
