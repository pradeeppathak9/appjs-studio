# appjs (monorepo)

Two independent services and an Android client in one git repo. Each has its own CLAUDE.md, which Claude loads when working
in that folder: read it before changing the service.

- `infra/`: shared Postgres (database `appjs`, a schema + login role per app), Redis, Caddy.
  Start it before any app. New app: `docker compose exec postgres /scripts/add-app.sh <name> <pw>`.
- `website/`: APPJS Technologies company site (`index.html`), served at `appjs.tech` by Caddy.
- `studio/`: AppJs Studio. Python via `uv` (pyproject), Alembic migrations, `web/` console.
- `restyle/`: Restyle, the Android app on Studio. Gradle (`./gradlew assembleDebug`, JDK from Android
  Studio); `local.properties` (gitignored) holds its Studio app key and Google client id. It follows
  `studio/docs/APPS_API.md`: change Studio's API first, then the app.
- `restyle-web/`: the Restyle web app (React + Vite, `npm run dev` on :5180 proxies /v1 to Studio on
  :8010; key in `.env.local`). Same API contract as the Android app; its Docker image's nginx only
  forwards `/v1/app/*`.
- `autorev/`: autorev payments. Python via `requirements*.txt` (no pyproject; don't add one), hand-applied
  SQL migrations (no Alembic), Celery workers, `frontend/` console. This is money movement: never call
  live Razorpay/PhonePe endpoints, and don't change idempotency, signatures or retries without a test.

## Rules

- Run commands from inside the service folder (`cd studio`, `cd autorev`); there is no root toolchain.
- Don't share code between the services or add a shared package. They talk over HTTP and webhooks.
- Changing an API one side calls means changing both, in one commit when possible.
- Ports: infra publishes Postgres :5432 and Redis :6379 on 127.0.0.1 (RabbitMQ is disabled; Celery uses Redis); autorev's
  backend uses :8000 (as do marktmakrs and fin-agent elsewhere in ~/Work). Check `lsof -i :8000`
  before starting autorev, and don't stop another project's containers without asking.
- Databases: an app only ever touches its own schema, connecting as its own role. Never give an app
  the `postgres` superuser, and never point tests at `appjs` (studio's make throwaway databases;
  autorev's use `autorev_test`).
- Secrets live in each service's `.env` (gitignored); read `.env.example` for the keys.
- Commit messages name the part they touch, e.g. `studio: ...`, `autorev: ...`, `restyle: ...`, `restyle-web: ...`.
