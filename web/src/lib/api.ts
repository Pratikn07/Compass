/** Typed same-origin client for Compass. Authentication is added server-side. */

const BASE = "/api/compass";

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
  decision_id: string;
  decision_date: string;
  hypothesis: string;
  instrument: string;
  theme_slug: string | null;
  action: "consider_enter" | "consider_exit" | "none";
  reasoning: Record<string, unknown>;
  base_rate: number | null;
  attention_status: "normal" | "needs_attention";
  attention_reasons: string[];
  acknowledged_at: string | null;
  acted_at: string | null;
  action_note: string | null;
}

export interface JournalRecord {
  journal_record_id: string;
  record_type: string;
  trading_date: string;
  decision_id: string | null;
  target: string | null;
  theme: string | null;
  source: string;
  payload: Record<string, unknown>;
}

export interface HealthComponent {
  component: string;
  status: "healthy" | "degraded" | "blocked" | "unknown";
  detail: string | null;
  created_at: string;
}

export interface Run {
  run_id: string;
  run_type: string;
  status: "running" | "succeeded" | "partial" | "failed";
  scheduled_date: string | null;
  started_at: string;
  completed_at: string | null;
  payload: Record<string, unknown>;
}

export interface Health {
  status: "healthy" | "degraded";
  components: HealthComponent[];
  recent_runs: Run[];
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

export interface ProviderHealth {
  providers: Array<Record<string, unknown>>;
  recent_errors: Array<Record<string, unknown>>;
}

export interface BacktestReport {
  learning_report_id: string;
  report_date: string;
  report_type: string;
  payload: {
    contexts_evaluated?: number;
    invalid_contexts_skipped?: number;
    execution_enabled?: boolean;
    scorecards?: Record<
      string,
      {
        events_evaluable: number;
        directional_hit_rate: number | null;
        average_option_return_pct: number | null;
        sample_size_verdict: string;
        survived: boolean | null;
        notes: string[];
      }
    >;
  };
}

export interface Paginated<T> {
  items: T[];
  next_cursor: string | null;
}

export interface DecisionDetail {
  decision: Recommendation;
  journal: JournalRecord[];
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
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
    request<{ since: string; records: JournalRecord[]; overrides: Override[] }>(
      "/v1/journal",
    ),
  ruleChanges: () => request<RuleChange[]>("/v1/rule-changes"),
  acknowledge: (decisionId: string) =>
    request<Recommendation>(`/v1/recommendations/${decisionId}/ack`, {
      method: "POST",
    }),
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
  decisions: (cursor?: string) =>
    request<Paginated<Recommendation>>(
      `/v1/decisions?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  decision: (id: string) => request<DecisionDetail>(`/v1/decisions/${id}`),
  backtest: () => request<BacktestReport>("/v1/backtests/latest"),
  runs: (cursor?: string) =>
    request<Paginated<Run>>(
      `/v1/runs?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  providers: () => request<ProviderHealth>("/v1/providers/health"),
  systemHealth: () => request<HealthComponent[]>("/v1/system-health"),
};
