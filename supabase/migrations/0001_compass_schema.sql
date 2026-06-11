-- Compass — Phase 1 schema.
-- Lives in the shared (vanta) Supabase project; all tables are compass_-prefixed.
-- Every fact table carries ingested_at (when WE learned it) for point-in-time provenance.

create table if not exists compass_companies (
    ticker        text primary key,
    name          text not null,
    kind          text not null check (kind in ('stock', 'etf', 'benchmark')),
    ingested_at   timestamptz not null default now()
);

create table if not exists compass_themes (
    slug            text primary key,
    name            text not null,
    etf_ticker      text references compass_companies(ticker),
    etf_is_primary  boolean not null default false,
    ingested_at     timestamptz not null default now()
);

create table if not exists compass_theme_memberships (
    id            bigint generated always as identity primary key,
    theme_slug    text not null references compass_themes(slug),
    ticker        text not null references compass_companies(ticker),
    member_since  date not null,
    member_until  date,
    justification text not null,
    ingested_at   timestamptz not null default now(),
    unique (theme_slug, ticker, member_since)
);

create table if not exists compass_price_bars (
    id            bigint generated always as identity primary key,
    ticker        text not null references compass_companies(ticker),
    d             date not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    adj_close     double precision not null,
    volume        bigint,
    source        text not null,
    ingested_at   timestamptz not null default now(),
    unique (ticker, d)
);

create table if not exists compass_fundamentals (
    id                  bigint generated always as identity primary key,
    ticker              text not null references compass_companies(ticker),
    fiscal_quarter_end  date not null,
    -- report_date makes no-lookahead possible in Phase 2; rows without it are unusable.
    report_date         date,
    revenue             double precision,
    operating_income    double precision,
    eps_estimate        double precision,
    eps_actual          double precision,
    surprise_pct        double precision,
    source              text not null,
    ingested_at         timestamptz not null default now(),
    unique (ticker, fiscal_quarter_end)
);

create table if not exists compass_ingest_runs (
    id            bigint generated always as identity primary key,
    started_at    timestamptz not null default now(),
    source        text not null,
    ticker        text not null,
    records       integer not null default 0,
    status        text not null,          -- 'ok' | 'error'
    error         text
);

create index if not exists compass_price_bars_ticker_d on compass_price_bars (ticker, d);
create index if not exists compass_fundamentals_ticker_report on compass_fundamentals (ticker, report_date);
