# infra

Shared infrastructure for the appjs services, the same locally and on servers.

| Service | For | Reach it (Docker network `appjs`) | Host port (127.0.0.1) |
|---|---|---|---|
| Postgres 17 | studio, autorev | `postgres:5432`, database `appjs` | 5432 |
| Redis 7 | autorev (db 0, Celery broker db 1) | `redis:6379` | 6379 |
| Caddy 2 | HTTPS for public domains (servers: `--profile edge`) | | 80, 443 (public) |

```bash
cp .env.example .env               # development defaults are fine locally
docker compose up -d               # postgres, redis
docker compose --profile edge up -d   # servers: + caddy
```

Start infra before the apps: their compose files join the external network `appjs`.

## Postgres: one database, a schema per app

Every app has a **login role and a schema of the same name** in database `appjs` (`studio`, `autorev`).
The role's `search_path` is its schema, so the app's tables live there without any code knowing about
schemas, and it has no rights on the other apps' schemas or on `public`.

| App | Connects as | URL inside Docker |
|---|---|---|
| studio | `studio` | `postgresql://studio:<pw>@postgres:5432/appjs` |
| autorev | `autorev` | `postgresql://autorev:<pw>@postgres:5432/appjs` |

Each app also gets a database `<app>_test` of its own (owned by its role) for its tests. Locally,
`APP_DB_CREATEDB=true` also lets app roles create databases (studio's tests make throwaway ones);
keep it `false` on servers.

Roles, schemas and test databases are created on Postgres's first start
([`postgres/initdb`](postgres/initdb)). Later:

```bash
docker compose exec postgres /scripts/add-app.sh newapp <password>   # a new app (or a new password)
docker compose exec postgres psql -U postgres -d appjs                # superuser shell
```

### Moving an app's existing database in

An app that used to have its own database (tables in `public`) is loaded into its schema with
[`postgres/scripts/import-schema.sh`](postgres/scripts/import-schema.sh). It replaces that schema.

```bash
pg_dump -Fc -U <old-user> <old-db> > old.dump          # wherever the old database runs
docker compose cp old.dump postgres:/tmp/old.dump
docker compose exec postgres /scripts/import-schema.sh autorev /tmp/old.dump
```

Local data was moved this way on 2026-11-23: studio's from the `creative_pgdata` volume, autorev's from
`autorev_pgdata`. Those old volumes are untouched; delete them once you no longer need them
(`docker volume rm creative_pgdata autorev_pgdata`).

### Backups

```bash
docker compose exec -T postgres pg_dump -U postgres -n studio appjs | gzip > studio-$(date +%F).sql.gz
docker compose exec -T postgres pg_dump -U postgres -Fc appjs > appjs-$(date +%F).dump   # every schema
```

## Caddy (servers)

[`caddy/Caddyfile`](caddy/Caddyfile) lists the public sites; domains come from `.env`
(`APPJS_DOMAIN`, `STUDIO_DOMAIN`, `STUDIO_API_DOMAIN`, `RESTYLE_DOMAIN`). `APPJS_DOMAIN` serves the static
company site from `../website`; the other sites proxy to network aliases that each app's
compose file sets on the `appjs` network (`studio-web`, `studio-api`, `restyle-web`). A new site is a
block in the Caddyfile plus an alias in the app's compose, then `docker compose --profile edge up -d caddy`.
