# appjs-studio

Template-driven image/video generation across hosted providers, with a web console and a per-app
API for mobile clients. The README is the reference; `docs/PLAN.md` explains design decisions.

## Layout

- `studio/` is the Python package (CLI entry `studio`, `cli.py`).
  - `api/` FastAPI routes · `auth/` console users, sessions, tokens · `apps/` app workspaces + app keys
  - `endusers/` app end users (phone OTP / Google sign-in, credits, plans) · `templates/` versioned templates
  - `jobs/` async job queue + worker · `providers/` Gemini / OpenAI / fal / OpenRouter / fake (fal + OpenRouter model lists in `providers/*.yaml`) · `storage/`, `media/`
  - `db/tables.py` is the schema source of truth; `migrations/` holds Alembic
- `web/`: React 19 + TS + Mantine + TanStack Query console. `web/e2e/` holds Playwright tests.
- `tests/`: pytest; `tests/smoke/` calls real providers (marker `smoke`, needs keys).
- `docs/APPS_API.md` is the contract for app clients such as `../restyle` and `../restyle-web`. Change it together with
  the `/v1/app/*` routes, never separately.

## Commands

```bash
uv sync && (cd ../infra && docker compose up -d postgres) && uv run studio db upgrade   # Postgres is in ../infra
ENABLE_FAKE_PROVIDER=true SETUP_TOKEN=dev uv run studio serve --port 8010   # API + in-process worker
cd web && npm ci && npm run dev                                               # :5173

uv run ruff check . && uv run ruff format --check . && uv run pytest         # needs compose db
cd web && npm run typecheck && npm run lint && npm test && npm run build
```

## Rules

- Use `ENABLE_FAKE_PROVIDER=true` for local work and tests. Don't call real providers (they cost money)
  unless asked; `pytest -m smoke` is the only place that does.
- Migrations: edit `studio/db/tables.py` → `uv run alembic revision --autogenerate -m "..."` → read and
  fix the generated file → `uv run pytest tests/test_webhooks_and_migrations.py`.
- Every template save makes a new version, and jobs record the version they used. Never mutate a
  saved version in place.
- Ruff: line length 110, py312, rules E F I B UP ASYNC. pytest runs asyncio in auto mode with a
  session loop.
- After changing API schemas, regenerate the web types: `web/openapi.json` → `npm run gen:api`.
- Payments are planned in `docs/PAYMENTS_PLAN.md` (engine: `../autorev`, the autorev service in this repo); nothing is wired yet.
