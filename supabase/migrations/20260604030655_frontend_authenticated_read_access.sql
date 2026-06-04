-- Frontend dashboard read access for the single-operator Slice 0 web shell.
-- The browser reads prescient_storage through Supabase with the authenticated
-- role only. It never receives write grants and never receives service-role
-- credentials.

grant usage on schema prescient_storage to authenticated;
grant select on all tables in schema prescient_storage to authenticated;

drop policy if exists authenticated_read on prescient_storage.runs;
create policy authenticated_read on prescient_storage.runs
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.journal_records;
create policy authenticated_read on prescient_storage.journal_records
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.decision_records;
create policy authenticated_read on prescient_storage.decision_records
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.lifecycle_records;
create policy authenticated_read on prescient_storage.lifecycle_records
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.provider_snapshots;
create policy authenticated_read on prescient_storage.provider_snapshots
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.provider_errors;
create policy authenticated_read on prescient_storage.provider_errors
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.learning_reports;
create policy authenticated_read on prescient_storage.learning_reports
    for select to authenticated
    using (true);

drop policy if exists authenticated_read on prescient_storage.storage_write_audit;
create policy authenticated_read on prescient_storage.storage_write_audit
    for select to authenticated
    using (true);
