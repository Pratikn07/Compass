import type { DecisionListItem } from "./decision-list.types";
import type { DecisionWatchlist } from "./decision-sidebar-schemas";

export const DECISION_LIST_PAGE_SIZES = [10, 25, 50] as const;
export const DECISION_QUICK_BUCKETS = [
  "all",
  "proposed",
  "needs_attention",
  "rejected",
  "no_action",
] as const;
export const DECISION_EARNINGS_WINDOWS = [
  "all",
  "next_7d",
  "next_14d",
  "unknown",
] as const;

export type DecisionListPageSize = (typeof DECISION_LIST_PAGE_SIZES)[number];
export type DecisionQuickBucket = (typeof DECISION_QUICK_BUCKETS)[number];
export type DecisionEarningsWindow = (typeof DECISION_EARNINGS_WINDOWS)[number];

export type DecisionListQuery = {
  query: string;
  status: string;
  strategy: string;
  page: number;
  pageSize: DecisionListPageSize;
  bucket: DecisionQuickBucket;
  earnings: DecisionEarningsWindow;
  watchlist: string;
};

export type DecisionListViewItem = DecisionListItem & {
  searchText: string;
  statusKey: string;
  strategyKey: string;
  bucketKey: Exclude<DecisionQuickBucket, "all">;
};

export type SidebarCountItem<T extends string = string> = {
  key: T;
  label: string;
  count: number;
  active: boolean;
};

export type SidebarWatchlistItem = {
  watchlistId: string;
  name: string;
  count: number;
  active: boolean;
};

export type DecisionListViewModel = {
  totalCount: number;
  filteredCount: number;
  page: number;
  pageSize: DecisionListPageSize;
  pageCount: number;
  from: number;
  to: number;
  pageItems: DecisionListViewItem[];
  statusOptions: string[];
  strategyOptions: string[];
  hasActiveFilters: boolean;
  sidebar: {
    quickFilters: SidebarCountItem<DecisionQuickBucket>[];
    earningsWindows: SidebarCountItem<DecisionEarningsWindow>[];
    watchlists: SidebarWatchlistItem[];
    activeWatchlistId: string;
  };
};

export type DecisionListViewContext = {
  activeRunDate?: string | null;
  watchlists?: DecisionWatchlist[];
};

export function normalizeDecisionListParams(
  params: Pick<URLSearchParams, "get">,
): DecisionListQuery {
  const pageSize = normalizePageSize(params.get("pageSize"));

  return {
    query: (params.get("q") ?? "").trim(),
    status: (params.get("status") ?? "").trim(),
    strategy: (params.get("strategy") ?? "").trim(),
    page: normalizePositiveInteger(params.get("page")),
    pageSize,
    bucket: normalizeQuickBucket(params.get("bucket")),
    earnings: normalizeEarningsWindow(params.get("earnings")),
    watchlist: (params.get("watchlist") ?? "").trim(),
  };
}

export function buildDecisionListViewModel(
  decisions: DecisionListItem[],
  query: DecisionListQuery,
  context: DecisionListViewContext = {},
): DecisionListViewModel {
  const viewItems = decisions.map(toViewItem);
  const normalizedQuery = query.query.toLowerCase();
  const watchlists = context.watchlists ?? [];
  const activeWatchlist =
    watchlists.find((watchlist) => watchlist.watchlistId === query.watchlist) ??
    null;
  const filteredItems = viewItems.filter((item) => {
    if (normalizedQuery && !item.searchText.includes(normalizedQuery)) {
      return false;
    }
    if (query.status && item.statusKey !== query.status) {
      return false;
    }
    if (query.strategy && item.strategyKey !== query.strategy) {
      return false;
    }
    if (query.bucket !== "all" && item.bucketKey !== query.bucket) {
      return false;
    }
    if (!matchesEarningsWindow(item, query.earnings, context.activeRunDate)) {
      return false;
    }
    if (activeWatchlist && !matchesWatchlist(item, activeWatchlist)) {
      return false;
    }
    return true;
  });

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / query.pageSize));
  const page = filteredItems.length === 0 ? 1 : Math.min(query.page, pageCount);
  const startIndex = (page - 1) * query.pageSize;
  const pageItems = filteredItems.slice(startIndex, startIndex + query.pageSize);

  return {
    totalCount: viewItems.length,
    filteredCount: filteredItems.length,
    page,
    pageSize: query.pageSize,
    pageCount,
    from: pageItems.length === 0 ? 0 : startIndex + 1,
    to: pageItems.length === 0 ? 0 : startIndex + pageItems.length,
    pageItems,
    statusOptions: uniqueSorted(viewItems.map((item) => item.statusKey)),
    strategyOptions: uniqueSorted(viewItems.map((item) => item.strategyKey)),
    hasActiveFilters: Boolean(
      query.query ||
        query.status ||
        query.strategy ||
        query.bucket !== "all" ||
        query.earnings !== "all" ||
        activeWatchlist,
    ),
    sidebar: {
      quickFilters: quickFilterCounts(viewItems, query.bucket),
      earningsWindows: earningsWindowCounts(
        viewItems,
        query.earnings,
        context.activeRunDate,
      ),
      watchlists: watchlistCounts(viewItems, watchlists, activeWatchlist?.watchlistId ?? ""),
      activeWatchlistId: activeWatchlist?.watchlistId ?? "",
    },
  };
}

