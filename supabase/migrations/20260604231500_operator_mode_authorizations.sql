-- Append-only operator execution-mode authorization history (spec §2).
-- Current mode = newest accepted row. Reachable ONLY via the guarded FastAPI
-- routes (service_role); never browser->Supabase directly.

create table if not exists prescient_storage.operator_mode_authorizations (
    id                bigint generated always as identity primary key,
    status            text not null,
    requested_mode    text not null,
    previous_mode     text not null,
    active_mode       text not null,
    actor             text not null,
    reason            text not null,
    rejection_reasons jsonb not null default '[]'::jsonb,
    warnings          jsonb not null default '[]'::jsonb,
    created_at        timestamptz not null default now(),
    schema_version    integer not null default 1
);

create index if not exists operator_mode_authorizations_created_at_idx
    on prescient_storage.operator_mode_authorizations (created_at desc);

alter table prescient_storage.operator_mode_authorizations enable row level security;

grant all on prescient_storage.operator_mode_authorizations to service_role;
-- Intentionally NO policy for anon/authenticated: operator mode state is only
-- reachable through the guarded FastAPI routes.
