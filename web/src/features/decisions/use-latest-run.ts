"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import type { RunRow } from "./decision-list.types";
import { fetchLatestRun, type LatestRunSupabase } from "./fetch-latest-run";

export function useLatestRun() {
  const supabase = useMemo(() => createClient(), []);

  return useQuery<RunRow | null, Error>({
    queryKey: ["latest-run"],
    queryFn: () => fetchLatestRun(supabase as unknown as LatestRunSupabase),
    staleTime: 30_000,
  });
}
