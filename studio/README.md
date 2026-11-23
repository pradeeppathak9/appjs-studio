# creative

Generate images and videos from a prompt, or from a **template** plus your own photo, using hosted
models (Google Gemini, OpenAI Images, fal.ai, OpenRouter). Jobs run asynchronously on a worker; a web console
handles sign-in, templates, users and results.

- **Apps are workspaces.** After sign-in, users see the apps they're assigned to. In an app's
  dashboard, **editors** create, edit, delete, reorder and test its templates; **testers** run its
  active templates. The **admin** dashboard manages users, apps, who is in which app (and as what),
  and app keys.
- **Templates**: a prompt with `{{variables}}`, input-image slots, and a provider + model, owned by
  one app. Every save is a new version; jobs record the version they used.
- **App clients** (e.g. Android) call `/v1/app/*` with an app key to list the app's active
  templates and run them. Contract for app developers: [docs/APPS_API.md](docs/APPS_API.md).
- **App users** (the people using an app, e.g. Reelify) sign in per app with a phone code (SMS) or
  Google, and get a bearer session. Each template has a **credit cost**; **plans** grant credits every
  month. Admins manage an app's sign-in settings, plans and users (credits, subscriptions, blocking) in
  Admin → Apps. Payments are not connected yet: admins give plans by hand.
- Design and decisions: [docs/PLAN.md](docs/PLAN.md). Payments (Razorpay / PhonePe), planned:
  [docs/PAYMENTS_PLAN.md](docs/PAYMENTS_PLAN.md).

## Run it (Docker)

```bash
cp .env.example .env            # add provider keys, or set ENABLE_FAKE_PROVIDER=true to try it free
export UID GID=$(id -g)         # files under ./data belong to you
mkdir -p data
docker compose up --build -d
docker compose logs api | grep "setup token"
```

Open http://localhost:8080/setup, enter the setup token, and create the admin. Then, in **Admin**,
create apps, add users (each gets a temporary password, shown once, which they change at first
sign-in) and assign them to apps as editor or tester.

