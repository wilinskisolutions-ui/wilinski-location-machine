-- Local stand-in for what a Supabase project already has, so the migration and its
-- row-level security can be tested on a plain Postgres. Never run this against Supabase.
--
-- Kept deliberately close to Supabase's real defaults, because the first version of the
-- migration passed a bare Postgres and failed on Supabase:
--   * extensions live in their own `extensions` schema, NOT on the search path here
--     (the strictest case: if the migration works without it, it works with it);
--   * every new table and function in `public` is granted to anon and authenticated by
--     default, so the migration must take privileges away explicitly, not just add them.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema extensions;
create extension pgcrypto with schema extensions;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
