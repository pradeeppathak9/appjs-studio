#!/bin/sh
# add-app.sh <name> <password>: a login role <name> owning schema <name> in the `appjs` database, with
# search_path = <name>, so the app's unqualified tables live in its schema. It has no rights on other
# apps' schemas or on `public`. Also creates <name>_test, a database of its own for the app's tests.
# APP_DB_CREATEDB=true (development) lets the role create databases (studio's tests make throwaway ones).
# Safe to run again: it updates the password and settings.
set -eu
app=$1
password=$2
case "$app" in *[!a-z0-9_]* | "") echo "add-app: name must be lower-case letters, digits, _" >&2; exit 1 ;; esac
createdb=NOCREATEDB
[ "${APP_DB_CREATEDB:-false}" = "true" ] && createdb=CREATEDB

psql -v ON_ERROR_STOP=1 -U postgres -d appjs -v app="$app" -v pw="$password" -v createdb="$createdb" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L %s', :'app', :'pw', :'createdb') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', :'app', :'app') \gexec
SELECT format('ALTER ROLE %I IN DATABASE appjs SET search_path = %I', :'app', :'app') \gexec
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON DATABASE appjs FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE appjs TO %I', :'app') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app' || '_test', :'app')
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app' || '_test') \gexec
SQL
echo "add-app: $app ready (schema $app in appjs, test database ${app}_test)"
