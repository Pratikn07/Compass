"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createClient } from "@/lib/supabase/client";
import type { DecisionChainRecord } from "./decision-chain.types";
import {
  fetchDecisionChain,
  type DecisionChainSupabase,
} from "./fetch-decision-chain";

export function useDecisionChain(decisionId: string) {
  const supabase = useMemo(() => createClient(), []);

  return useQuery<DecisionChainRecord[], Error>({
    queryKey: ["decision-chain", decisionId],
    queryFn: () =>
      fetchDecisionChain(
        supabase as unknown as DecisionChainSupabase,
        decisionId,
      ),
    enabled: decisionId.length > 0,
    staleTime: 30_000,
  });
}
