# infra

Shared Postgres, Redis, RabbitMQ and Caddy for the appjs services. Read README.md first.

- Postgres: database `appjs`, one login role + schema per app (`studio`, `rev`), role search_path =
  its schema. Apps connect as their own role only. Never hand an app the `postgres` superuser.
- Changing roles/schemas: `postgres/scripts/add-app.sh` (idempotent). `postgres/initdb/` runs only on
  an empty data directory.
- `postgres/scripts/import-schema.sh` replaces an app's schema with a dump: confirm with the user before
  running it against data that matters, and take a `pg_dump` first.
- `docker compose down -v` here deletes every app's data (and Caddy's certificates). Don't run it
  without asking. Restarting or `down` without `-v` is safe.
- Apps reach services by name on the external network `appjs`; public sites need a Caddyfile block and
  a network alias in the app's compose.
