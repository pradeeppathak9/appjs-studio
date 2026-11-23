# appjs-rev (formerly autorev)

Subscription billing and recurring-payment orchestration over PhonePe and Razorpay, with outbound
webhooks to client apps. The folder was renamed. The readme, the `AUTOREV_*` env vars, DB names
(`autorev`, `autorev_test`), the API host (`api.autorev.postkaro.app`) and the github remote still
say autorev. Don't rename those unless asked.

## Layout

- `backend/app/`: FastAPI. `router/` (one file per area: `razorpay_router`, `phonepe_router`,
  `webhooks_router`, `apps`, `admin`, `auth`, `dashboard`, `tasks_router`), `api_handler/` (provider
  HTTP clients), `models/`, `razorpay_billing.py` (per-cycle collection), `webhooks.py` (outbound).
- `backend/readme.md` documents the full Razorpay recurring flow (setup → authorize → collect →
  webhook → revoke). Read it before touching billing.
- `backend/migrations/`: **no Alembic**. The schema comes from `Base.metadata.create_all()`, and
  changes are numbered idempotent `.sql` files applied by hand with
  `python migrations/apply.py migrations/NNN_name.sql`.
- `workers/`: Celery (RabbitMQ broker) PhonePe/Razorpay sync workers + beat. Compose file:
  `docker-compose.worker.yaml`.
- `frontend/`: React 19 + Mantine console, same stack as appjs-studio's. `src/legacy/` holds pages
  not yet ported from the old CRA console; port them into `src/pages/` one at a time.

## Commands

```bash
docker compose up -d                                   # postgres :5432, redis :6379, backend :8000, frontend :3000
docker compose -f docker-compose.worker.yaml up -d     # rabbitmq, worker, beat, flower :5555

# backend tests: real routes against a throwaway DB, Razorpay HTTP replaced by a recorder
docker compose exec postgres psql -U autorev -c "CREATE DATABASE autorev_test"   # once
cd backend && uv run --python 3.12 --no-project --with-requirements requirements-dev.txt python -m pytest tests

cd frontend && VITE_API_URL=http://localhost:8000 npm run dev
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

## Rules

- Tests drop and recreate every table in `AUTOREV_TEST_DATABASE_URL`. Never point it at a real DB.
- This is money movement. Never call live PhonePe/Razorpay endpoints, and don't change idempotency,
  webhook signature or retry logic without a test that shows the before and after.
- Dependencies are pinned in `requirements*.txt`. There is no pyproject; don't add one.
- After changing API schemas, regenerate the frontend types: dump `app.openapi()` to
  `frontend/openapi.json`, then `npm run gen:api` (exact command in `frontend/readme.md`).
- Feature work usually happens on a branch (e.g. `ui-mantine-port`), so check the branch before
  committing.
