#!/usr/bin/env bash
# Apply the migration to a throwaway Postgres and run the row-level security checks.
# Needs Postgres 16 binaries (initdb, pg_ctl, psql) and must run as a non-root user.
#   web/supabase/tests/run-local.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bin="${PG_BIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"
tmp="$(mktemp -d)"
trap '"$bin/pg_ctl" -D "$tmp/data" stop -m immediate >/dev/null 2>&1 || true; rm -rf "$tmp"' EXIT
"$bin/initdb" -D "$tmp/data" -U postgres --auth=trust >/dev/null
"$bin/pg_ctl" -D "$tmp/data" -o "-k $tmp -c listen_addresses=''" -l "$tmp/log" start >/dev/null
psql=("$bin/psql" -h "$tmp" -U postgres -d postgres -v ON_ERROR_STOP=1 -q)
"${psql[@]}" -f "$here/auth_stub.sql"
"${psql[@]}" -f "$here/../migrations/0001_init.sql"
"${psql[@]}" -f "$here/rls.sql"
