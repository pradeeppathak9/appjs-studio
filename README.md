# appjs

The AppJs platform: two independent services and the first client app (Android and web), in one repository.

| Folder | Service | What it does | Stack |
|---|---|---|---|
| [`infra/`](infra/) | Shared infrastructure | Postgres (schema + role per app), Redis, RabbitMQ, Caddy (HTTPS, servers) | Docker Compose |
| [`studio/`](studio/) | AppJs Studio ("creative") | Template-driven image/video generation, app users, credits and plans, admin console, and the per-app API (`/v1/app/*`) for mobile clients such as Restyle | Python (uv, FastAPI, async SQLAlchemy, Alembic) + `web/` React 19 / Mantine / Vite |
| [`restyle/`](restyle/) | Restyle (Android) | The first app on Studio (slug `restyle-ai`): pick a style, add a photo, get the restyled image; calls Studio's `/v1/app/*` | Kotlin, Jetpack Compose, Gradle |
| [`restyle-web/`](restyle-web/) | Restyle (web) | The same app in the browser: sign in, pick a style, upload, download; its nginx proxies `/v1/app/*` to Studio | React 19 / Vite / TanStack Query, nginx |
| [`rev/`](rev/) | appjs-rev (formerly autorev) | Subscription billing over Razorpay and PhonePe (UPI Autopay), with signed webhooks to client apps | `backend/` FastAPI (requirements.txt), `workers/` Celery + RabbitMQ, `frontend/` React 19 / Mantine / Vite |

They share nothing at build time: each keeps its own toolchain, Dockerfiles, `docker-compose` files,
`.env` (Restyle: `local.properties`), tests and README. Read the service's README and CLAUDE.md before changing it.

## Run

```bash
cd infra && cp -n .env.example .env && docker compose up -d   # Postgres :5432, Redis :6379, RabbitMQ (UI :15672)
cd studio && docker compose up -d --build        # api :8010, web :8080
cd rev && docker compose up -d                   # backend :8000, frontend :3000
cd rev && docker compose -f docker-compose.worker.yaml up -d   # workers, beat, flower :5555
```

[`infra/`](infra/) holds the shared services: one Postgres with a database `appjs` and a schema + role
per app (`studio`, `rev`; each sees only its own), Redis, RabbitMQ, and Caddy for HTTPS on servers.
Start it first; the apps join its Docker network `appjs`.

## How they connect

Studio's paid plans are to be charged through rev (see `studio/docs/PAYMENTS_PLAN.md`): Studio asks
rev to start a Razorpay or PhonePe subscription, and rev's signed webhooks (`subscription.activated`,
`subscription.next_payment_updated`, `subscription.revoked`, ...) tell Studio to grant or stop credits.
Nothing is wired yet.

## History

This repository started on 2026-11-23 from a snapshot of both projects, and replaced the earlier
single-service contents of github `appjs-studio` (where it now lives). Earlier history: appjs-rev's is
on github `autorev`; both projects' last pre-monorepo state is branch `wip/pre-monorepo` in the local
copies `~/Work/appjs-studio` and `~/Work/appjs-rev`.
