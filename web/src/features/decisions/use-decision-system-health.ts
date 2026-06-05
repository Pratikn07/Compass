"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import {
  fetchDecisionSystemHealth,
  type DecisionSystemHealthSupabase,
} from "./fetch-decision-system-health";

export function useDecisionSystemHealth() {
  const supabase = useMemo(() => createClient(), []);

  return useQuery({
    queryKey: ["decision-system-health"],
    queryFn: () =>
      fetchDecisionSystemHealth(
        supabase as unknown as DecisionSystemHealthSupabase,
      ),
    staleTime: 30_000,
  });
}
