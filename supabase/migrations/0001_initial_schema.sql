-- Vanta warehouse — Step 1 schema.
-- Every fact table carries ingested_at (when WE learned it) for point-in-time correctness.

create table if not exists tickers (
    symbol        text primary key,
    name          text not null,
    theme         text not null,
    role          text not null,
    peer_symbols  text[] not null default '{}',
    inserted_at   timestamptz not null default now()
);

create table if not exists news (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    source        text not null,
    published_at  timestamptz,
    ingested_at   timestamptz not null default now(),
    headline      text not null,
    url           text not null,
    sentiment     double precision,
    raw           jsonb not null default '{}',
    unique (ticker, source, url)
);

create table if not exists filings (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    form_type     text not null,
    filed_at      timestamptz,
    ingested_at   timestamptz not null default now(),
    url           text not null,
    raw           jsonb not null default '{}',
    unique (ticker, url)
);

create table if not exists earnings_dates (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    report_date   date not null,
    confirmed     boolean not null default false,
    ingested_at   timestamptz not null default now(),
    unique (ticker, report_date)
);

create table if not exists estimates (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    period        text not null,
    eps_est       double precision,
    rev_est       double precision,
    eps_actual    double precision,
    surprise_pct  double precision,
    as_of         date not null,
    ingested_at   timestamptz not null default now(),
    unique (ticker, period, as_of)
);

create table if not exists prices (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    date          date not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    volume        bigint,
    ingested_at   timestamptz not null default now(),
    unique (ticker, date)
);

create table if not exists ingest_runs (
    id            bigint generated always as identity primary key,
    started_at    timestamptz not null default now(),
    source        text not null,
    ticker        text not null,
    records       integer not null default 0,
    status        text not null,          -- 'ok' | 'error'
    error         text
);
