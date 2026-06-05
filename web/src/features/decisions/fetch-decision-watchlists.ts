import {
  type DecisionWatchlist,
  watchlistItemRowSchema,
  watchlistRowSchema,
} from "./decision-sidebar-schemas";

type SupabaseReadResult = {
  data: unknown;
  error: { message: string } | null;
};

type SupabaseReadQuery = {
  order(column: string, options: { ascending: boolean }): PromiseLike<SupabaseReadResult>;
};

type SupabaseFromQuery = {
  select(columns: string): SupabaseReadQuery;
};

export type DecisionWatchlistsSupabase = {
  from(table: "watchlists" | "watchlist_items"): SupabaseFromQuery;
};

export async function fetchDecisionWatchlists(
  supabase: DecisionWatchlistsSupabase,
): Promise<DecisionWatchlist[]> {
  const [watchlistsResult, itemsResult] = await Promise.all([
    supabase.from("watchlists").select("*").order("name", { ascending: true }),
    supabase
      .from("watchlist_items")
      .select("*")
      .order("sort_order", { ascending: true }),
  ]);

  if (watchlistsResult.error) {
    throw new Error(`Failed to load watchlists: ${watchlistsResult.error.message}`);
  }
  if (itemsResult.error) {
    throw new Error(`Failed to load watchlist items: ${itemsResult.error.message}`);
  }

  const watchlists = watchlistRowSchema.array().parse(watchlistsResult.data ?? []);
  const items = watchlistItemRowSchema.array().parse(itemsResult.data ?? []);
  const itemsByWatchlist = new Map<string, DecisionWatchlist["items"]>();

  for (const item of items) {
    const current = itemsByWatchlist.get(item.watchlistId) ?? [];
    current.push({ ticker: item.ticker, theme: item.theme });
    itemsByWatchlist.set(item.watchlistId, current);
  }

  return watchlists.map((watchlist) => ({
    ...watchlist,
    items: itemsByWatchlist.get(watchlist.watchlistId) ?? [],
  }));
}
