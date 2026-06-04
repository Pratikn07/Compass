"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import type { RunRow } from "./decision-list.types";
import { fetchRunHistory, type RunHistorySupabase } from "./fetch-run-history";

export function useRunHistory() {
  const supabase = useMemo(() => createClient(), []);

  return useQuery<RunRow[], Error>({
    queryKey: ["run-history"],
    queryFn: () => fetchRunHistory(supabase as unknown as RunHistorySupabase),
    staleTime: 30_000,
  });
}
