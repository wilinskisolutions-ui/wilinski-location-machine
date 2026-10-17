-- Row-level security and the account functions, exercised as four different people.
-- Run by run-local.sh after auth_stub.sql and the migration. Any failure stops the run.
\set ON_ERROR_STOP on
\set QUIET on
\o /dev/null

create schema test;
create function test.expect_error(stmt text, pattern text) returns void language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    if sqlerrm ~ pattern then return; end if;
    raise exception 'FAIL: [%] raised "%", expected /%/', stmt, sqlerrm, pattern;
  end;
  raise exception 'FAIL: [%] succeeded, expected an error matching /%/', stmt, pattern;
end $$;
create function test.expect_count(q text, n int) returns void language plpgsql as $$
declare c int;
begin
  execute 'select count(*) from (' || q || ') x' into c;
  if c <> n then raise exception 'FAIL: [%] returned % rows, expected %', q, c, n; end if;
end $$;
grant usage on schema test to anon, authenticated;
grant execute on all functions in schema test to anon, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'a@example.com'),
  ('00000000-0000-0000-0000-00000000000b', 'b@example.com'),
  ('00000000-0000-0000-0000-00000000000c', 'c@example.com'),
  ('00000000-0000-0000-0000-00000000000d', 'd@example.com');

\echo '1. A makes a couple map and saves to it'
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false) \gset
select public.create_household('couple') as hid_a \gset
insert into public.household_settings (household_id, settings) values (:'hid_a', '{"weights": {"cost": 16}}');
insert into public.pins (household_id, id, label, anchor, radius_mi) values (:'hid_a', 'p-4727740', 'Franklin, TN', '4727740', 25);
insert into public.town_notes (household_id, place_geoid, status, note) values (:'hid_a', '4708280', 'want', 'Main St on a Saturday');
select test.expect_error($$select public.create_household('single')$$, 'already_in_household');
select test.expect_count('select * from public.pins', 1);

\echo '2. B, a stranger, sees nothing of A and cannot write into it'
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false) \gset
select test.expect_count('select * from public.households', 0);
select test.expect_count('select * from public.household_settings', 0);
select test.expect_count('select * from public.pins', 0);
select test.expect_count('select * from public.town_notes', 0);
select test.expect_count('select * from public.invites', 0);
select test.expect_error(format($$insert into public.pins (household_id, id, label, anchor, radius_mi) values (%L, 'x', 'x', '4727740', 10)$$, :'hid_a'), 'row-level security');
select test.expect_error(format($$insert into public.household_members (household_id, user_id) values (%L, auth.uid())$$, :'hid_a'), 'permission denied');
select test.expect_error(format($$select public.create_invite(%L)$$, :'hid_a'), 'not_a_member');
select test.expect_error(format($$insert into public.invites (household_id) values (%L)$$, :'hid_a'), 'permission denied');
select test.expect_error($$select public.pins_limit()$$, 'permission denied|trigger functions');
-- Updates and deletes against A's rows silently touch nothing under RLS; prove A's data survived below.
update public.town_notes set note = 'hijacked' where household_id = :'hid_a';
delete from public.pins where household_id = :'hid_a';
select public.create_household('single') as hid_b \gset

\echo '3. A invites a partner; B (already has a map) is refused; C joins'
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false) \gset
select test.expect_count($$select * from public.town_notes where note = 'Main St on a Saturday'$$, 1);
select test.expect_count('select * from public.pins', 1);
select test.expect_error(format($$update public.households set created_by = auth.uid() where id = %L$$, :'hid_a'), 'permission denied');
select public.create_invite(:'hid_a') as tok \gset
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false) \gset
select test.expect_error(format($$select public.accept_invite(%L)$$, :'tok'), 'already_in_household');
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000c', false) \gset
select public.accept_invite(:'tok') = :'hid_a'::uuid as joined \gset
select test.expect_count('select * from public.pins', 1);
select test.expect_count('select * from public.household_members', 2);
insert into public.town_notes (household_id, place_geoid, status) values (:'hid_a', '4770580', 'favorite');

\echo '4. The link works once, and a full map takes nobody else'
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000d', false) \gset
select test.expect_error(format($$select public.accept_invite(%L)$$, :'tok'), 'invite_used');
select test.expect_error($$select public.accept_invite('not-a-token')$$, 'invite_not_found');
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false) \gset
select test.expect_error(format($$select public.create_invite(%L)$$, :'hid_a'), 'household_full');

\echo '5. Validation and limits hold for members too'
select test.expect_error(format($$insert into public.pins (household_id, id, label, anchor, radius_mi) values (%L, 'bad', 'x', 'not-a-geoid', 10)$$, :'hid_a'), 'check constraint');
select test.expect_error(format($$insert into public.town_notes (household_id, place_geoid, status) values (%L, '4700001', 'stalking')$$, :'hid_a'), 'check constraint');
select test.expect_error(format($$insert into public.household_settings (household_id, settings) values (%L, '[]') on conflict (household_id) do update set settings = excluded.settings$$, :'hid_a'), 'check constraint');
do $$ declare i int; begin
  for i in 1..24 loop
    insert into public.pins (household_id, id, label, anchor, radius_mi)
    select household_id, 'bulk-' || i, 'x', '4727740', 10 from public.household_members where user_id = auth.uid();
  end loop;
end $$;
select test.expect_error(format($$insert into public.pins (household_id, id, label, anchor, radius_mi) values (%L, 'one-too-many', 'x', '4727740', 10)$$, :'hid_a'), 'pin_limit');

\echo '6. Signed-out visitors read nothing'
reset role;
set role anon;
select test.expect_error('select * from public.pins', 'permission denied');
select test.expect_error($$select public.create_household('single')$$, 'permission denied');

\echo '7. Deleting an account: a partner keeps the shared map; the last one out takes it with them'
reset role;
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false) \gset
select public.delete_my_account();
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000c', false) \gset
select test.expect_count('select * from public.households', 1);
select test.expect_count('select * from public.town_notes', 2);
select public.delete_my_account();
reset role;
select test.expect_count(format('select * from public.households where id = %L', :'hid_a'), 0);
select test.expect_count(format('select * from public.pins where household_id = %L', :'hid_a'), 0);
select test.expect_count($$select * from auth.users where email in ('a@example.com', 'c@example.com')$$, 0);
select test.expect_count(format('select * from public.households where id = %L', :'hid_b'), 1);

\echo 'ALL RLS CHECKS PASSED'
