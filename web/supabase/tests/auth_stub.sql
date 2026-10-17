-- Local stand-in for the parts of Supabase the migration relies on, so the row-level
-- security can be tested on a plain Postgres. Never run this against a Supabase project:
-- Supabase already provides the real auth schema and roles.
create role anon nologin;
create role authenticated nologin;
create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
grant usage on schema public to anon, authenticated;
