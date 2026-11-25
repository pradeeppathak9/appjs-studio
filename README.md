# appjs

The AppJs platform: two independent services and the first client app (Android and web), in one repository.

| Folder | Service | What it does | Stack |
|---|---|---|---|
| [`infra/`](infra/) | Shared infrastructure | Postgres (schema + role per app), Redis, Caddy (HTTPS, servers) | Docker Compose |
| [`website/`](website/) | APPJS Technologies website | Company landing page served at `appjs.tech` by Caddy | Static HTML / CSS |
| [`studio/`](studio/) | AppJs Studio | Template-driven image/video generation, app users, credits and plans, admin console, and the per-app API (`/v1/app/*`) for mobile clients such as Restyle | Python (uv, FastAPI, async SQLAlchemy, Alembic) + `web/` React 19 / Mantine / Vite |
| [`restyle/`](restyle/) | Restyle (Android) | The first app on Studio (slug `restyle-ai`): pick a style, add a photo, get the restyled image; calls Studio's `/v1/app/*` | Kotlin, Jetpack Compose, Gradle |
| [`restyle-web/`](restyle-web/) | Restyle (web) | The same app in the browser: sign in, pick a style, upload, download; its nginx proxies `/v1/app/*` to Studio | React 19 / Vite / TanStack Query, nginx |
| [`autorev/`](autorev/) | autorev | Subscription billing over Razorpay and PhonePe (UPI Autopay), with signed webhooks to client apps | `backend/` FastAPI (requirements.txt), `workers/` Celery (Redis broker), `frontend/` React 19 / Mantine / Vite |

They share nothing at build time: each keeps its own toolchain, Dockerfiles, `docker-compose` files,
`.env` (Restyle: `local.properties`), tests and README. Read the service's README and CLAUDE.md before changing it.

## Run

```bash
cd infra && cp -n .env.example .env && docker compose up -d   # Postgres :5432, Redis :6379
cd studio && docker compose up -d --build        # api :8010, web :8080
cd autorev && docker compose up -d               # backend :8000, frontend :3000
cd autorev && docker compose -f docker-compose.worker.yaml up -d   # workers, beat, flower :5555
```

[`infra/`](infra/) holds the shared services: one Postgres with a database `appjs` and a schema + role
per app (`studio`, `autorev`; each sees only its own), Redis (also autorev's Celery broker), and Caddy for HTTPS on servers. RabbitMQ is disabled for now.
Start it first; the apps join its Docker network `appjs`.

## Deploy

[`fabfile.py`](fabfile.py) deploys to a server over SSH with Fabric. Put the host in `TARGETS` (or set
`APPJS_HOST` / `APPJS_USER`), then:

```bash
uvx --from fabric fab -l                 # list tasks
uvx --from fabric fab check              # SSH works, Docker is there
uvx --from fabric fab bootstrap          # first time: clone, create .env files (edit them on the server)
uvx --from fabric fab build-studio       # build + push Studio/restyle-web images (your machine)
uvx --from fabric fab deploy             # infra, then studio (autorev is switched off; --with-autorev adds it)
uvx --from fabric fab logs studio --service api --follow
uvx --from fabric fab backup             # pg_dump of every schema, downloaded to ./backups
```

## How they connect

Studio's paid plans are to be charged through autorev (see `studio/docs/PAYMENTS_PLAN.md`): Studio asks
autorev to start a Razorpay or PhonePe subscription, and autorev's signed webhooks (`subscription.activated`,
`subscription.next_payment_updated`, `subscription.revoked`, ...) tell Studio to grant or stop credits.
Nothing is wired yet.

## History

This repository started on 2026-11-23 from a snapshot of both projects, and replaced the earlier
single-service contents of github `appjs-studio` (where it now lives). Earlier history: autorev's is
on github `autorev`; both projects' last pre-monorepo state is branch `wip/pre-monorepo`.
