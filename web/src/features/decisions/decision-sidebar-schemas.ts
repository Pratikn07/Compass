import { z } from "zod";

export const watchlistRowSchema = z
  .object({
    watchlist_id: z.string(),
    name: z.string(),
    description: z.string().nullable(),
    source: z.string(),
    schema_version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .transform((value) => ({
    watchlistId: value.watchlist_id,
    name: value.name,
    description: value.description,
    source: value.source,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
    updatedAt: value.updated_at,
  }));

export const watchlistItemRowSchema = z
  .object({
    watchlist_item_id: z.string(),
    watchlist_id: z.string(),
    ticker: z.string(),
    theme: z.string().nullable(),
    sort_order: z.number(),
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    watchlistItemId: value.watchlist_item_id,
    watchlistId: value.watchlist_id,
    ticker: value.ticker,
    theme: value.theme,
    sortOrder: value.sort_order,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export const systemHealthRowSchema = z
  .object({
    system_health_id: z.string(),
    component: z.enum(["market_data", "pricing_engine", "risk_engine"]),
    status: z.enum(["healthy", "degraded", "blocked", "unknown"]),
    detail: z.string().nullable(),
    latency_seconds: z.number().nullable(),
    run_id: z.string().nullable(),
    schema_version: z.number(),
    created_at: z.string(),
  })
  .transform((value) => ({
    systemHealthId: value.system_health_id,
    component: value.component,
    status: value.status,
    detail: value.detail,
    latencySeconds: value.latency_seconds,
    runId: value.run_id,
    schemaVersion: value.schema_version,
    createdAt: value.created_at,
  }));

export type WatchlistRow = z.infer<typeof watchlistRowSchema>;
export type WatchlistItemRow = z.infer<typeof watchlistItemRowSchema>;
export type SystemHealthRow = z.infer<typeof systemHealthRowSchema>;

export type DecisionWatchlist = WatchlistRow & {
  items: Pick<WatchlistItemRow, "ticker" | "theme">[];
};
