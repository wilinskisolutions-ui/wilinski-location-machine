-- Wilinski Atlas: accounts, households and saved maps.
--
-- Paste the whole file into Supabase -> SQL Editor -> New query, and press Run. If
-- Supabase warns about a "destructive operation", choose "Run this query": the only
-- deletes in this file are inside the delete-my-account function. Safe to run again.
--
--   households          one map: a single person, or a couple sharing one
--   household_members   who belongs to which household (at most two people)
--   household_settings  the map's settings: weights, budget, climate, layer opt-ins (jsonb)
--   pins                areas on the map (a radius around a town or county)
--   town_notes          per-town status (want to visit, visited...) and notes
--   invites             one-time links that let a partner join a couple's map
--
-- Every table has row-level security: a signed-in person reads and writes only rows of a
-- household they belong to. Creating a household, joining one and deleting an account go
-- through the functions at the bottom, which check the rules themselves.
--
-- Stored on purpose: settings, pins, notes. Not stored: names, addresses, or any label
-- for a sensitive answer. A sensitive layer is kept only as the weight and direction the
-- person chose, inside settings.
--
-- Written for Supabase's defaults: no extension is needed (extensions live in their own
-- schema there), and because Supabase grants every new table to anon and authenticated,
-- privileges are revoked first and then granted back one by one.

-- ---------------------------------------------------------------- tables

create table if not exists public.households (
  id          uuid primary key default gen_random_uuid(),
  mode        text not null default 'single' check (mode in ('single', 'couple')),
  -- set null, not cascade: when the person who made a couple's map deletes their
  -- account, the map stays with their partner.
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now()
);

create table if not exists public.household_members (
  household_id uuid not null references public.households (id) on delete cascade,
  user_id      uuid not null references auth.users (id) on delete cascade,
  joined_at    timestamptz not null default now(),
  primary key (household_id, user_id)
);
-- One map per person: joining a partner's map means leaving your own first.
create unique index if not exists household_members_one_per_user on public.household_members (user_id);

create table if not exists public.household_settings (
  household_id uuid primary key references public.households (id) on delete cascade,
  settings     jsonb not null,
  updated_at   timestamptz not null default now(),
  updated_by   uuid default auth.uid(),
  constraint settings_is_object check (jsonb_typeof(settings) = 'object'),
  constraint settings_is_small check (pg_column_size(settings) < 32768)
);

create table if not exists public.pins (
  household_id uuid not null references public.households (id) on delete cascade,
  id           text not null check (char_length(id) between 1 and 80),
  label        text not null check (char_length(label) between 1 and 120),
  anchor       text not null check (anchor ~ '^[0-9]{5}([0-9]{2})?$'),  -- county or place GEOID
  radius_mi    integer not null check (radius_mi between 5 and 60),
  sort         integer not null default 0,
  updated_at   timestamptz not null default now(),
  primary key (household_id, id)
);

create table if not exists public.town_notes (
  household_id uuid not null references public.households (id) on delete cascade,
  place_geoid  text not null check (place_geoid ~ '^[0-9]{7}$'),
  status       text check (status in ('want', 'visited', 'favorite', 'ruled-out')),
  note         text check (char_length(note) <= 4000),
  updated_at   timestamptz not null default now(),
  updated_by   uuid default auth.uid(),
  primary key (household_id, place_geoid)
);

create table if not exists public.invites (
  -- Two random UUIDs, dashes removed: 64 hex characters from Postgres's built-in
  -- generator, so no extension is needed.
  token        text primary key
               default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  household_id uuid not null references public.households (id) on delete cascade,
  created_by   uuid references auth.users (id) on delete cascade,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null default now() + interval '7 days',
  used_by      uuid references auth.users (id) on delete set null,
  used_at      timestamptz
);

-- Pins per household are few by design; cap them so one account cannot fill the database.
create or replace function public.pins_limit() returns trigger language plpgsql as $$
begin
  if (select count(*) from public.pins where household_id = new.household_id) >= 25 then
    raise exception 'pin_limit' using hint = 'A map holds at most 25 pinned areas.';
  end if;
  return new;
end $$;
drop trigger if exists pins_limit on public.pins;
create trigger pins_limit before insert on public.pins for each row execute function public.pins_limit();

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists touch on public.household_settings;
drop trigger if exists touch on public.pins;
drop trigger if exists touch on public.town_notes;
create trigger touch before update on public.household_settings for each row execute function public.touch_updated_at();
create trigger touch before update on public.pins for each row execute function public.touch_updated_at();
create trigger touch before update on public.town_notes for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------- membership check

-- SECURITY DEFINER so policies can ask "is this person a member?" without the policy on
-- household_members recursing into itself.
create or replace function public.is_member(hid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.household_members m
    where m.household_id = hid and m.user_id = auth.uid()
  );
$$;

-- ---------------------------------------------------------------- row-level security

alter table public.households enable row level security;
alter table public.household_members enable row level security;
alter table public.household_settings enable row level security;
alter table public.pins enable row level security;
alter table public.town_notes enable row level security;
alter table public.invites enable row level security;

