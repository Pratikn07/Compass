/** Typed client for the compass /v1 API. The front end renders; it never
 * computes — every number on screen comes from rows the nightly job wrote. */

const BASE = process.env.NEXT_PUBLIC_COMPASS_API ?? "http://localhost:8420";
const KEY = process.env.NEXT_PUBLIC_COMPASS_KEY ?? "";

export interface ThemeState {
  d: string;
  theme_slug: string;
  index_level: number;
  sma200: number | null;
  trend_on: boolean | null;
  days_in_state: number;
}

export interface Theme {
  slug: string;
  name: string;
  etf_ticker: string | null;
  etf_is_primary: boolean;
  state: ThemeState | null;
}

export interface Member {
  ticker: string;
  member_since: string;
  member_until: string | null;
  justification: string;
}

export interface ThemeDetail extends Omit<Theme, "state"> {
  members: Member[];
  state_history: ThemeState[];
}

export interface Recommendation {
  id: number;
  d: string;
  hypothesis: string;
  instrument: string;
  action: "consider_enter" | "consider_exit" | "none";
  reasoning: Record<string, unknown>;
  base_rate: number | null;
  acknowledged_at: string | null;
  acted_at: string | null;
  action_note: string | null;
}

export interface Health {
  latest_price_date: string | null;
  latest_state_date: string | null;
  recent_alerts: { started_at: string; error: string | null }[];
  recent_runs: { started_at: string; source: string; status: string }[];
}

export interface Override {
  id: number;
  ts: string;
  what: string;
  reason: string;
}

export interface RuleChange {
  id: number;
  proposed_at: string;
  change: Record<string, unknown>;
  effective_at: string;
  approved: boolean;
  active: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(KEY ? { "X-Compass-Key": KEY } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/v1/health"),
  themes: () => request<Theme[]>("/v1/themes"),
  themeDetail: (slug: string) => request<ThemeDetail>(`/v1/themes/${slug}`),
  today: () =>
    request<{ d: string | null; recommendations: Recommendation[] }>(
      "/v1/recommendations/today",
    ),
  journal: () =>
    request<{ since: string; recommendations: Recommendation[]; overrides: Override[] }>(
      "/v1/journal",
    ),
  ruleChanges: () => request<RuleChange[]>("/v1/rule-changes"),
  acknowledge: (id: number) =>
    request<Recommendation>(`/v1/recommendations/${id}/ack`, { method: "POST" }),
  createOverride: (what: string, reason: string) =>
    request<Override>("/v1/overrides", {
      method: "POST",
      body: JSON.stringify({ what, reason }),
    }),
  proposeRuleChange: (change: Record<string, unknown>) =>
    request<RuleChange & { note: string }>("/v1/rule-changes", {
      method: "POST",
      body: JSON.stringify({ change }),
    }),
};
