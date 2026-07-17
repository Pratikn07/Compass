create schema if not exists compass_storage;

revoke all on schema compass_storage from anon, authenticated;
alter default privileges in schema compass_storage revoke all on tables from anon, authenticated;
alter default privileges in schema compass_storage revoke all on sequences from anon, authenticated;

grant usage on schema compass_storage to service_role;
alter default privileges in schema compass_storage grant all on tables to service_role;
alter default privileges in schema compass_storage grant usage, select on sequences to service_role;

create table compass_storage.companies (
    owner_id uuid not null references auth.users(id),
    ticker text primary key,
    name text not null,
    kind text not null check (kind in ('stock', 'etf', 'benchmark')),
    ingested_at timestamptz not null default now()
);

create table compass_storage.themes (
    owner_id uuid not null references auth.users(id),
    slug text primary key,
    name text not null,
    etf_ticker text references compass_storage.companies(ticker),
    etf_is_primary boolean not null default false,
    ingested_at timestamptz not null default now()
);

create table compass_storage.theme_memberships (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    theme_slug text not null references compass_storage.themes(slug),
    ticker text not null references compass_storage.companies(ticker),
    member_since date not null,
    member_until date,
    justification text not null,
    ingested_at timestamptz not null default now(),
    unique (owner_id, theme_slug, ticker, member_since)
);

create table compass_storage.price_bars (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    ticker text not null references compass_storage.companies(ticker),
    d date not null,
    open double precision,
    high double precision,
    low double precision,
    close double precision,
    adj_close double precision not null,
    volume bigint,
    source text not null,
    ingested_at timestamptz not null default now(),
    unique (owner_id, ticker, d)
);

create table compass_storage.fundamentals (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    ticker text not null references compass_storage.companies(ticker),
    fiscal_quarter_end date not null,
    report_date date,
    revenue double precision,
    operating_income double precision,
    eps_estimate double precision,
    eps_actual double precision,
    surprise_pct double precision,
    source text not null,
    ingested_at timestamptz not null default now(),
    unique (owner_id, ticker, fiscal_quarter_end)
);

create table compass_storage.theme_state_daily (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    d date not null,
    theme_slug text not null references compass_storage.themes(slug),
    index_level double precision not null,
    sma200 double precision,
    trend_on boolean,
    days_in_state integer not null default 1,
    ingested_at timestamptz not null default now(),
    unique (owner_id, d, theme_slug)
);

create table compass_storage.runs (
    owner_id uuid not null references auth.users(id),
    run_id text primary key,
    run_type text not null check (run_type in ('nightly', 'ingest', 'backtest')),
    trigger_type text not null default 'scheduled',
    scheduled_date date,
    status text not null check (status in ('running', 'succeeded', 'partial', 'failed')),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    ingested_at timestamptz not null default now()
);

create table compass_storage.decision_records (
    owner_id uuid not null references auth.users(id),
    decision_id text primary key,
    run_id text references compass_storage.runs(run_id),
    decision_date date not null,
    hypothesis text not null,
    instrument text not null,
    theme_slug text references compass_storage.themes(slug),
    action text not null check (action in ('consider_enter', 'consider_exit', 'none')),
    reasoning jsonb not null default '{}'::jsonb,
    base_rate double precision,
    attention_status text not null default 'normal'
        check (attention_status in ('normal', 'needs_attention')),
    attention_reasons text[] not null default '{}'::text[],
    acknowledged_at timestamptz,
    acted_at timestamptz,
    action_note text,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now(),
    unique (owner_id, decision_date, hypothesis, instrument)
);

create table compass_storage.overrides (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    ts timestamptz not null default now(),
    what text not null,
    reason text not null check (length(trim(reason)) > 0),
    ingested_at timestamptz not null default now()
);

create table compass_storage.rule_changes (
    owner_id uuid not null references auth.users(id),
    id bigint generated always as identity primary key,
    proposed_at timestamptz not null default now(),
    change jsonb not null,
    effective_at timestamptz not null,
    approved boolean not null default false,
    ingested_at timestamptz not null default now(),
    check (effective_at >= proposed_at + interval '48 hours')
);