Services: `db` (Postgres 17, volume `pgdata`), `migrate` (runs `creative db upgrade`, then exits),
`api` (http://localhost:8010), `worker` (scale with `docker compose up -d --scale worker=3`), `web`
(http://localhost:8080). Ports are bound to 127.0.0.1 by default. To open the console to other
machines, set `WEB_BIND=0.0.0.0` in `.env` and run `docker compose up -d web`; it is plain HTTP, so
put it behind HTTPS (and set `COOKIE_SECURE=true`) before using real passwords on a shared network.

`docker compose down -v` deletes the database volume, which removes every user, template and job.

## Develop

```bash
uv sync
docker compose up -d db
uv run creative db upgrade
ENABLE_FAKE_PROVIDER=true SETUP_TOKEN=dev uv run creative serve --port 8010   # API + in-process worker
cd web && npm ci && npm run dev                                               # http://localhost:5173
```

Run the worker separately instead with `WORKER_ENABLED=false` on `serve` and `uv run creative worker`.

Tests (need the compose `db`; each run uses a throwaway database):

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
cd web && npm run typecheck && npm run lint && npm test && npm run build
```

Shell commands, also usable as `docker compose exec api creative ...`:

| Command | Does |
|---|---|
| `creative users create-admin --email ... --name ...` | create an admin without the setup page |
| `creative users reset-password --email ...` | set a password and reactivate (locked-out admin) |
| `creative tokens create --email ... --name ...` | print a new API token for a user |
| `creative db upgrade` | apply migrations |

New migration: edit `creative/db/tables.py`, then `uv run alembic revision --autogenerate -m "..."`,
read and fix the generated file, and run `uv run pytest tests/test_webhooks_and_migrations.py`.

## Use the API

Create a token under **Account** (or `creative tokens create`); it acts as you, with your role.

```bash
export CREATIVE_TOKEN=crt_...
# your apps and their ids
curl -H "Authorization: Bearer $CREATIVE_TOKEN" http://localhost:8010/v1/apps
# run a template of an app with a photo
curl -H "Authorization: Bearer $CREATIVE_TOKEN" \
     -F photo=@me.jpg -F 'variables={"mood":"rainy evening"}' \
     http://localhost:8010/v1/apps/<app id>/templates/ghibli-gemini/generations
# poll the job
curl -H "Authorization: Bearer $CREATIVE_TOKEN" http://localhost:8010/v1/generations/<job id>
# free prompt (editors of the app)
curl -H "Authorization: Bearer $CREATIVE_TOKEN" -H "Content-Type: application/json" \
     -d '{"prompt":"a red bicycle on a beach","media_type":"image","n":2}' \
     http://localhost:8010/v1/apps/<app id>/generations
```

Or with the CLI: `uv run creative generate --app <app id> --template ghibli-gemini --image photo=me.jpg --var mood=rainy`.

Full API reference: http://localhost:8010/docs.

## Configuration

All settings come from the environment or `.env`; see [.env.example](.env.example) for the full
list with defaults. The most used:

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY`, `OPENROUTER_API_KEY` | – | enable each provider |
| `FAL_MODELS_FILE`, `OPENROUTER_MODELS_FILE` | packaged YAML | which fal / OpenRouter models are enabled (see Provider notes) |
| `ENABLE_FAKE_PROVIDER` | `false` | deterministic local provider (prompt keywords `FAIL_TRANSIENT`, `FAIL_TRANSIENT:<k>`, `FAIL_POLICY`, `SLEEP:<s>`) |
| `SETUP_TOKEN` | generated | token for the first-run setup page |
| `DATABASE_URL` | `postgresql://creative:creative@localhost:5432/creative` | Postgres |
| `DATA_DIR` | `./data` | outputs, uploaded inputs, reference images |
| `WORKER_CONCURRENCY` | `2` | jobs per worker process |
| `COOKIE_SECURE` | `false` | set `true` behind HTTPS |
| `WEBHOOK_SECRET` | – | HMAC-SHA256 signature on webhooks (`X-Creative-Signature`) |
| `SMS_PROVIDER` | `log` | `log` writes sign-in codes to the api log (dev); `msg91` sends them (`MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`). Fallback for apps without their own MSG91 account or Firebase, set in App settings → Sign-in |
| `SECRETS_KEY` | unset | encrypts credentials entered in the console (an app's MSG91 auth key); any long random string. Needed before such credentials can be saved |
| `OTP_SECRET` | random | key for stored sign-in codes; set it in production so codes survive restarts |
| `OTP_TEST_NUMBERS` | – | fixed codes for store reviewers, no SMS sent (`+919999999999:123456,…`) |

## Provider notes

fal and OpenRouter accept only the models listed with `enabled: true` in
[creative/providers/fal.yaml](creative/providers/fal.yaml) and
[creative/providers/openrouter.yaml](creative/providers/openrouter.yaml). Requests and templates
naming any other model get a 422 on `model`. The files also hold each provider's default models,
aspect ratios and per-model input-image support (for fal, the argument name each endpoint uses).
Edit them in place, or set `FAL_MODELS_FILE` / `OPENROUTER_MODELS_FILE` to a mounted copy. Changes
apply on restart, and an invalid file stops startup with the reason.

OpenRouter is image-only. It goes through the chat completions API with `modalities`
(`["image", "text"]`, or `["image"]` for image-only models such as Flux) and
`image_config.aspect_ratio`. Each call returns one image, so `n` > 1 makes parallel calls.

Model IDs and request shapes were checked against the installed SDKs (google-genai 2.34,
openai 3.42, fal-client 1.0). Still to confirm with real keys: Gemini image input and the video
`duration` format (`"6s"`), and the fal image-to-image endpoints (`fal-ai/flux-pro/kontext`,
`fal-ai/nano-banana/edit`) and their argument names. `uv run pytest -m smoke` is reserved for those
checks once keys are available.
