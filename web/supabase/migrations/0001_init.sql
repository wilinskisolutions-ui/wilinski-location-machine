-- Wilinski Atlas: accounts, households and saved maps.
--
-- Run once in the Supabase SQL editor (or `supabase db push`). Safe to read top to bottom:
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

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- tables

create table public.households (
  id          uuid primary key default gen_random_uuid(),
  mode        text not null default 'single' check (mode in ('single', 'couple')),
  -- set null, not cascade: when the person who made a couple's map deletes their
  -- account, the map stays with their partner.
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now()
);

create table public.household_members (
  household_id uuid not null references public.households (id) on delete cascade,
  user_id      uuid not null references auth.users (id) on delete cascade,
  joined_at    timestamptz not null default now(),
  primary key (household_id, user_id)
);
-- One map per person: joining a partner's map means leaving your own first.
create unique index household_members_one_per_user on public.household_members (user_id);

create table public.household_settings (
  household_id uuid primary key references public.households (id) on delete cascade,
  settings     jsonb not null,
  updated_at   timestamptz not null default now(),
  updated_by   uuid default auth.uid(),
  constraint settings_is_object check (jsonb_typeof(settings) = 'object'),
  constraint settings_is_small check (pg_column_size(settings) < 32768)
);

create table public.pins (
  household_id uuid not null references public.households (id) on delete cascade,
  id           text not null check (char_length(id) between 1 and 80),
  label        text not null check (char_length(label) between 1 and 120),
  anchor       text not null check (anchor ~ '^[0-9]{5}([0-9]{2})?$'),  -- county or place GEOID
  radius_mi    integer not null check (radius_mi between 5 and 60),
  sort         integer not null default 0,
  updated_at   timestamptz not null default now(),
  primary key (household_id, id)
);

create table public.town_notes (
  household_id uuid not null references public.households (id) on delete cascade,
  place_geoid  text not null check (place_geoid ~ '^[0-9]{7}$'),
  status       text check (status in ('want', 'visited', 'favorite', 'ruled-out')),
  note         text check (char_length(note) <= 4000),
  updated_at   timestamptz not null default now(),
  updated_by   uuid default auth.uid(),
  primary key (household_id, place_geoid)
);

create table public.invites (
  token        text primary key default encode(gen_random_bytes(18), 'hex'),
  household_id uuid not null references public.households (id) on delete cascade,
  created_by   uuid not null references auth.users (id) on delete cascade,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null default now() + interval '7 days',
  used_by      uuid references auth.users (id) on delete set null,
  used_at      timestamptz
);

-- Pins per household are few by design; cap them so one account cannot fill the database.
create function public.pins_limit() returns trigger language plpgsql as $$
begin
  if (select count(*) from public.pins where household_id = new.household_id) >= 25 then
    raise exception 'pin_limit' using hint = 'A map holds at most 25 pinned areas.';
  end if;
  return new;
end $$;
create trigger pins_limit before insert on public.pins for each row execute function public.pins_limit();

create function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
create trigger touch before update on public.household_settings for each row execute function public.touch_updated_at();
create trigger touch before update on public.pins for each row execute function public.touch_updated_at();
create trigger touch before update on public.town_notes for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------- membership check

-- SECURITY DEFINER so policies can ask "is this person a member?" without the policy on
-- household_members recursing into itself.
create function public.is_member(hid uuid) returns boolean
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

-- Signed-out visitors get nothing from any table.
revoke all on all tables in schema public from anon;
grant select, insert, update, delete on public.household_settings, public.pins, public.town_notes to authenticated;
grant select on public.households to authenticated;
grant update (mode) on public.households to authenticated;  -- nothing else is editable
grant select on public.household_members, public.invites to authenticated;

-- ---------------------------------------------------------------- functions

-- A brand-new account makes its own map. Fails if the person already has one.
create function public.create_household(p_mode text default 'single') returns uuid
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
create function public.create_invite(p_household uuid) returns text
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
create function public.accept_invite(p_token text) returns uuid
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
create function public.delete_my_account() returns void
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
  public.accept_invite(text), public.delete_my_account(), public.is_member(uuid) from public, anon;
grant execute on function public.create_household(text), public.create_invite(uuid),
  public.accept_invite(text), public.delete_my_account(), public.is_member(uuid) to authenticated;

-- ---------------------------------------------------------------- live updates for couples

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.household_settings, public.pins, public.town_notes;
  end if;
end $$;
