#!/bin/sh
# First start only (empty data dir): a login role and a schema per app, in the `appjs` database.
# Later apps: docker compose exec postgres /scripts/add-app.sh <name> <password>
set -eu
for app in ${APP_SCHEMAS:-studio autorev}; do
  var=$(echo "$app" | tr '[:lower:]-' '[:upper:]_')_DB_PASSWORD
  eval "password=\${$var:-}"
  [ -n "$password" ] || { echo "initdb: $var is not set" >&2; exit 1; }
  /scripts/add-app.sh "$app" "$password"
done