function toViewItem(item: DecisionListItem): DecisionListViewItem {
  const statusKey = item.status;
  const strategyKey = item.strategyType ?? "";

  return {
    ...item,
    searchText: [
      item.target,
      item.theme,
      item.strategyType,
      item.status,
      item.outcome,
      item.mode,
      item.thesis,
      item.earningsDate,
      item.evidenceSummary,
      ...item.attentionReasons,
    ]
      .filter(isNonEmptyString)
      .join(" ")
      .toLowerCase(),
    statusKey,
    strategyKey,
    bucketKey: quickBucketForItem(item),
  };
}

function quickFilterCounts(
  items: DecisionListViewItem[],
  activeBucket: DecisionQuickBucket,
): SidebarCountItem<DecisionQuickBucket>[] {
  const filters: Omit<SidebarCountItem<DecisionQuickBucket>, "active">[] = [
    { key: "all", label: "All", count: items.length },
    {
      key: "proposed",
      label: "Proposed",
      count: countBucket(items, "proposed"),
    },
    {
      key: "needs_attention",
      label: "Needs Attention",
      count: countBucket(items, "needs_attention"),
    },
    { key: "rejected", label: "Rejected", count: countBucket(items, "rejected") },
    {
      key: "no_action",
      label: "No Action",
      count: countBucket(items, "no_action"),
    },
  ];
  return filters.map((item) => ({ ...item, active: item.key === activeBucket }));
}

function earningsWindowCounts(
  items: DecisionListViewItem[],
  activeWindow: DecisionEarningsWindow,
  activeRunDate?: string | null,
): SidebarCountItem<DecisionEarningsWindow>[] {
  const windows: Omit<SidebarCountItem<DecisionEarningsWindow>, "active">[] = [
    { key: "all", label: "All", count: items.length },
    {
      key: "next_7d",
      label: "Next 7d",
      count: items.filter((item) =>
        matchesEarningsWindow(item, "next_7d", activeRunDate),
      ).length,
    },
    {
      key: "next_14d",
      label: "Next 14d",
      count: items.filter((item) =>
        matchesEarningsWindow(item, "next_14d", activeRunDate),
      ).length,
    },
    {
      key: "unknown",
      label: "Unknown",
      count: items.filter((item) =>
        matchesEarningsWindow(item, "unknown", activeRunDate),
      ).length,
    },
  ];
  return windows.map((item) => ({ ...item, active: item.key === activeWindow }));
}

function watchlistCounts(
  items: DecisionListViewItem[],
  watchlists: DecisionWatchlist[],
  activeWatchlistId: string,
): SidebarWatchlistItem[] {
  return watchlists.map((watchlist) => ({
    watchlistId: watchlist.watchlistId,
    name: watchlist.name,
    count: items.filter((item) => matchesWatchlist(item, watchlist)).length,
    active: watchlist.watchlistId === activeWatchlistId,
  }));
}

function countBucket(
  items: DecisionListViewItem[],
  bucket: Exclude<DecisionQuickBucket, "all">,
): number {
  return items.filter((item) => item.bucketKey === bucket).length;
}

function quickBucketForItem(
  item: DecisionListItem,
): Exclude<DecisionQuickBucket, "all"> {
  if (item.malformed || item.attentionStatus === "needs_attention") {
    return "needs_attention";
  }
  const status = item.status.toLowerCase();
  const outcome = item.outcome.toLowerCase();
  if (
    status.includes("rejected") ||
    outcome.includes("rejected") ||
    outcome === "risk_blocked"
  ) {
    return "rejected";
  }
  if (status === "no_trade" || outcome === "no_trade") {
    return "no_action";
  }
  return "proposed";
}

function matchesEarningsWindow(
  item: DecisionListItem,
  window: DecisionEarningsWindow,
  activeRunDate?: string | null,
): boolean {
  if (window === "all") {
    return true;
  }
  if (!item.earningsDate) {
    return window === "unknown";
  }
  if (window === "unknown") {
    return false;
  }

  const baseDate = parseDateOnly(activeRunDate ?? item.tradingDate);
  const earningsDate = parseDateOnly(item.earningsDate);
  if (!baseDate || !earningsDate) {
    return false;
  }

  const diffDays = Math.floor(
    (earningsDate.getTime() - baseDate.getTime()) / 86_400_000,
  );
  const maxDays = window === "next_7d" ? 7 : 14;
  return diffDays >= 0 && diffDays <= maxDays;
}

function matchesWatchlist(
  item: DecisionListItem,
  watchlist: DecisionWatchlist,
): boolean {
  const target = item.target.toUpperCase();
  return watchlist.items.some((entry) => entry.ticker.toUpperCase() === target);
}

function normalizePositiveInteger(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

function normalizePageSize(value: string | null): DecisionListPageSize {
  const parsed = Number(value);
  return DECISION_LIST_PAGE_SIZES.includes(parsed as DecisionListPageSize)
    ? (parsed as DecisionListPageSize)
    : 25;
}

function normalizeQuickBucket(value: string | null): DecisionQuickBucket {
  return DECISION_QUICK_BUCKETS.includes(value as DecisionQuickBucket)
    ? (value as DecisionQuickBucket)
    : "all";
}

function normalizeEarningsWindow(value: string | null): DecisionEarningsWindow {
  return DECISION_EARNINGS_WINDOWS.includes(value as DecisionEarningsWindow)
    ? (value as DecisionEarningsWindow)
    : "all";
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(
    new Set(values.filter((value) => value.trim().length > 0)),
  ).sort((a, b) => a.localeCompare(b));
}

function isNonEmptyString(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parseDateOnly(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
