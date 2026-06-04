"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchDailyHaltStatus,
  fetchLatestRuns,
  fetchRecentProviderErrors,
  fetchRecentStorageAudit,
} from "@/lib/runs/queries";

export function useLatestRuns() {
  return useQuery({
    queryKey: ["runs", "latest"],
    queryFn: () => fetchLatestRuns(10),
    refetchOnWindowFocus: true,
  });
}

export function useRecentProviderErrors() {
  return useQuery({
    queryKey: ["runs", "provider-errors"],
    queryFn: () => fetchRecentProviderErrors(20),
    refetchOnWindowFocus: true,
  });
}

export function useRecentStorageAudit() {
  return useQuery({
    queryKey: ["runs", "storage-audit"],
    queryFn: () => fetchRecentStorageAudit(10),
    refetchOnWindowFocus: true,
  });
}

export function useDailyHaltStatus() {
  return useQuery({
    queryKey: ["runs", "daily-halt"],
    queryFn: fetchDailyHaltStatus,
    refetchOnWindowFocus: true,
  });
}
