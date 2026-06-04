"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchOperatorStatus, requestModeAuthorization } from "@/lib/operator/client";

export function useOperatorStatus() {
  return useQuery({
    queryKey: ["operator-status"],
    queryFn: fetchOperatorStatus,
    refetchOnWindowFocus: true,
  });
}

export function useModeAuthorizationMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: requestModeAuthorization,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["operator-status"] });
    },
  });
}