drop policy if exists households_read on public.households;
drop policy if exists households_update on public.households;
drop policy if exists members_read on public.household_members;
drop policy if exists settings_all on public.household_settings;
drop policy if exists pins_all on public.pins;
drop policy if exists notes_all on public.town_notes;
drop policy if exists invites_read on public.invites;

create policy households_read on public.households for select to authenticated
  using (public.is_member(id));
-- Mode changes (single -> couple) by a member; creation only through create_household().
create policy households_update on public.households for update to authenticated
  using (public.is_member(id)) with check (public.is_member(id));

create policy members_read on public.household_members for select to authenticated
  using (public.is_member(household_id));
-- No insert/update/delete policies: joining and leaving go through the functions below.

create policy settings_all on public.household_settings for all to authenticated
  using (public.is_member(household_id)) with check (public.is_member(household_id));
create policy pins_all on public.pins for all to authenticated
  using (public.is_member(household_id)) with check (public.is_member(household_id));
create policy notes_all on public.town_notes for all to authenticated
  using (public.is_member(household_id)) with check (public.is_member(household_id));

create policy invites_read on public.invites for select to authenticated
  using (public.is_member(household_id));
-- Invites are created through create_invite(); nobody reads another household's tokens.

-- Privileges: Supabase grants every new table to anon and authenticated, so take it all
-- away first, then give back exactly what the app uses. Signed-out visitors get nothing.
revoke all on public.households, public.household_members, public.household_settings,
  public.pins, public.town_notes, public.invites from anon, authenticated;
grant select, insert, update, delete on public.household_settings, public.pins, public.town_notes to authenticated;
grant select on public.households, public.household_members, public.invites to authenticated;
grant update (mode) on public.households to authenticated;  -- nothing else there is editable

-- ---------------------------------------------------------------- functions

-- A brand-new account makes its own map. Fails if the person already has one.
create or replace function public.create_household(p_mode text default 'single') returns uuid
language plpgsql security definer set search_path = public as $$
declare hid uuid;
begin
  if auth.uid() is null then raise exception 'not_signed_in'; end if;
  if exists (select 1 from household_members where user_id = auth.uid()) then
    raise exception 'already_in_household';
  end if;
  insert into households (mode, created_by)
    values (case when p_mode = 'couple' then 'couple' else 'single' end, auth.uid())
    returning id into hid;
  insert into household_members (household_id, user_id) values (hid, auth.uid());
  return hid;
end $$;

-- A member of a couple's map makes a one-time link for their partner.
create or replace function public.create_invite(p_household uuid) returns text
language plpgsql security definer set search_path = public as $$
declare tok text;
begin
  if not is_member(p_household) then raise exception 'not_a_member'; end if;
  if (select count(*) from household_members where household_id = p_household) >= 2 then
    raise exception 'household_full';
  end if;
  update households set mode = 'couple' where id = p_household;
  insert into invites (household_id, created_by) values (p_household, auth.uid())
    returning token into tok;
  return tok;
end $$;

-- The partner opens the link and joins. One map per person, two people per map.
create or replace function public.accept_invite(p_token text) returns uuid
language plpgsql security definer set search_path = public as $$
declare inv invites%rowtype;
begin
  if auth.uid() is null then raise exception 'not_signed_in'; end if;
  select * into inv from invites where token = p_token for update;
  if not found then raise exception 'invite_not_found'; end if;
  if inv.used_at is not null then raise exception 'invite_used'; end if;
  if inv.expires_at < now() then raise exception 'invite_expired'; end if;
  if exists (select 1 from household_members where household_id = inv.household_id and user_id = auth.uid()) then
    return inv.household_id;  -- already joined: opening the link twice is harmless
  end if;
  if exists (select 1 from household_members where user_id = auth.uid()) then
    raise exception 'already_in_household';
  end if;
  if (select count(*) from household_members where household_id = inv.household_id) >= 2 then
    raise exception 'household_full';
  end if;
  insert into household_members (household_id, user_id) values (inv.household_id, auth.uid());
  update invites set used_by = auth.uid(), used_at = now() where token = p_token;
  return inv.household_id;
end $$;

-- Delete the signed-in account. A map nobody belongs to any more is deleted with it
-- (pins, notes, settings, invites cascade); a couple's map stays with the partner.
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = public, auth as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'not_signed_in'; end if;
  delete from public.households h
   where h.id in (select household_id from public.household_members where user_id = me)
     and (select count(*) from public.household_members m where m.household_id = h.id) = 1;
  delete from public.household_members where user_id = me;
  delete from auth.users where id = me;
end $$;

revoke all on function public.create_household(text), public.create_invite(uuid),
  public.accept_invite(text), public.delete_my_account(), public.is_member(uuid),
  public.pins_limit(), public.touch_updated_at() from public, anon, authenticated;
grant execute on function public.create_household(text), public.create_invite(uuid),
  public.accept_invite(text), public.delete_my_account(), public.is_member(uuid) to authenticated;

-- ---------------------------------------------------------------- live updates for couples

do $$
declare t text;
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach t in array array['household_settings', 'pins', 'town_notes'] loop
      if not exists (select 1 from pg_publication_tables
                     where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
        execute format('alter publication supabase_realtime add table public.%I', t);
      end if;
    end loop;
  end if;
end $$;
