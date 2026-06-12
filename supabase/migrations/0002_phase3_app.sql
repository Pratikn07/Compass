-- Compass Phase 3 — nightly state, recommendations, governance tables.
-- Propose-only is structural: there is no orders/positions table, anywhere.

create table if not exists compass_theme_state_daily (
    id            bigint generated always as identity primary key,
    d             date not null,
    theme_slug    text not null references compass_themes(slug),
    index_level   double precision not null,
    sma200        double precision,
    trend_on      boolean,
    days_in_state integer not null default 1,
    ingested_at   timestamptz not null default now(),
    unique (d, theme_slug)
);

create table if not exists compass_recommendations (
    id              bigint generated always as identity primary key,
    d               date not null,
    hypothesis      text not null,           -- 'h2' | 'none'
    instrument      text not null,           -- theme slug, ETF ticker, or '-'
    action          text not null check (action in ('consider_enter', 'consider_exit', 'none')),
    reasoning       jsonb not null default '{}',
    base_rate       double precision,
    acknowledged_at timestamptz,
    acted_at        timestamptz,
    action_note     text,
    ingested_at     timestamptz not null default now(),
    unique (d, hypothesis, instrument)
);

create table if not exists compass_overrides (
    id           bigint generated always as identity primary key,
    ts           timestamptz not null default now(),
    what         text not null,
    reason       text not null check (length(trim(reason)) > 0),
    ingested_at  timestamptz not null default now()
);

create table if not exists compass_rule_changes (
    id            bigint generated always as identity primary key,
    proposed_at   timestamptz not null default now(),
    change        jsonb not null,
    -- The 48-hour cooling-off clock, enforced by the database itself.
    effective_at  timestamptz not null,
    approved      boolean not null default false,
    ingested_at   timestamptz not null default now(),
    check (effective_at >= proposed_at + interval '48 hours')
);

create index if not exists compass_theme_state_daily_slug_d
    on compass_theme_state_daily (theme_slug, d);
create index if not exists compass_recommendations_d on compass_recommendations (d);
