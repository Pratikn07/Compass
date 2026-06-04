create schema if not exists prescient_storage;

revoke all on schema prescient_storage from anon, authenticated;
revoke all on all tables in schema prescient_storage from anon, authenticated;
alter default privileges in schema prescient_storage revoke all on tables from anon, authenticated;

grant usage on schema prescient_storage to service_role;
alter default privileges in schema prescient_storage grant all on tables to service_role;

create table if not exists prescient_storage.runs (
    run_id text primary key,
    trigger_type text,
    scheduled_date date,
    "current_date" date,
    window_start date,
    window_end date,
    status text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.journal_records (
    journal_record_id text primary key,
    record_type text not null,
    run_id text not null,
    decision_id text,
    decision_index integer,
    trading_date date not null,
    created_at timestamptz not null default now(),
    target text,
    theme text,
    strategy_type text,
    strategy_status text,
    execution_mode text,
    source text not null,
    provider text,
    order_id text,
    parent_record_id text,
    duplicate_of_record_id text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1
);

create table if not exists prescient_storage.decision_records (
    decision_record_id text primary key,
    run_id text not null,
    decision_id text not null,
    decision_index integer,
    trading_date date not null,
    target text,
    theme text,
    strategy_type text,
    strategy_status text,
    execution_mode text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.lifecycle_records (
    lifecycle_record_id text primary key,
    run_id text not null,
    decision_id text,
    journal_record_id text,
    record_type text not null,
    trading_date date not null,
    target text,
    theme text,
    order_id text,
    outcome_type text,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.provider_snapshots (
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
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.provider_errors (
    provider_error_id text primary key,
    provider text not null,
    error_type text not null,
    run_id text,
    target text,
    source text,
    message text not null,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.learning_reports (
    learning_report_id text primary key,
    run_id text,
    report_date date not null,
    target text,
    theme text,
    report_type text not null,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

create table if not exists prescient_storage.storage_write_audit (
    storage_write_audit_id text primary key,
    provider text not null,
    table_name text not null,
    run_id text,
    attempted_record_count integer not null default 0,
    written_record_count integer not null default 0,
    error_count integer not null default 0,
    payload jsonb not null default '{}'::jsonb,
    schema_version integer not null default 1,
    created_at timestamptz not null default now()
);

alter table prescient_storage.runs enable row level security;
alter table prescient_storage.journal_records enable row level security;
alter table prescient_storage.decision_records enable row level security;
alter table prescient_storage.lifecycle_records enable row level security;
alter table prescient_storage.provider_snapshots enable row level security;
alter table prescient_storage.provider_errors enable row level security;
alter table prescient_storage.learning_reports enable row level security;
alter table prescient_storage.storage_write_audit enable row level security;

grant all on all tables in schema prescient_storage to service_role;

create index if not exists journal_records_run_id_idx
    on prescient_storage.journal_records (run_id);

create index if not exists journal_records_decision_id_idx
    on prescient_storage.journal_records (decision_id);

create index if not exists journal_records_trading_date_record_type_idx
    on prescient_storage.journal_records (trading_date, record_type);

create index if not exists journal_records_target_theme_idx
    on prescient_storage.journal_records (target, theme);

create index if not exists journal_records_unresolved_outcomes_idx
    on prescient_storage.journal_records (run_id, decision_id)
    where record_type in ('trade_outcome', 'outcome_correction')
      and coalesce(payload ->> 'outcome_type', 'unknown') in ('pending', 'unknown');

create index if not exists decision_records_run_decision_idx
    on prescient_storage.decision_records (run_id, decision_id);

create index if not exists lifecycle_records_run_decision_idx
    on prescient_storage.lifecycle_records (run_id, decision_id);

create index if not exists lifecycle_records_order_id_idx
    on prescient_storage.lifecycle_records (order_id);

create index if not exists provider_snapshots_provider_target_idx
    on prescient_storage.provider_snapshots (provider, target, retrieved_at desc);

create index if not exists provider_snapshots_source_id_idx
    on prescient_storage.provider_snapshots (provider, source_id);

create index if not exists provider_errors_provider_error_type_idx
    on prescient_storage.provider_errors (provider, error_type, created_at desc);

create index if not exists learning_reports_run_id_idx
    on prescient_storage.learning_reports (run_id);

create index if not exists learning_reports_report_date_idx
    on prescient_storage.learning_reports (report_date, report_type);

create index if not exists storage_write_audit_run_id_idx
    on prescient_storage.storage_write_audit (run_id, created_at desc);