create table compass_storage.journal_records (
    owner_id uuid not null references auth.users(id),
    journal_record_id text primary key,
    record_type text not null,
    run_id text references compass_storage.runs(run_id),
    decision_id text references compass_storage.decision_records(decision_id),
    decision_index integer,
    trading_date date not null,
    target text,
    theme text,
    source text not null,
    parent_record_id text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.provider_snapshots (
    owner_id uuid not null references auth.users(id),
    provider_snapshot_id text primary key,
    provider text not null,
    target text,
    theme text,
    source_endpoint text,
    source_url text,
    source_id text,
    as_of date,
    retrieved_at timestamptz,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.provider_errors (
    owner_id uuid not null references auth.users(id),
    provider_error_id text primary key,
    provider text not null,
    error_type text not null,
    run_id text references compass_storage.runs(run_id),
    target text,
    source text,
    message text not null,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.learning_reports (
    owner_id uuid not null references auth.users(id),
    learning_report_id text primary key,
    run_id text references compass_storage.runs(run_id),
    report_date date not null,
    target text,
    theme text,
    report_type text not null,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.storage_write_audit (
    owner_id uuid not null references auth.users(id),
    storage_write_audit_id text primary key,
    provider text not null,
    table_name text not null,
    run_id text references compass_storage.runs(run_id),
    attempted_record_count integer not null default 0,
    written_record_count integer not null default 0,
    error_count integer not null default 0,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.system_health (
    owner_id uuid not null references auth.users(id),
    system_health_id text primary key,
    component text not null check (component in (
        'api', 'database', 'market_data', 'provider_health',
        'recommendation_engine', 'backtest_engine', 'storage', 'nightly_worker'
    )),
    status text not null default 'unknown'
        check (status in ('healthy', 'degraded', 'blocked', 'unknown')),
    detail text,
    latency_seconds double precision,
    run_id text references compass_storage.runs(run_id),
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.watchlists (
    owner_id uuid not null references auth.users(id),
    watchlist_id text primary key,
    name text not null,
    description text,
    source text not null default 'strategy_universe',
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    ingested_at timestamptz not null default now()
);

create table compass_storage.watchlist_items (
    owner_id uuid not null references auth.users(id),
    watchlist_item_id text primary key,
    watchlist_id text not null references compass_storage.watchlists(watchlist_id)
        on delete cascade,
    ticker text not null,
    theme text,
    sort_order integer not null default 0,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    ingested_at timestamptz not null default now(),
    unique (owner_id, watchlist_id, ticker, theme)
);

create index price_bars_owner_ticker_d_idx
    on compass_storage.price_bars (owner_id, ticker, d desc);
create index fundamentals_owner_ticker_report_idx
    on compass_storage.fundamentals (owner_id, ticker, report_date desc);
create index theme_state_owner_slug_d_idx
    on compass_storage.theme_state_daily (owner_id, theme_slug, d desc);
create index decisions_owner_date_idx
    on compass_storage.decision_records (owner_id, decision_date desc, decision_id);
create index decisions_owner_run_attention_idx
    on compass_storage.decision_records (owner_id, run_id, attention_status);
create index runs_owner_started_idx
    on compass_storage.runs (owner_id, started_at desc, run_id);
create index journal_owner_decision_idx
    on compass_storage.journal_records (owner_id, decision_id, created_at);
create index provider_errors_owner_created_idx
    on compass_storage.provider_errors (owner_id, created_at desc);
create index health_owner_component_created_idx
    on compass_storage.system_health (owner_id, component, created_at desc);
create index learning_reports_owner_date_idx
    on compass_storage.learning_reports (owner_id, report_type, report_date desc);

alter table compass_storage.companies enable row level security;
alter table compass_storage.themes enable row level security;
alter table compass_storage.theme_memberships enable row level security;
alter table compass_storage.price_bars enable row level security;
alter table compass_storage.fundamentals enable row level security;
alter table compass_storage.theme_state_daily enable row level security;
alter table compass_storage.decision_records enable row level security;
alter table compass_storage.overrides enable row level security;
alter table compass_storage.rule_changes enable row level security;
alter table compass_storage.runs enable row level security;
alter table compass_storage.journal_records enable row level security;
alter table compass_storage.provider_snapshots enable row level security;
alter table compass_storage.provider_errors enable row level security;
alter table compass_storage.learning_reports enable row level security;
alter table compass_storage.storage_write_audit enable row level security;
alter table compass_storage.system_health enable row level security;
alter table compass_storage.watchlists enable row level security;
alter table compass_storage.watchlist_items enable row level security;

create policy owner_select on compass_storage.companies
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.themes
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.theme_memberships
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.price_bars
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.fundamentals
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.theme_state_daily
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.decision_records
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.overrides
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.rule_changes
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.runs
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.journal_records
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.provider_snapshots
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.provider_errors
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.learning_reports
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.storage_write_audit
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.system_health
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.watchlists
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);
create policy owner_select on compass_storage.watchlist_items
    for select
    to authenticated
    using ((select auth.uid()) = owner_id);

revoke all on all tables in schema compass_storage from anon, authenticated;
revoke all on all sequences in schema compass_storage from anon, authenticated;
grant all on all tables in schema compass_storage to service_role;
grant usage, select on all sequences in schema compass_storage to service_role;
