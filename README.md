# appjs

The AppJs platform: two independent services in one repository.

| Folder | Service | What it does | Stack |
|---|---|---|---|
| [`studio/`](studio/) | AppJs Studio ("creative") | Template-driven image/video generation, app users, credits and plans, admin console, and the per-app API (`/v1/app/*`) for mobile clients such as Restyle | Python (uv, FastAPI, async SQLAlchemy, Alembic) + `web/` React 19 / Mantine / Vite |
| [`rev/`](rev/) | appjs-rev (formerly autorev) | Subscription billing over Razorpay and PhonePe (UPI Autopay), with signed webhooks to client apps | `backend/` FastAPI (requirements.txt), `workers/` Celery + RabbitMQ, `frontend/` React 19 / Mantine / Vite |

They share nothing at build time: each keeps its own toolchain, Dockerfiles, `docker-compose` files,
`.env`, tests and README. Read the service's README and CLAUDE.md before changing it.

## Run

```bash
cd studio && docker compose up -d --build        # api :8010, web :8080 (Postgres on 127.0.0.1:5432)
cd rev && docker compose up -d                   # backend :8000, frontend :3000, postgres :5432, redis :6379
cd rev && docker compose -f docker-compose.worker.yaml up -d   # rabbitmq, workers, beat, flower :5555
```

**Both publish Postgres on :5432**, so run one at a time, or move one with its compose `ports:`.
Compose project names are fixed (`creative`, `appjs-rev`, `autorev-workers`), so the containers and
database volumes are the same ones these services used before they moved here.

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
