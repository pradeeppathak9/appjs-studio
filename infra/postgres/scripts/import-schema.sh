#!/bin/sh
# import-schema.sh <app> <dump-file>: load a pg_dump (custom format, -Fc) of an app's old database,
# whose tables are in `public`, into schema <app> of the `appjs` database, owned by role <app>.
# Replaces whatever is in schema <app>. Run inside the postgres container:
#   docker compose cp old.dump postgres:/tmp/old.dump
#   docker compose exec postgres /scripts/import-schema.sh studio /tmp/old.dump
set -eu
app=$1
dump=$2
tmp="import_${app}_$$"
psql() { command psql -v ON_ERROR_STOP=1 -U postgres -q "$@"; }

# 1. restore into a scratch database and rename its public schema to the app's name
psql -d postgres -c "CREATE DATABASE \"$tmp\""
trap 'psql -d postgres -c "DROP DATABASE IF EXISTS \"$tmp\" WITH (FORCE)"' EXIT
pg_restore -U postgres -d "$tmp" --no-owner --no-acl --exit-on-error "$dump"
psql -d "$tmp" -c "ALTER SCHEMA public RENAME TO \"$app\""
pg_dump -U postgres -Fc -n "$app" "$tmp" > "/tmp/$tmp.dump"

# 2. load it into appjs as a throwaway role, then hand everything to the app's role
psql -d appjs -c "DROP ROLE IF EXISTS importer; CREATE ROLE importer; GRANT CREATE ON DATABASE appjs TO importer;"
psql -d appjs -c "DROP SCHEMA IF EXISTS \"$app\" CASCADE"
pg_restore -U postgres -d appjs --no-owner --no-acl --role=importer --exit-on-error "/tmp/$tmp.dump"
psql -d appjs -c "REASSIGN OWNED BY importer TO \"$app\"; DROP OWNED BY importer; DROP ROLE importer;"
rm -f "/tmp/$tmp.dump"
psql -d appjs -Atc "SELECT 'import-schema: $app has ' || count(*) || ' tables' FROM pg_tables WHERE schemaname = '$app'"
