"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Compass, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/themes", label: "Themes" },
  { href: "/decisions", label: "Decisions" },
  { href: "/backtest", label: "Backtest" },
  { href: "/runs", label: "Runs" },
  { href: "/journal", label: "Journal" },
  { href: "/rules", label: "Rules" },
];

export function Nav() {
  const pathname = usePathname();
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealthy(h.status === "healthy"))
      .catch(() => setHealthy(false));
  }, [pathname]);

  if (pathname === "/login") return null;

  async function signOut() {
    await createClient().auth.signOut();
    window.location.assign("/login");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#08090c]/80 backdrop-blur-xl">
      <nav
        aria-label="Primary"
        className="mx-auto flex min-h-14 w-full max-w-6xl items-center gap-1 overflow-x-auto px-4 sm:px-6"
      >
        <Link
          href="/"
          className="mr-4 flex items-center gap-2 text-[15px] font-semibold tracking-tight"
        >
          <Compass aria-hidden className="h-4.5 w-4.5 text-text-2" size={18} />
          compass
        </Link>
        {LINKS.map(({ href, label }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative rounded-md px-3 py-1.5 text-sm transition-colors duration-200",
                active
                  ? "text-text-1"
                  : "text-text-3 hover:text-text-2",
              )}
            >
              {label}
              {active && (
                <span
                  aria-hidden
                  className="absolute inset-x-2 -bottom-[13px] h-px bg-gradient-to-r from-accent-a/70 to-accent-b/70"
                />
              )}
            </Link>
          );
        })}
        <div className="ml-auto flex shrink-0 items-center gap-2" role="status">
          <span
            aria-hidden
            className={cn(
              "h-1.5 w-1.5 rounded-full transition-colors",
              healthy === null
                ? "bg-text-3"
                : healthy
                  ? "bg-up"
                  : "bg-alert",
            )}
          />
          <span className="text-xs text-text-3">
            {healthy === null ? "checking" : healthy ? "data healthy" : "alerts"}
          </span>
          <button
            onClick={signOut}
            aria-label="Sign out"
            className="ml-1 cursor-pointer rounded-md p-2 text-text-3 hover:text-text-1"
          >
            <LogOut aria-hidden size={14} />
          </button>
        </div>
      </nav>
    </header>
  );
}
