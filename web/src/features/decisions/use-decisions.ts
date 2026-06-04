"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import type { DecisionListItem } from "./decision-list.types";
import { fetchDecisions, type DecisionsSupabase } from "./fetch-decisions";

export function useDecisions(runId: string | null | undefined) {
  const supabase = useMemo(() => createClient(), []);

  return useQuery<DecisionListItem[], Error>({
    queryKey: ["decisions", runId],
    queryFn: () => fetchDecisions(supabase as unknown as DecisionsSupabase, runId!),
    enabled: Boolean(runId),
    staleTime: 30_000,
  });
}
