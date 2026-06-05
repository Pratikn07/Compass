"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import {
  fetchDecisionWatchlists,
  type DecisionWatchlistsSupabase,
} from "./fetch-decision-watchlists";

export function useDecisionWatchlists() {
  const supabase = useMemo(() => createClient(), []);

  return useQuery({
    queryKey: ["decision-watchlists"],
    queryFn: () =>
      fetchDecisionWatchlists(supabase as unknown as DecisionWatchlistsSupabase),
    staleTime: 60_000,
  });
}
