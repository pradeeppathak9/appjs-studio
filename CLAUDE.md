# appjs (monorepo)

Two independent services and an Android client in one git repo. Each has its own CLAUDE.md, which Claude loads when working
in that folder: read it before changing the service.

- `studio/`: AppJs Studio. Python via `uv` (pyproject), Alembic migrations, `web/` console.
- `restyle/`: Restyle, the Android app on Studio. Gradle (`./gradlew assembleDebug`, JDK from Android
  Studio); `local.properties` (gitignored) holds its Studio app key and Google client id. It follows
  `studio/docs/APPS_API.md`: change Studio's API first, then the app.
- `rev/`: appjs-rev payments. Python via `requirements*.txt` (no pyproject; don't add one), hand-applied
  SQL migrations (no Alembic), Celery workers, `frontend/` console. This is money movement: never call
  live Razorpay/PhonePe endpoints, and don't change idempotency, signatures or retries without a test.

## Rules

- Run commands from inside the service folder (`cd studio`, `cd rev`); there is no root toolchain.
- Don't share code between the services or add a shared package. They talk over HTTP and webhooks.
- Changing an API one side calls means changing both, in one commit when possible.
- Ports: both stacks publish Postgres on :5432; rev's backend uses :8000 (as do marktmakrs and
  fin-agent elsewhere in ~/Work). Check `lsof -i :5432 -i :8000` before starting a stack, and don't
  stop another project's containers without asking.
- Secrets live in each service's `.env` (gitignored); read `.env.example` for the keys.
- Commit messages name the part they touch, e.g. `studio: ...`, `rev: ...`, `restyle: ...`.
