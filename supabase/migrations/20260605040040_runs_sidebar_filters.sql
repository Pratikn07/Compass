-- Backend-owned contracts for the late decisions sidebar slice.
-- The browser receives authenticated read-only access; service_role remains the
-- only role that writes these projection tables.

alter table prescient_storage.decision_records
    add column if not exists attention_status text not null default 'normal',
    add column if not exists attention_reasons text[] not null default '{}'::text[];
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'decision_records_attention_status_check'
    ) then
        alter table prescient_storage.decision_records
            add constraint decision_records_attention_status_check
            check (attention_status in ('normal', 'needs_attention'));
    end if;
end $$;
create table if not exists prescient_storage.watchlists (
    watchlist_id text primary key,
    name text not null,
    description text,
    source text not null default 'strategy_universe',
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create table if not exists prescient_storage.watchlist_items (
    watchlist_item_id text primary key,
    watchlist_id text not null references prescient_storage.watchlists (watchlist_id)
        on delete cascade,
    ticker text not null,
    theme text,
    sort_order integer not null default 0,
    schema_version integer not null default 1,
    created_at timestamptz not null default now(),
    unique (watchlist_id, ticker, theme)
);
create table if not exists prescient_storage.system_health (
    system_health_id text primary key,
    component text not null,
    status text not null default 'unknown',
    detail text,
    latency_seconds double precision,
    run_id text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);
alter table prescient_storage.system_health
    add column if not exists payload jsonb not null default '{}'::jsonb;
alter table prescient_storage.system_health
    drop constraint if exists system_health_component_check;
alter table prescient_storage.system_health
    add constraint system_health_component_check
    check (component in (
        'market_data',
        'provider_health',
        'pricing_engine',
        'risk_engine'
    ));
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'system_health_status_check'
    ) then
        alter table prescient_storage.system_health
            add constraint system_health_status_check
            check (status in ('healthy', 'degraded', 'blocked', 'unknown'));
    end if;
end $$;
alter table prescient_storage.watchlists enable row level security;
alter table prescient_storage.watchlist_items enable row level security;
alter table prescient_storage.system_health enable row level security;
grant select on all tables in schema prescient_storage to authenticated;
drop policy if exists authenticated_read on prescient_storage.watchlists;
create policy authenticated_read on prescient_storage.watchlists
    for select to authenticated
    using (true);
drop policy if exists authenticated_read on prescient_storage.watchlist_items;
create policy authenticated_read on prescient_storage.watchlist_items
    for select to authenticated
    using (true);
drop policy if exists authenticated_read on prescient_storage.system_health;
create policy authenticated_read on prescient_storage.system_health
    for select to authenticated
    using (true);
create index if not exists decision_records_attention_status_idx
    on prescient_storage.decision_records (run_id, attention_status);
create index if not exists watchlist_items_watchlist_sort_idx
    on prescient_storage.watchlist_items (watchlist_id, sort_order, ticker);
create index if not exists system_health_component_created_idx
    on prescient_storage.system_health (component, created_at desc);
create index if not exists system_health_run_id_idx
    on prescient_storage.system_health (run_id, created_at desc);
