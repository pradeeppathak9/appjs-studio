# Plan: `studio` — prompt-to-image/video backend with templates

## Context

Greenfield Python service in `~/aarki/creative`.
It accepts a text prompt, or a template plus the user's own image, and produces an image or a video via hosted generation APIs.
Decisions already made with the user:

- Providers: Google Gemini API (image + video), OpenAI Images API (image only), fal.ai (image + video). Each is enabled only if its key is set.
- Async job model: POST returns a job id; client polls, optional webhook. A background worker does the generation.
- Storage v1: files on local disk (behind an interface so S3 can be swapped in later); job records and the job queue in **PostgreSQL, run as a container in the compose stack** (user, 2026-10-31; replaces the earlier SQLite plan).
- General-purpose service, not ad-creative specific.
- Deployment shape (user, 2026-10-31): dockerized, with the **web service and the generation worker as separate containers** built from one image, sharing an assets volume, plus a **`db` (Postgres) container**.

Conventions borrowed from sibling repos (`ml-platform/pyproject.toml`, `ml-lab/webservice`): Python >= 3.10, FastAPI, pydantic v2 + pydantic-settings `Settings` in `config.py`, httpx, uv + `uv.lock`, setuptools, ruff (line-length 110), pytest, multi-stage slim Dockerfile with non-root user, docker-compose.

Frontend (user, 2026-10-31): a React + Vite app in `web/` for using and testing the service: sign-in, running templates, building templates, managing users, watching jobs. See "Stack" for the libraries.

Templates (user, 2026-10-31): a creator makes **templates** in the frontend. A template is a prompt (editable by its creators), one or more input-image slots, and a provider + model (switchable). Example: *"Ghibli Image Generation with Gemini"*. An API client then calls the template by ID with an uploaded image; the backend combines the template's prompt with that image and generates a new image. Details in "Templates" below.

Accounts (user, 2026-10-31): the frontend has a **login**. The **first user is the admin**; the admin creates the other users, each either a **creator** (creates and modifies templates) or a **tester** (may only run the active, preset templates). Details in "Accounts, login and roles" below.

Decisions taken in this plan (change them here if wrong):
- Three roles: `admin` > `creator` > `tester`; each role can do everything the roles below it can. The admin also manages users.
- Sign-in is email + password with a server-side session cookie. API clients (scripts, other services) use personal API tokens that act as the user who created them, with that user's role.
- The prompt belongs to creators. A tester can't replace it, only fill `{{variables}}` the creator put in it, and never sees the prompt text.
- "Switchable model": the creator picks the provider + model, and can also list `allowed_models` that a caller may choose from per request.
- All creators can edit all templates (one shared team library); each version records who made it.
- Testers see only their own jobs; creators and admins see all jobs.
- Every edit creates a new immutable template version; a job records the version it used.
- v1 templates produce **images** from input images (image -> image). Image -> video is a follow-up; the schema already allows it.

## Stack (reviewed 2026-10-31, after accounts and templates were added)

The scope grew from "prompt in, image out" to accounts, three roles, versioned templates and a multi-page console. The stack was re-checked against that; the user said to change whatever fits better.

| Area | Choice | Why |
|---|---|---|
| API | **FastAPI** + pydantic v2 (unchanged) | Async (long provider calls, uploads), typed request/response models, and the OpenAPI schema the frontend types are generated from. Matches sibling repos. |
| Database | **Postgres 17** in compose (unchanged) | Relational data (users, templates, versions, jobs), `SKIP LOCKED` queue, `LISTEN/NOTIFY`, advisory locks; one store for everything. |
| DB access | **SQLAlchemy 2.0 async** (asyncpg driver) — *changed from raw asyncpg* | About 12 tables with relations and many CRUD endpoints now. Typed table models and Core queries remove most hand-written SQL; the queue's claim, finalize and stale-sweep statements stay explicit (`with_for_update(skip_locked=True)` / `text()`), because their exact SQL is the point. |
| Migrations | **Alembic** — *changed from home-made numbered SQL files* | Autogenerate as a starting point (reviewed by hand), real revision history, and `alembic check` in tests to catch models drifting from migrations. Run once per deploy by a `migrate` compose service instead of by every process at startup. |
| Job queue | **Own Postgres queue** (unchanged) | ~200 lines with claim fencing, heartbeats and stale requeue already designed. Celery/arq would add Redis and still need the same heartbeat logic for 15-minute video jobs; procrastinate (a Postgres queue library) was considered, but the custom fencing rules would have to be bent around it. |
| Auth | **Own, small** (argon2id passwords, DB sessions in an HttpOnly cookie, hashed API tokens) | Needs are narrow: email/password, three roles, admin-created users, tokens. fastapi-users is in maintenance mode and centred on JWTs; Keycloak/Authentik would be a bigger service to run than this whole app. SSO can replace the login step later without touching roles. |
| Frontend | **React 19 + Vite + TypeScript** (unchanged apart from React 19) | Fast dev loop, static build served by nginx. |
| Routing | **React Router** (library mode, normal paths like `/templates/<id>`) — *changed from a hand-written hash switch* | Login redirects, role guards and about 10 pages; nginx already falls back to `index.html`. |
| Server state | **TanStack Query** — *replaces the hand-written polling hook* | Polling with `refetchInterval` that stops at a terminal status, caching, mutations with invalidation (save template -> list refreshes), retry and 401 handling in one place. |
| UI kit | **Mantine** (core, form, dropzone, notifications) — *was "no UI kit"* | Ready tables, modals, file drop zones with previews, form validation and toasts; the template editor and users page are form-heavy, and this saves most of the CSS. |
| API client | **openapi-typescript + openapi-fetch** — *typed client instead of a hand-written wrapper* | Paths, bodies and responses are typed from the server's OpenAPI schema; a backend change that breaks the frontend fails `npm run typecheck`. |
| Frontend tests | **Vitest + Testing Library**, and **Playwright** for end-to-end — *Playwright is new* | The roles walk-through (setup -> users -> tester restrictions -> template run) is now worth automating instead of only checking by hand. |
| Serving | **nginx** container for the built frontend, proxying `/v1` (unchanged) | Same origin for cookies, upload size limit, streaming of assets. |
| Asset storage | Local volume (unchanged) | Behind `AssetStore`; S3 or MinIO is a later swap. |

Versions: latest stable of each at scaffold time, pinned by `uv.lock` and `package-lock.json`.

## As built (2026-10-31): differences from the text below

The service is implemented (backend in `studio/`, frontend in `web/`). Where the build differs from the sections below, this list wins:
- **One migration.** All tables landed together, so Alembic has a single revision `0001_initial` instead of `0001_jobs`/`0002_auth`/`0003_templates`. New changes get new revisions.
- **Template API split.** `/v1/templates` (any signed-in user) is the public view: active templates, no prompt, plus `POST /v1/templates/{ref}/generations`. Creators manage templates under `/v1/manage/templates` (list, create, get with history, `PUT` with `base_version`, versions, restore, status), always in full. Uploads stay at `/v1/uploads`. This keeps each endpoint's response type fixed for the typed frontend client.
- **Output files are per attempt**: `assets/<job_id>/<attempt>-<idx>.<ext>`, so a worker whose job was taken over deletes only its own files.
- **Gemini** (checked against google-genai 2.34): `client.aio.interactions.create(model, input=[{"type":"image","data":<b64>,"mime_type":...}, ..., {"type":"text","text":prompt}], response_format=...)`. The image response format lists only `image/jpeg` as an output type, so no mime type is requested and the output's own `mime_type` is used. Video **does** take a `duration` (string); it is sent as `"<n>s"`, a format still to confirm with a real key.
- **OpenAI** (openai 3.42): `images.edit(image=[(name, bytes, mime), ...], ...)` for input images; `gpt-image-2.5-flare` / `-sunburst` are in the SDK's model list.
- **fal** (fal-client 1.0): inputs uploaded with `AsyncClient.upload(bytes, content_type)`. Image-input endpoints `fal-ai/flux-pro/kontext` (`image_url`) and `fal-ai/nano-banana/edit` (`image_urls`) are not verified yet.
- **No real-provider calls were made** (no keys on the build machine). `uv run pytest -m smoke tests/smoke` runs them once keys are set.
- **Fake provider video** comes back as an animated GIF (`image/gif`), so no ffmpeg is needed.
- **Auth and template services** talk to the database directly (no separate repository Protocols); the job repository and queue keep theirs.
- **Apps are workspaces** (2026-10-31, replaces the global template library and the global creator/tester roles). Migration `0004_app_workspaces` converts existing data.
  - Global roles: `admin` (admin dashboard `/v1/admin/*`: users, apps, members, keys; acts as admin in every app) and `user`.
  - Users reach apps through `app_members` with a per-app role: `editor` (create/edit/delete/reorder/copy/test templates, free-prompt tests, all the app's jobs, catalog preview) or `tester` (run active templates, own jobs). Non-members get 404 for the app.
  - Each template belongs to one app (`templates.app_id`, slug unique per app, `position` for display order); copying to another app makes a new draft there. Template status is `draft | active`; delete is soft (`deleted_at`): gone from the app and its clients, old jobs keep the name; the slug can be reused.
  - All jobs belong to an app. Console jobs have `created_by`; client (app-key) jobs don't. App limits and usage count client jobs only.
  - Deleting an app is soft: keys stop working, templates and members go, the slug is freed, old jobs keep the name.
  - User-facing API: `/v1/apps` (my apps with role) and `/v1/apps/{app_id}/...` (dashboard); `GET /v1/generations/{id}` for one job. The client API `/v1/app/*` is unchanged.
- **Apps** (added after the first build): creators manage client apps under `/v1/manage/apps` (name, slug, status, optional `daily_job_limit` / `device_hourly_limit`, ordered enabled templates, app keys `cak_...` shown once). Apps call `/v1/app/*` with `X-App-Key` and an optional per-install `X-Device-Id`: list their active enabled templates, run one (multipart, same as users but no `version`/`webhook_url`), poll the job and download files. App jobs have `app_id`/`device_id` and no `created_by`; they're visible to the app (and device) that made them and to creators. Contract for the Android team: [APPS_API.md](APPS_API.md). Templates gained an optional `cover_upload` picture.
- **Deleting users**: `DELETE /v1/users/{id}` (admin) sets `deleted_at`, ends sessions, revokes tokens, clears the password and renames the email to `deleted+<id>@users.invalid` so it can be reused. The row stays so jobs and template versions keep the author's name. No self-delete; the last admin can't be deleted.
- **Migrations** are now `0001_initial`, `0002_apps`, `0003_user_deleted_at`, `0004_app_workspaces`.
- **Host ports**: API on `127.0.0.1:8010` (8000 is taken on the dev box), web on `127.0.0.1:8080`, Postgres on `127.0.0.1:5432`.

## Verified provider facts (official docs, 2026-10-31)

Many model IDs seen in tutorials are dead. Use these:

| Provider | Media | Default model / endpoint | Call | Output |
|---|---|---|---|---|
| Google (`google-genai`) | image | `gemini-nano-banana-2.1` (also live: `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`) | `client.interactions.create(model, input=prompt, response_format={"type":"image","mime_type":"image/png","aspect_ratio":"16:9","image_size":"1K"})` | `interaction.output_image.data` (base64) |
| Google (`google-genai`) | video | `gemini-omni-1.1-flash` | `client.interactions.create(model, input=prompt, response_format={"type":"video","aspect_ratio":"16:9","resolution":"720p"})`, synchronous call, no operation polling | `interaction.output_video.data` (base64 mp4) |
| OpenAI (`openai`) | image | `gpt-image-2.5-flare` (alt: `gpt-image-2.5-sunburst`) | `AsyncOpenAI().images.generate(model, prompt, size="WxH", n, quality, output_format="png")`; size any `WxH` divisible by 16, ratio 1:3..3:1, max 3840x2160 | `result.data[i].b64_json` |
| fal.ai (`fal-client`) | image | `fal-ai/flux/dev` | `fal_client.AsyncClient(key).subscribe(endpoint, arguments={"prompt","image_size","num_images","seed","output_format"})` | `result["images"][i]["url"]` + width/height |
| fal.ai (`fal-client`) | video | `fal-ai/kling-video/v3/pro/text-to-video` | same, `arguments={"prompt","duration":"5","aspect_ratio":"16:9","negative_prompt"}` | `result["video"]["url"]` |

Dead IDs to avoid: `imagen-4.0-*` (shut down 2026-08-17), `veo-3.1-*-preview` (shut down 2026-10-22), `gpt-image-1` (shut down 2026-10-23).

Mapping notes:
- Google Interactions API has no `negative_prompt`, `seed`, or `n` params. Fold negative prompt into the prompt text; for `n > 1` issue `n` concurrent calls (`asyncio.gather`). Image aspect ratios: 1:1, 3:2, 2:3, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9. Video aspect: 16:9, 9:16 only. Use `client.aio.interactions.create` if the SDK exposes it, else wrap the sync call in `asyncio.to_thread`. Video responses can be large base64 payloads; decode and write straight to the temp dir.
- OpenAI: no aspect-ratio param; table maps `aspect_ratio` to `size` (1:1 -> 1024x1024, 16:9 -> 1536x864, 9:16 -> 864x1536, 3:2 -> 1536x1024, 2:3 -> 1024x1536, 4:3 -> 1408x1056, 3:4 -> 1056x1408). Always base64, n up to 10.
- fal: outputs are URLs, so the provider downloads them with the shared `httpx.AsyncClient` (images to bytes, video streamed to a temp file). Flux `image_size` enum: `square_hd, square, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9` or `{"width","height"}`. Kling `duration` is a string enum "3".."15". Flux has no negative prompt.

Env vars: `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY`.

### Image input (for templates) — NOT yet verified

Templates need each provider to take input images with the prompt. The table above was checked only for text-to-image and text-to-video. The calls below are the expected shape. **Check each against the official docs before step 11** and update this table, as was done for the one above:

| Provider | Expected call with input images | To verify |
|---|---|---|
| Google | `interactions.create(model, input=[image part (inline base64 + mime), text part], response_format={"type":"image", ...})` | input-part format in the Interactions API; which image models take input images; max input images |
| OpenAI | `images.edit(model, image=[file, ...], prompt, size, n, output_format="png")` | that the current `gpt-image-2.5-*` models support edit with several images; max count and file size |
| fal | an image-to-image endpoint (e.g. a Flux Kontext-style edit endpoint) with `image_url` / `image_urls`; local files go up first with `fal_client.upload_file_async` (fal storage) or as a data URI | which endpoints, their exact argument names, and size limits; whether data URIs are accepted |

Argument names differ per fal endpoint, so `FalProvider` keeps a small table `IMAGE_INPUT_ENDPOINTS = {endpoint: (arg_name, max_images)}` and rejects image input for endpoints not in it.

## Development environment: Linux

Development, tests and the Docker stack run on a Linux host (Debian/Ubuntu assumed; swap `apt` for `dnf` on RHEL-family). The Mac is only an editor; nothing in the plan depends on macOS tooling.

Step 0 on the Linux box (one-time):

```bash
# uv (installs to ~/.local/bin; add to PATH)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# Docker Engine + compose plugin (Debian/Ubuntu); then log out/in for the group change
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"

# Node 22 LTS for the web/ frontend (fnm installs to ~/.local/share/fnm; add to PATH);
# later, once web/ exists: (cd web && npx playwright install --with-deps chromium) for the e2e tests
curl -fsSL https://fnm.vercel.app/install | bash
fnm install 22 && fnm default 22

# sanity
uv --version; docker --version; docker compose version; node --version; npm --version

# Postgres for local dev and tests (the same compose service the stack uses)
docker compose up -d db && docker compose exec db pg_isready -U creative
```

No Postgres install on the host is needed; `psql` runs through `docker compose exec db psql -U creative`.

Notes:
- The repo lives at `~/aarki/creative` (or wherever the user clones); `git init` there. No `ffmpeg` needed for v1.
- `uv sync` creates `.venv`; all commands are `uv run ...`. Never use system `python3`.
- Project Python is pinned via `.python-version` = `3.12` so `uv` and the Dockerfile agree.
- Assets live in a **bind mount** (`./data:/app/data`) so they can be inspected from the host. Postgres data lives in the **named volume** `pgdata` (not a bind mount: the postgres image's uid would otherwise own files in the repo).
- Host ports: API on `8000`, Postgres on `127.0.0.1:5432` (loopback only, so host-side `uv run` processes and tests can reach it), web console on `8080` in compose and `5173` under `npm run dev`. If any is taken, change `PORT` / `POSTGRES_HOST_PORT` / `WEB_PORT` in `.env`.
- `web/` pins Node via `web/.nvmrc` = `22` (fnm reads it) and uses npm with a committed `package-lock.json`; always `npm ci`, never `npm install`, in Docker.
- File ownership: the container runs as non-root uid `10001`; compose passes `user: "${UID:-10001}:${GID:-10001}"` so files under `./data` are owned by the developer on the host. Document `export UID GID` (or an `.env` entry) in the README.

## Architecture

Two processes from one image, plus Postgres:

- **`db`** container: `postgres:17` with the named volume `pgdata`. Holds jobs, assets metadata, templates and their versions, input-image metadata, worker heartbeats and schema migrations.
- **`api`** container: `studio serve` (uvicorn, `WORKER_ENABLED=false`). Handles login, sessions, users and API tokens; checks each request's role; validates requests, manages templates (creators), accepts image uploads, turns a template call into an ordinary job, inserts `queued` jobs, serves job status and asset files. Stateless apart from Postgres and the assets volume.
- **`worker`** container: `studio worker`. Claims queued jobs from Postgres, calls providers, writes assets to the volume, delivers webhooks. Scale with `--scale worker=N`; `FOR UPDATE SKIP LOCKED` lets workers claim concurrently without blocking each other.
- **Shared state**: job records in Postgres via SQLAlchemy 2.0 async on the asyncpg driver (one `AsyncEngine` per process, `DATABASE_URL`; each worker also holds one raw asyncpg connection for `LISTEN`); assets in `./data` bind-mounted at `/app/data` in `api` and `worker`. The `status` column is the queue. `JobRepository`/`JobQueue`/`AssetStore` stay Protocols, so S3 (and a managed Postgres) can replace the local pieces without touching API or worker code.
- `WORKER_ENABLED=true` on the API process still works for a single-process dev setup (`studio serve` then also starts the worker loop in lifespan); it still needs the `db` container.
- Transactions are short: never hold a connection or transaction across a provider await. A worker borrows a pool connection only for claim, heartbeat and finalize.
- Providers own their long-running behaviour so the worker just awaits with a timeout. `GeneratedAsset.content: bytes | Path` so large videos never sit in memory.
- Templates don't reach the worker. At submit the API resolves the template version, renders the prompt, stores the user's images, and writes a normal job whose `request` holds the rendered prompt and settings, plus `job_inputs` rows for the images. The worker runs it like any other job, so retries and stale requeue work the same, and later template edits can't change a queued job.

### Layout

```
studio/
├── pyproject.toml          deps: fastapi, uvicorn[standard], pydantic>=2.7, pydantic-settings, httpx, sqlalchemy[asyncio]>=2.0, asyncpg, alembic, python-multipart, pillow, argon2-cffi, google-genai, openai, fal-client; dev: pytest, pytest-asyncio, ruff, respx; script studio="studio.cli:main"
├── .env.example  .gitignore  README.md  Dockerfile  docker-compose.yaml  alembic.ini
├── migrations/             Alembic env.py (advisory lock around upgrade) + versions/0001_jobs.py, 0002_auth.py, 0003_templates.py
├── studio/
│   ├── config.py           Settings(BaseSettings), env_file=".env", no prefix
│   ├── logging.py          configure_logging; PromptRedactingFilter (drop prompts unless LOG_PROMPTS)
│   ├── main.py             create_app(settings) -> FastAPI; lifespan: build AppState, requeue_stale, start/stop worker
│   ├── deps.py             AppState (settings, db, repo, queue, store, registry, templates, auth, worker, webhooks, http); get_state, get_service, current_user, require_role(tester|creator|admin)
│   ├── cli.py              `serve` (API), `worker` (generation worker), `providers`, `generate` (submit + poll + download; the smoke tool; `--template <id|slug> --image slot=path --var k=v`), `health` (worker liveness check for the compose healthcheck),
│                           `users create-admin | reset-password`, `tokens create` (bootstrap and recovery from a shell), `db upgrade` (Alembic upgrade head)
│   ├── db/
│   │   ├── engine.py       create_engine(settings), async session factory, `listen_connection()` for LISTEN/NOTIFY
│   │   └── tables.py       all SQLAlchemy table models (jobs, assets, job_inputs, workers, users, sessions, api_tokens, login_attempts, templates, template_versions, template_events, uploads)
│   ├── auth/
│   │   ├── models.py       Role (tester < creator < admin), User, Session, ApiToken
│   │   ├── passwords.py    argon2id hash/verify (argon2-cffi), password rules, dummy verify for unknown emails
│   │   ├── repository.py   UserRepository / SessionRepository / TokenRepository Protocols + SQLAlchemy implementations
│   │   └── service.py      AuthService: setup (first admin), login + throttle, sessions, tokens, user management, last-admin guard
│   ├── api/
│   │   ├── schemas.py      GenerationCreate, JobResponse, AssetResponse, ErrorResponse, ProviderInfo, HealthResponse, TemplateCreate/Update, TemplateFull, TemplatePublic, TemplateVersionOut, UploadOut, MeResponse, LoginIn, SetupIn, UserOut, UserCreate/Update, TokenOut
│   │   ├── auth.py         /v1/auth: setup, login, logout, me, password, tokens
│   │   ├── users.py        /v1/users (admin)
│   │   ├── generations.py  POST /v1/generations (creator), GET /v1/generations/{id}, GET /v1/generations
│   │   ├── templates.py    /v1/templates: list/get (role-shaped), create/update/versions/restore/status (creator), POST {ref}/generations (multipart)
│   │   ├── uploads.py      POST /v1/uploads (creator; reference images)
│   │   ├── assets.py       GET /v1/assets/{asset_id}, GET /v1/inputs/{input_id}, GET /v1/uploads/{upload_id}
│   │   ├── meta.py         GET /healthz, GET /v1/providers
│   │   └── errors.py       NotFoundError, UnsupportedRequestError, NoProviderAvailableError + install_error_handlers
│   ├── providers/
│   │   ├── base.py         MediaType, GenerationRequest, GeneratedAsset, ProviderCapabilities, Provider(ABC), ProviderError hierarchy
│   │   ├── registry.py     ProviderRegistry.from_settings / get / list / resolve(media_type, provider, model)
│   │   ├── gemini.py       GeminiProvider (Interactions API, image + video)
│   │   ├── openai_images.py OpenAIImagesProvider (image only)
│   │   ├── fal.py          FalProvider (submit/subscribe, URL download)
│   │   └── fake.py         FakeProvider (deterministic bytes; prompt keywords FAIL_TRANSIENT, FAIL_POLICY, SLEEP:<s>; accepts input images and tints/flips them so tests can tell output from input)
│   ├── templates/
│   │   ├── models.py       Template, TemplateVersion, InputSlot, Variable dataclasses
│   │   ├── render.py       render_prompt(prompt, variables, values): `{{name}}` substitution, no expressions
│   │   ├── repository.py   TemplateRepository Protocol + SQLAlchemy implementation
│   │   └── service.py      TemplateService: create / update (new version) / set_status / restore / validate_against_registry / build_job (template call -> job)
│   ├── media/
│   │   └── images.py       read_upload (size-capped streaming read), normalize_image (Pillow verify, EXIF orientation, strip metadata, downscale)
│   ├── jobs/
│   │   ├── models.py       JobStatus, Job, Asset dataclasses, row<->dataclass helpers
│   │   ├── repository.py   JobRepository Protocol, JobQueue Protocol
│   │   ├── pg_repository.py PgJobRepository + PgJobQueue (claim / finalize / stale sweep as explicit SQL)
│   │   ├── service.py      GenerationService.create / get / list / to_response
│   │   ├── worker.py       Worker.start / stop / run_once; claim -> execute -> finalize
│   │   └── webhooks.py     WebhookSender.send with retries + HMAC signature
│   └── storage/
│       ├── base.py         AssetStore Protocol (put, put_input, put_upload, local_path, public_url, delete_job, temp_dir)
│       └── local.py        LocalAssetStore: outputs <root>/assets/<job_id>/<idx>.<ext>, user inputs <root>/inputs/<job_id>/<slot>.<ext>,
│                           creator uploads <root>/uploads/<upload_id>.<ext>; temp <root>/tmp, atomic .part + os.replace
├── tests/  conftest.py, test_migrations.py, test_api_pipeline.py, test_registry.py, test_pg_repository.py, test_worker.py,
│           test_local_store.py, test_webhooks.py, test_providers_mapping.py, test_templates.py,
│           test_template_api.py, test_images.py, test_auth.py, test_users.py, test_permissions.py,
│           smoke/test_real_providers.py
└── web/                    React + Vite + TypeScript console (see "Frontend")
    ├── package.json  package-lock.json  .nvmrc  tsconfig.json  vite.config.ts  postcss.config.cjs  index.html  playwright.config.ts
    ├── e2e/                roles.spec.ts, templates.spec.ts (Playwright, against the compose stack with the fake provider)
    ├── Dockerfile  nginx.conf
    └── src/
        ├── main.tsx  App.tsx (MantineProvider, QueryClientProvider, router)  routes.tsx (paths + role guards)
        ├── api/
        │   ├── schema.d.ts     generated from the API's /openapi.json (openapi-typescript); committed
        │   ├── client.ts       openapi-fetch client: same-origin cookies, uniform error body -> ApiError, 401 -> login
        │   └── queries.ts      TanStack Query hooks: useMe, useTemplates, useJob (polls until terminal), useJobs, mutations
        ├── auth/
        │   ├── RequireRole.tsx route guard from useMe(); can(role) helper
        │   ├── SetupPage.tsx   first run: setup token + admin email, name, password
        │   ├── LoginPage.tsx   email + password
        │   ├── ChangePassword.tsx forced after a temporary password; also from Account
        │   └── AccountPage.tsx name, password, personal API tokens (create: shown once; revoke)
        └── components/
            ├── TopBar.tsx        user name + role badge, Account, Log out; /healthz summary (db, workers, queued/running)
            ├── Tabs.tsx          tabs allowed for the role: Use template (all) | Generate, Templates (creator+) | Users (admin)
            ├── UsersPage.tsx     admin: list, create (temporary password shown once), change role, deactivate, reset password, revoke tokens
            ├── GenerateForm.tsx  form driven by /v1/providers capabilities
            ├── UseTemplate.tsx   pick an active template, image pickers per slot with preview, variable fields, submit
            ├── TemplateList.tsx  creator: all templates, status, current version, provider/model, last edited by
            ├── TemplateEditor.tsx creator: edit fields, prompt with {{variable}} detection, slots, reference images, save = new version
            ├── TemplateHistory.tsx creator: versions with author and diff of changed fields, restore
            ├── TemplateTestRun.tsx creator: upload an image and run this exact version (draft too), result inline
            ├── JobList.tsx       recent jobs with status badges, status and template filters
            ├── JobDetail.tsx     request, template + version, attempts, timings, error, webhook state, raw JSON toggle; inputs beside outputs
            └── AssetView.tsx     plain <img>/<video src> (the session cookie authorises it; Range works), download link
```

### Provider abstraction (`providers/base.py`)

- `GenerationRequest(job_id, prompt, media_type, model, aspect_ratio="1:1", n=1, duration_seconds=None, negative_prompt=None, seed=None, input_images=[])`.
- `InputImage(path, mime_type, width, height, role: "input" | "reference")`. `input` = the caller's image(s); `reference` = images a creator attached to the template (e.g. a style sample). Providers send inputs first, then references, then the prompt text.
- `GeneratedAsset(content: bytes | Path, mime_type, width, height, duration_seconds, metadata)`.
- `ProviderCapabilities(name, image, video, default_image_model, default_video_model, known_*_models, max_images, image_aspect_ratios, video_aspect_ratios, video_durations, supports_negative_prompt, supports_seed, image_input: bool, image_input_models, max_input_images)`. `image_input_models` lists the models (fal: endpoints) known to take input images; a template may name another model, but then saving it shows a warning, and a failure surfaces as `invalid_request` on the job.
- When `input_images` is non-empty and the request has no `aspect_ratio`, providers follow the first input's shape (nearest supported ratio), so a portrait photo stays portrait.
- `Provider(ABC)`: `validate(req)` (default impl from capabilities, raises `UnsupportedRequestError`), `generate_image(req) -> list[GeneratedAsset]`, `generate_video(req) -> GeneratedAsset`, `aclose()`.
- Errors: `ProviderError(code, message, retryable)` with subclasses `ProviderUnavailableError` (429/5xx/network, retryable), `ProviderInvalidRequestError`, `ProviderContentPolicyError`, `ProviderOperationTimeout` (all non-retryable). Each provider has `_translate(exc)` and a single `_build_arguments(req)` so SDK drift is a one-file fix.
- Model strings are not validated against a hard-coded list; a bad model fails the job with `invalid_request`. Media-type support, `n`, aspect ratio, duration are validated at submit (422).

### Registry resolution

1. `provider` given: unknown -> 422 listing configured providers; configured but lacks the media type -> 422.
2. `provider` None: `DEFAULT_IMAGE_PROVIDER`/`DEFAULT_VIDEO_PROVIDER`, else first configured capable provider in order gemini, openai, fal, fake; none -> 503 `no_provider_available`.
3. `model = model or default_<media>_model`.

### Data model and schema

`jobs(id uuid PK, status text CHECK (status IN ('queued','running','succeeded','failed')), media_type text, provider text, model text, request jsonb, webhook_url text, webhook_status text, webhook_attempts int, error_code text, error_message text, attempt int, max_attempts int, run_after timestamptz, worker_id text, heartbeat_at timestamptz, created_at, updated_at, started_at, finished_at timestamptz)`.
Indexes: partial `(created_at) WHERE status='queued'` for the claim; partial `(heartbeat_at) WHERE status='running'` for the stale sweep; `(created_at DESC)` for listing.
`assets(id uuid PK, job_id uuid REFERENCES jobs ON DELETE CASCADE, idx int, path text, mime_type text, size_bytes bigint, width int, height int, duration_seconds real, metadata jsonb, created_at timestamptz, UNIQUE (job_id, idx))`.
Account tables (Alembic revision `0002_auth`):
- `users(id uuid PK, email text UNIQUE (stored lower-cased), name text, role text CHECK (role IN ('admin','creator','tester')), password_hash text, must_change_password bool, is_active bool, created_by uuid NULL REFERENCES users, created_at, updated_at, last_login_at)`. Users are deactivated, never deleted, because jobs and template versions point at them.
- `sessions(id text PK = sha256 of the cookie token, user_id uuid REFERENCES users ON DELETE CASCADE, created_at, last_seen_at, expires_at, ip text, user_agent text)`; index `(user_id)`.
- `api_tokens(id uuid PK, user_id uuid REFERENCES users, name text, token_hash text UNIQUE (sha256), prefix text (first 8 chars, for display), created_at, last_used_at, revoked_at)`.
- `login_attempts(email text, ip text, at timestamptz, ok bool)`; index `(email, at)`; rows older than a day are deleted by the worker's heartbeat tick.
- `jobs` gains `created_by uuid REFERENCES users`; index `(created_by, created_at DESC)` for a tester's own list.

Template tables (Alembic revision `0003_templates`):
- `templates(id uuid PK, slug text UNIQUE, title text, description text, status text CHECK (status IN ('draft','active','archived')), current_version int, created_by uuid REFERENCES users, created_at, updated_at)`.
- `template_versions(template_id uuid REFERENCES templates ON DELETE CASCADE, version int, media_type text, provider text, model text, allowed_models text[], prompt text, negative_prompt text, params jsonb, inputs jsonb, variables jsonb, reference_uploads uuid[], note text, created_by uuid REFERENCES users, created_at, PRIMARY KEY (template_id, version))`. Rows are never updated. Status changes are recorded in `template_events(template_id, user_id, action, from_status, to_status, at)`.
  - `params`: defaults the caller can't change: `aspect_ratio` (or `"auto"` = follow the input image), `n`, `seed`.
  - `inputs`: slots, e.g. `[{"name": "photo", "label": "Your photo", "required": true}]` (1..`max_input_images` slots).
  - `variables`: e.g. `[{"name": "mood", "label": "Mood", "default": "sunny", "max_length": 100, "choices": ["sunny", "rainy"] | null}]`.
- `uploads(id uuid PK, path, mime_type, size_bytes, width, height, sha256, created_by uuid REFERENCES users, created_at)`: creator-uploaded reference images. Immutable, so old versions keep working.
- `job_inputs(id uuid PK, job_id uuid REFERENCES jobs ON DELETE CASCADE, slot text, role text, path, mime_type, size_bytes, width, height, sha256, created_at, UNIQUE (job_id, slot))`. Reference images are copied into `job_inputs` (role `reference`) by path, so the worker only reads `job_inputs`.
- `jobs` gains `template_id uuid NULL REFERENCES templates`, `template_version int NULL`; index `(template_id, created_at DESC)`.

`workers(id text PK, hostname text, started_at, heartbeat_at timestamptz, inflight int)` so the API can report worker liveness and stale jobs can be detected by heartbeat age rather than by process restart. `jobs.heartbeat_at` is refreshed by the owning worker while a job runs.
uuid4 ids generated in Python; all timestamps `timestamptz`, set from `now()` in SQL so every process uses the database clock. `jsonb` columns use SQLAlchemy's `JSONB` type.

Migrations: Alembic, revisions `0001_jobs`, `0002_auth`, `0003_templates` (one per build step that adds tables). `studio db upgrade` runs `alembic upgrade head`; `migrations/env.py` takes `pg_advisory_xact_lock(<const>)` first, so two upgrades started together are safe (one waits, then finds nothing to do). In compose a one-shot `migrate` service runs it before `api` and `worker` start; in dev, run `uv run studio db upgrade` after pulling. New revisions: `uv run alembic revision --autogenerate -m "..."`, then read and fix the generated file (autogenerate misses partial indexes, CHECK constraints and data moves). At startup `api` and `worker` check that the database is at `head` and refuse to start otherwise, with a message to run the upgrade.

Claim SQL (one statement, autocommit):
```sql
UPDATE jobs SET status='running', worker_id=$1, attempt=attempt+1,
       started_at=now(), heartbeat_at=now(), updated_at=now()
WHERE id = (SELECT id FROM jobs WHERE status='queued' AND run_after <= now()
            ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
RETURNING *;
```
Setting `heartbeat_at` on claim keeps a freshly claimed retry from looking stale to another worker's sweep.

Finalize statements (`mark_succeeded`, `mark_failed`, `release`, heartbeat bump) are fenced: `... WHERE id=$1 AND worker_id=$2 AND attempt=$3 AND status='running'`. If no row is updated, the job was requeued and taken over; the worker drops its result, deletes the files it wrote, and does not send a webhook. `mark_succeeded` inserts the assets and updates the job in one transaction.

### Worker

- Loop: while not stopping, if inflight < `WORKER_CONCURRENCY` claim a job and spawn `_execute`; when nothing was claimed, wait up to `WORKER_POLL_INTERVAL_S` or until woken. Wake-up: the API runs `NOTIFY studio_jobs` in the insert transaction, and each worker holds one dedicated `LISTEN studio_jobs` connection (outside the pool). Polling stays as the fallback, so a dropped LISTEN connection only adds latency.
- `_execute`: build request (with `input_images` from `job_inputs`), `asyncio.wait_for(provider.generate_*(req), JOB_TIMEOUT_IMAGE_S | JOB_TIMEOUT_VIDEO_S)`, `store.put` each asset, `add_assets`, `mark_succeeded`. On retryable `ProviderError` with attempts left: `queue.release(run_after = now + RETRY_BACKOFF_BASE_S * 2**(attempt-1))`. Else `mark_failed(code, message)` and `store.delete_job`. Unexpected exceptions -> `internal_error`, no retry. Webhook sent after the terminal status is committed.
- `stop()`: cancel loop, wait `SHUTDOWN_GRACE_S` for inflight, release the rest back to queued, delete its `workers` row. Handles SIGTERM from `docker stop`.
- Heartbeat task every `WORKER_HEARTBEAT_S` (15 s): upserts its `workers` row and bumps `heartbeat_at` on its running jobs.
- `requeue_stale()` runs at worker startup and every heartbeat tick: `running` jobs whose `heartbeat_at < now() - STALE_JOB_AFTER_S` (120 s) go back to `queued` (`worker_id=NULL`), or to `failed/worker_lost` if `attempt >= max_attempts`. One `UPDATE ... RETURNING id`, so concurrent sweeps by several workers don't double-process a row. It never touches a job with a fresh heartbeat. Old `workers` rows (heartbeat older than an hour) are deleted in the same tick.
- `WebhookSender`: POST JobResponse JSON, headers `X-Studio-Event`, `X-Studio-Job-Id`, `X-Studio-Signature: sha256=<hmac>` when `WEBHOOK_SECRET` set; 3 attempts with 1/4/16 s backoff, 10 s timeout; 4xx (except 408/429) gives up. Reject private/loopback hosts unless `ALLOW_PRIVATE_WEBHOOKS`.

### API

- Auth: every `/v1` route except `/v1/auth/setup` and `/v1/auth/login` needs a signed-in user (session cookie or API token) and declares its minimum role; see "Accounts, login and roles". No anonymous access. `/healthz` stays open.
- `POST /v1/generations` (creator) -> 202 `JobResponse`. Free-prompt generation, so testers can't use it. Body: `prompt` (1..4000), `media_type`, `provider?`, `model?`, `aspect_ratio="1:1"`, `n=1` (1..8, must be 1 for video), `duration_seconds?` (video only, 1..60), `negative_prompt?`, `seed?`, `webhook_url?` (HttpUrl).
- `JobResponse`: `id, status, media_type, provider, model, request{...}, template{id, slug, title, version}|null, inputs[{id, slot, role, url "/v1/inputs/{id}", mime_type, width, height}], assets[{id, url "/v1/assets/{id}", mime_type, size_bytes, width, height, duration_seconds}], error{code,message}|null, attempt, created_at, started_at, finished_at, webhook{url,status,attempts}|null, created_by{id, name}`. For template jobs seen by a tester, `request.prompt` and `request.negative_prompt` are removed and reference inputs are left out.
- `GET /v1/generations/{id}` -> 200 | 404. `GET /v1/generations?status=&template=&created_by=&limit=50` -> `{items}`. Testers get only their own jobs (another user's job is a 404, not a 403, so ids don't leak); `created_by` is ignored for them.
- `GET /v1/assets/{id}`, `GET /v1/inputs/{id}` -> `FileResponse` (Range support for video) or 307 to `public_url` when a store provides one; same ownership rule as the job. `GET /v1/uploads/{id}` is creator+.

Templates (`{ref}` is the template id or its slug). Reads are shaped by role:
- `GET /v1/templates` -> testers: active templates as `TemplatePublic` (`id, slug, title, description, media_type, version, inputs, variables, allowed_models, default model, has_reference_images`; no prompt). Creators: all templates as `TemplateFull` (current version in full, `status`, last edited by), filter `?status=`.
- `GET /v1/templates/{ref}` -> one template, same shaping; for testers 404 if draft or archived. Creators also get the version list.
- `POST /v1/templates/{ref}/generations` (tester+) -> 202 `JobResponse`. `multipart/form-data`:
  - one file field per input slot, named after the slot (e.g. `photo=@me.jpg`); required slots must be present, unknown field names are a 422;
  - `variables` (optional JSON object string), `model` (optional, must be in `allowed_models`), `webhook_url` (optional);
  - creator+ only: `version` (run a specific version, also allowed on draft templates; used by the editor's test run). Testers always run the current version of an active template.
  - Steps: resolve the version -> validate files (see Image uploads) -> render the prompt -> check the provider is configured and the model supports image input -> store inputs -> insert the job and `job_inputs` in one transaction with `NOTIFY`. A file that fails validation is a 422 naming the slot. If a later step fails, files already written are deleted.
  - Example: `curl -H "Authorization: Bearer $STUDIO_TOKEN" -F photo=@me.jpg http://localhost:8000/v1/templates/ghibli-gemini/generations`.

Templates, writes (creator+), under `/v1/templates`:
- `POST /v1/templates` (JSON `TemplateCreate`: `slug, title, description, media_type, provider, model, allowed_models?, prompt, negative_prompt?, params, inputs, variables, reference_uploads?, note?`) -> 201 `TemplateFull` with version 1, status `draft`.
- `PUT /v1/templates/{id}` (same body without `slug`, plus `base_version`) -> writes version `current+1` and points `current_version` at it. If `base_version` isn't the current version (another creator saved in between) -> 409 `version_conflict` with the current version, so two creators can't silently overwrite each other. Title/description changes still make a new version, to keep it simple.
- `GET /v1/templates/{id}/versions/{v}`; `POST /v1/templates/{id}/versions/{v}/restore` -> copies version `v` as a new version.
- `POST /v1/templates/{id}/status` `{status: draft|active|archived}`. Archived templates are hidden from testers and can't be called; jobs already queued still run.
- `POST /v1/uploads` (multipart `file`) -> `UploadOut{id, url, mime_type, width, height}`, for reference images.
- Save-time checks (422 with field details): slug format `[a-z0-9-]{3,64}`; every `{{name}}` in prompt/negative prompt is declared in `variables` and every declared variable is used; provider configured and `image_input` true when `inputs` is non-empty; model and each of `allowed_models` in `image_input_models` (otherwise a warning in the response, not an error); `n` <= `max_images`; aspect ratio supported or `auto`; input slots + reference images <= `max_input_images`. Saving also works when the provider isn't configured on this host, with a warning, so templates can be prepared before keys are added; calling such a template returns 503 `provider_unavailable`.

Other:
- `GET /v1/providers` (any signed-in user), `GET /healthz` -> `{status, db: ok (a `SELECT 1` on the pool; HTTP 503 if it fails), workers: [{id, heartbeat_at, inflight}], jobs: {queued, running}}`; `status` is `degraded` when no worker heartbeat is fresher than `STALE_JOB_AFTER_S` (still HTTP 200 so the API container stays up; the worker has its own healthcheck).
- Uniform error body `{"error": {"code", "message", "details"?}}`.
- `ProviderInfo` exposes the full `ProviderCapabilities` (media types, default and known models, `max_images`, aspect ratios per media type, video durations, `supports_negative_prompt`, `supports_seed`) so the frontend can build its form from it.

### Accounts, login and roles

What each role may do (each role includes the rows of the roles left of it):

| | tester | creator | admin |
|---|---|---|---|
| Sign in, change own password, own API tokens | yes | yes | yes |
| List and run **active** templates (current version) | yes | yes | yes |
| See own jobs, their inputs and outputs | yes | yes | yes |
| See everyone's jobs | – | yes | yes |
| See template prompts and full settings | – | yes | yes |
| Free-prompt generation (`POST /v1/generations`) | – | yes | yes |
| Create and edit templates, restore versions, change status, upload reference images, test-run drafts and old versions | – | yes | yes |
| Create users, change roles, deactivate, reset passwords, revoke anyone's tokens | – | – | yes |

Each route declares its minimum role with `require_role(...)`; `test_permissions.py` walks every route in the app for each role and fails if a route has no declared role, so a new endpoint can't be left open by accident.

**First user = admin (setup).**
- While the `users` table is empty, `GET /v1/auth/setup` returns `{needed: true}` and the frontend shows the setup page; afterwards `{needed: false}` and `POST /v1/auth/setup` is a 409.
- `POST /v1/auth/setup {setup_token, email, name, password}` creates the admin and signs them in. It runs under a Postgres advisory lock and re-checks that no user exists, so two simultaneous setups can't create two admins.
- The setup token stops whoever reaches the page first from taking the admin account. It's `SETUP_TOKEN` from `.env` if set, otherwise generated at `api` startup while no users exist and printed in the api log (`docker compose logs api`): `First-run setup: open /setup and use token XXXX`. It's useless once the admin exists.
- From a shell, `studio users create-admin --email ... --name ...` (prompts for the password) does the same without the web page, e.g. `docker compose exec api studio users create-admin ...`. `studio users reset-password --email ...` recovers a locked-out admin.

**Users (admin), `/v1/users`.**
- `GET /v1/users` -> all users with role, active flag, last login, token count.
- `POST /v1/users {email, name, role: creator|tester}` -> 201 with a generated **temporary password, shown once**. The user must change it at first sign-in (`must_change_password`); until they do, every route except `/v1/auth/*` returns 403 `password_change_required`.
- `PATCH /v1/users/{id} {name?, role?, is_active?}`. Deactivating a user, or changing their role, ends their sessions; deactivating also revokes their API tokens. Role changes take effect on the next request.
- `POST /v1/users/{id}/reset-password` -> a new temporary password, shown once; ends their sessions.
- Guards: the web UI creates only creators and testers; the admin can't deactivate or demote themself, and the last active admin can't be removed. More admins: `studio users create-admin` or promote a user to `admin` with `PATCH` (allowed, but the UI asks for confirmation).

**Sign-in and sessions, `/v1/auth`.**
- `POST /login {email, password}` -> sets cookie `studio_session` (random 32 bytes; the DB stores only its sha256), `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` when `COOKIE_SECURE=true` (set it behind HTTPS). Returns `MeResponse {id, email, name, role, must_change_password}`.
- Wrong email and wrong password give the same 401 `invalid_credentials`, and an unknown email still runs a dummy argon2 verify, so response time doesn't reveal which emails exist.
- Throttle: after `LOGIN_MAX_FAILURES` (10) failures for one email, or 30 from one IP, within `LOGIN_WINDOW_MIN` (15 min) -> 429 until the window passes.
- Sessions end after `SESSION_IDLE_HOURS` (12) without use or `SESSION_MAX_AGE_HOURS` (168) in total. `last_seen_at` is written at most once a minute.
- `POST /logout` deletes the session. `GET /me`. `POST /password {current_password, new_password}` -> ends the user's other sessions.
- Passwords: argon2id; length `PASSWORD_MIN_LENGTH` (12) to 256; not equal to the email.
- CSRF: for cookie-authenticated `POST/PUT/PATCH/DELETE`, the `Origin` header (or `Referer`) must match the request's host; otherwise 403. With `SameSite=Lax` this covers forms and multipart posts from other sites. Requests with a Bearer token are exempt. nginx and the Vite proxy must keep the browser's `Host` (`proxy_set_header Host $http_host`; Vite `changeOrigin: false`).

**API tokens (for scripts and integrations), `/v1/auth/tokens`.**
- `GET` own tokens; `POST {name}` -> `crt_<random>`, **shown once** (DB stores sha256 + an 8-char prefix); `DELETE /{id}` revokes. Admins can list and revoke anyone's tokens from `/v1/users/{id}/tokens`.
- `Authorization: Bearer crt_...` acts as the token's owner with the owner's **current** role; a deactivated owner's tokens stop working. `last_used_at` is written at most once a minute.
- An external service that should only run templates gets its own tester account and a token from it.

### Templates: prompt rendering and image uploads

- Prompt rendering (`templates/render.py`): replace `{{name}}` (letters, digits, `_`) with the caller's value or the variable's default. Values: string, max `max_length` (default 100), newlines collapsed to spaces, `{{`/`}}` removed so a value can't inject another placeholder, must be in `choices` when set. Unknown variable names are a 422. No template engine (no Jinja), so there's no logic in prompts.
- Uploads (`media/images.py`):
  - Read in chunks and stop at `INPUT_IMAGE_MAX_BYTES` (10 MB) with 413, so a huge upload isn't buffered whole.
  - Accept only PNG, JPEG and WebP, by content (Pillow), not by filename or `Content-Type`. `Image.verify()`, then re-open; reject over `INPUT_IMAGE_MAX_PIXELS` (40 MP) before decoding fully, to block decompression bombs.
  - Apply the EXIF orientation, then re-encode without metadata (drops GPS and camera data from user photos). Keep the format; JPEG at quality 95.
  - Downscale so the long side is at most `INPUT_IMAGE_MAX_SIDE` (2048) to cut upload size to the provider.
  - Store width, height, size and sha256 in `job_inputs` / `uploads`.
- Inputs are deleted with their job (`store.delete_job` removes `inputs/<job_id>` as well as `assets/<job_id>`). The retention follow-up below covers both.

### Example: "Ghibli Image Generation with Gemini"

A creator signs in and fills in the Templates editor, which sends:

```json
POST /v1/templates
{
  "slug": "ghibli-gemini",
  "title": "Ghibli Image Generation with Gemini",
  "description": "Turns a photo into a hand-painted anime film still.",
  "media_type": "image",
  "provider": "gemini",
  "model": "gemini-nano-banana-2.1",
  "allowed_models": ["gemini-nano-banana-2.1", "gemini-3-pro-image"],
  "prompt": "Redraw this photo as a hand-painted 1990s Japanese anime film still: soft watercolor backgrounds, warm natural light, gentle line art. Keep the people's poses, faces and the composition. Mood: {{mood}}.",
  "params": {"aspect_ratio": "auto", "n": 1},
  "inputs": [{"name": "photo", "label": "Your photo", "required": true}],
  "variables": [{"name": "mood", "label": "Mood", "default": "sunny afternoon", "max_length": 60}]
}
```
The creator test-runs the draft with a photo, then activates it (`POST /v1/templates/{id}/status {"status":"active"}`). A tester now sees it under Use template, and an integration runs `curl -H "Authorization: Bearer $STUDIO_TOKEN" -F photo=@me.jpg -F 'variables={"mood":"rainy evening"}' .../v1/templates/ghibli-gemini/generations`. Switching it to OpenAI is a `PUT` with `provider: "openai"` and its model, creating version 2; jobs made with version 1 still show version 1.

The prompt describes the style rather than naming the studio. Providers may refuse prompts that name a studio or living artist, and style imitation of a named studio is an IP question for whoever owns the product, not something the service decides.

### CORS
- CORS: off by default. `CORS_ORIGINS` (comma-separated) enables `CORSMiddleware` for the case where the console is served from another origin; the normal setups below are same-origin and don't need it.

### Frontend (`web/`)

A single-page console with sign-in, React 19 + Vite + TypeScript (see "Stack"). Dependencies: `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `@mantine/core`, `@mantine/hooks`, `@mantine/form`, `@mantine/dropzone`, `@mantine/notifications`, `openapi-fetch`; dev: `vite`, `@vitejs/plugin-react`, `typescript`, `openapi-typescript`, `postcss-preset-mantine`, `eslint` (+ `typescript-eslint`, `eslint-plugin-react-hooks`), `vitest`, `@testing-library/react`, `@playwright/test`.

Routes: `/setup`, `/login`, `/change-password`, `/account`, `/users`, `/templates`, `/templates/<id>`, `/use`, `/use/<slug>`, `/generate`, `/jobs/<id>`. Each route declares its minimum role in `routes.tsx`; `RequireRole` redirects to `/login` (signed out) or shows "your role can't do this".

Data: all server state goes through TanStack Query. `useJob(id)` uses `refetchInterval: (q) => terminal(q.state.data) ? false : 1500`; the job list polls every 2 s while anything is queued or running, else 15 s; `refetchIntervalInBackground: false` pauses polling in hidden tabs. Mutations invalidate the affected queries (saving a template refreshes its list and history). A 401 from any query clears the cache and goes to `/login`.

UI: Mantine components (`AppShell` with header and tabs, `Table`, `Modal`, `Dropzone` for image slots with previews, `@mantine/form` for the editor and user forms with server 422 details mapped onto fields, `notifications` for toasts). Light and dark follow the system.

Sign-in flow:
- On load: `GET /v1/auth/setup`; if needed, show the setup page. Otherwise `GET /v1/auth/me`; a 401 shows the login page and returns to the requested page after sign-in. `must_change_password` shows only the change-password page until it's done.
- `client.ts` sends `credentials: "same-origin"`; any 401 drops the user back to login; a 403 shows "your role can't do this". The frontend hides what the role can't do, but the server is what enforces it.
- No tokens in `localStorage`: the session lives only in the `HttpOnly` cookie, so page scripts can't read it.

Same-origin everywhere, so no CORS and no API URL config:
- Dev: `npm run dev` (port 5173); `vite.config.ts` proxies `/v1` and `/healthz` to `http://localhost:${API_PORT:-8000}`.
- Compose: the `web` container (nginx) serves the built files and proxies `/v1` and `/healthz` to `api:8000` (`proxy_buffering off` for `/v1/assets/` so video streams).

Page layout (one screen, two columns; stacks on narrow widths):
- **Top bar**: the user's name and role badge, Account (name, password, API tokens), Log out; and the `/healthz` summary polled every 5 s: status (`ok`/`degraded`), db, number of live workers, queued/running counts.
- **Tabs by role**: tester -> **Use template** only; creator -> **Use template**, **Generate**, **Templates**; admin -> those plus **Users**. Testers land on Use template, creators on Templates, the admin on Users.
- **Users** (admin): table of users (name, email, role, active, last login); "Add user" (email, name, role creator/tester) shows the temporary password once with a copy button; per row: change role, deactivate/reactivate, reset password (shows the new temporary one), view and revoke tokens. The admin's own row can't be deactivated or demoted.
- **Account** (everyone): change name and password; API tokens list (name, prefix, created, last used), "New token" shows the full token once with a copy button and an example `curl`; revoke.
- **Left: Generate form** (creator+). Provider select from `/v1/providers` (plus "default"); media type limited to what the provider supports; model select = known models + free-text "other"; aspect ratio, `n` (1..`max_images`, hidden for video), duration (only the provider's `video_durations`, hidden when it has none), negative prompt and seed shown only when supported; prompt textarea; optional webhook URL. Submit -> `POST /v1/generations`; a 422 shows `error.details` next to the fields. When the `fake` provider is selected, quick-fill buttons insert `FAIL_TRANSIENT`, `FAIL_POLICY`, `SLEEP:30` into the prompt to drive the retry, failure and stale-requeue paths.
- The job list and job detail stay visible under Use template, Generate and Templates.
- **Use template** (everyone; what an API client does, by hand): select from `GET /v1/templates`; shows title and description; one file picker per input slot with a local preview (`URL.createObjectURL` of the chosen file) and its size; a field per variable (a select when it has `choices`), prefilled with the default; a model select when `allowed_models` has more than one; Submit sends `multipart/form-data` to `POST /v1/templates/{slug}/generations` with `FormData`, then selects the new job. Client-side checks are only hints (type, 10 MB); the server decides. Shows the equivalent `curl` command (with a `$STUDIO_TOKEN` placeholder), so testers can copy it.
- **Templates** (creator+):
  - List: title, slug, status badge, version, provider/model, last edited by and when; "New template"; filter by status.
  - Editor: title, slug (fixed after create), description, media type, provider select (from `/v1/providers`, only providers with `image_input` when the template has input slots), model select (that provider's `image_input_models` + free-text "other"), `allowed_models` multi-select, prompt textarea that lists the `{{variables}}` it finds and offers to add any undeclared one, negative prompt (if supported), defaults (aspect ratio incl. `auto`, `n`, seed), input slots editor (name, label, required; add/remove), variables editor (name, label, default, max length, choices), reference images (upload via `/v1/uploads`, thumbnails, remove), a "change note". Save -> new version; the save response's warnings show above the form. A 409 `version_conflict` (someone else saved first) says who saved and offers to reload their version. Status buttons: Activate / Move to draft / Archive.
  - History: versions newest first with author, note and date; selecting one shows which fields differ from the previous version; "Restore as new version".
  - Test run: pick an image (and variables), run the version currently open in the editor, even a draft (`version` form field); the job opens in Job detail with input and output side by side.
- **Left below: Job list.** `GET /v1/generations?limit=50`, status and template filters, plus "mine / everyone" for creator+ (testers only ever see their own); polled every 2 s while any listed job is `queued` or `running`, otherwise every 15 s. Each row: short id, media type, provider/model, status badge, attempt, age, who ran it, prompt excerpt (creator+) or template title.
- **Right: Job detail** for the selected job (also reachable as `/jobs/<id>` so it can be linked/reloaded): polled every 1.5 s until terminal. Shows status timeline (created/started/finished, attempt n of max), error code and message, webhook state, who ran it, the template (title, slug, version, linked to its editor for creators), the request (prompt hidden for testers), and a raw-JSON toggle. For template jobs the input image(s) and the output(s) appear side by side (before / after); otherwise the asset grid.
- **Assets**: the browser sends the session cookie with `<img src="/v1/assets/...">` and `<video src>`, so they load directly, with seeking (Range) for video. A download link uses the same URL. Shows mime type, size, width x height, duration.

API types: `npm run gen:api` runs `openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts`. The generated file is committed; regenerate whenever `api/schemas.py` changes, and `npm run typecheck` catches drift.

Scripts: `dev`, `build` (`tsc -b && vite build`), `preview`, `typecheck`, `lint`, `test` (vitest), `e2e` (playwright), `gen:api`.

Tests stay small: vitest for `client.ts` (error-body parsing, 401 -> login with return path, 403 message, multipart submit doesn't set `Content-Type` by hand so the browser adds the boundary), the job query's refetch interval (stops at a terminal status), the editor's `{{variable}}` detection, and the role -> tabs mapping. Component tests use Testing Library. End to end, `npm run e2e` (Playwright) drives the compose stack with the fake provider: setup -> create a creator and a tester -> tester restrictions -> creator builds and activates a template -> tester runs it with a fixture photo -> before/after shown. The rest of the Verification checklist is by hand.

### Config (`config.py`, no prefix)

`GOOGLE_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY` (SecretStr | None); `ENABLE_FAKE_PROVIDER=false`; `DATA_DIR=./data`; `DATABASE_URL` (SecretStr, default `postgresql://studio:studio@localhost:5432/appjs`; compose overrides the host to `db`), `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, `DB_COMMAND_TIMEOUT_S=10`; compose-only `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` (default `studio`), `POSTGRES_HOST_PORT=5432`; `DEFAULT_IMAGE_PROVIDER`, `DEFAULT_VIDEO_PROVIDER`; `WORKER_ENABLED=true` (compose sets `false` on `api`), `WORKER_CONCURRENCY=2`, `WORKER_POLL_INTERVAL_S=0.5`, `WORKER_HEARTBEAT_S=15`, `STALE_JOB_AFTER_S=120`; `JOB_MAX_ATTEMPTS=3`, `RETRY_BACKOFF_BASE_S=5`, `JOB_TIMEOUT_IMAGE_S=180`, `JOB_TIMEOUT_VIDEO_S=900`, `SHUTDOWN_GRACE_S=30`; `SETUP_TOKEN` (SecretStr | None; generated and logged when unset and no users exist), `SESSION_IDLE_HOURS=12`, `SESSION_MAX_AGE_HOURS=168`, `COOKIE_SECURE=false` (true behind HTTPS), `PASSWORD_MIN_LENGTH=12`, `LOGIN_MAX_FAILURES=10`, `LOGIN_WINDOW_MIN=15`; `INPUT_IMAGE_MAX_BYTES=10485760`, `INPUT_IMAGE_MAX_PIXELS=40000000`, `INPUT_IMAGE_MAX_SIDE=2048`; `WEBHOOK_SECRET`, `WEBHOOK_TIMEOUT_S=10`, `WEBHOOK_MAX_ATTEMPTS=3`, `ALLOW_PRIVATE_WEBHOOKS=false`; `LOG_PROMPTS=false`; `HOST`, `PORT=8000`, `LOG_LEVEL=INFO`; `CORS_ORIGINS` (unset = no CORS); compose-only `WEB_PORT=8080`.

## Implementation order

0. Linux box setup from the "Development environment" section (uv, Docker Engine, compose plugin, Node); `git init`.
1. Scaffold: pyproject, `.python-version`, `uv lock`, `.env.example`, `.gitignore`, `config.py`, `logging.py`, and a first `docker-compose.yaml` holding only the `db` service (so step 4 has a database; step 17 adds `api`, `worker` and `web`). Verify `uv run python -c "from studio.config import Settings; print(Settings(_env_file=None))"`, `uv run ruff check`.
2. Domain types: `providers/base.py`, `jobs/models.py`, `auth/models.py`, `api/errors.py`.
3. Storage: `storage/base.py`, `storage/local.py`. Verify `test_local_store.py`.
4. DB: `db/engine.py`, `db/tables.py` (jobs, assets, workers), Alembic setup and revision `0001_jobs`, repository + queue. Verify `test_pg_repository.py`: N concurrent claims over M jobs never return the same job twice; a retried job claimed by worker A survives worker B's `requeue_stale`; a fenced `mark_succeeded` from a worker whose job was requeued updates nothing; two concurrent `studio db upgrade` runs both succeed and apply each revision once. `test_migrations.py`: upgrade to head, downgrade to base and back works, and `alembic check` finds no difference between `db/tables.py` and the migrations.
   Test database: `conftest.py` reads `TEST_DATABASE_URL` (default: the compose `db` on localhost), creates a throwaway database `studio_test_<random>` per session, runs `alembic upgrade head`, truncates all tables between tests, and drops the database at the end. If Postgres is unreachable the DB tests **fail** with a hint (`docker compose up -d db`), not skip.
5. FakeProvider + registry. Verify `test_registry.py`.
6. Service + worker (`run_once` first, then loop) + webhooks. Verify `test_worker.py`, `test_webhooks.py`.
7. Accounts: Alembic revision `0002_auth`, `auth/` package, `/v1/auth/*`, `/v1/users`, `require_role`, the `Origin` check, CLI `users create-admin | reset-password` and `tokens create`. `conftest.py` gains fixtures `admin`, `creator`, `tester` (signed-in test clients) and `token_for(user)`. Verify `test_auth.py` and `test_users.py`:
   - setup: wrong token -> 403; two concurrent setups create exactly one admin; setup after the first user -> 409;
   - login: same 401 for unknown email and wrong password; the 11th failure -> 429; expired and idle sessions -> 401; logout ends the session;
   - a temporary password forces `password_change_required` until changed; changing it ends other sessions;
   - deactivating a user ends sessions and tokens at once; a role change applies on the next request; the last admin can't be deactivated or demoted;
   - cookie `POST` with a foreign `Origin` -> 403; the same with a Bearer token works.
8. API + app wiring + `cli serve` + `cli worker` (worker entrypoint: build state, run worker loop until SIGTERM/SIGINT). Every route declares its role. Verify `test_api_pipeline.py` (worker enabled in-process, as a creator) and the first version of `test_permissions.py` (every route has a declared role; a tester gets 403 on `POST /v1/generations` and 404 on another user's job and its assets). Then a two-process check against the compose `db`: `uv run studio db upgrade`, `uv run studio users create-admin ...`, `uv run studio tokens create --email ...`, `WORKER_ENABLED=false uv run studio serve` in one shell, `ENABLE_FAKE_PROVIDER=true uv run studio worker` in another, curl a job through with the token.
9. OpenAI provider. Mapping tests; smoke with `OPENAI_API_KEY`.
10. Gemini provider (image then video via Interactions API). Mapping tests with fake client; smoke.
11. fal provider. Mapping tests with respx-mocked downloads; smoke Flux then Kling.
12. Image input in providers. First verify the "Image input" table against the official docs and fix it. Then `InputImage`, the capability fields, `media/images.py`, the `job_inputs` table (in revision `0003_templates`, or its own revision if this step lands first) + `put_input`, and image input in FakeProvider, OpenAI, Gemini, fal (in that order). Verify `test_images.py` (size cap -> 413, wrong type, decompression bomb, EXIF orientation applied and metadata gone, downscale) and mapping tests that the inputs reach each SDK call; smoke one real edit per provider.
13. Templates backend: Alembic revision `0003_templates`, `templates/` package, template routes with role-shaped reads, uploads, `JobResponse` additions and prompt hiding. Verify `test_templates.py` (rendering incl. injection attempts, save-time checks, versioning, restore, `version_conflict` on a stale `base_version`) and `test_template_api.py`: a tester gets 403 on every template write and on `version=`; drafts and archived templates are invisible to testers; multipart call with the fake provider runs end to end and the output differs from the input; editing the template after submit doesn't change the queued job; a tester's `GET` hides the prompt and a creator's shows it; a missing required slot or an unknown field is a 422. Extend `test_permissions.py` to the template routes.
14. CLI `generate` (incl. `--template`; token from `STUDIO_TOKEN`) / `providers`, README with first-run setup, curl examples (plain and template, with a token) and env table.
15. Frontend in `web/`: `npm create vite@latest web -- --template react-ts`, trim the template, add `vite.config.ts` proxy (`changeOrigin: false`), `.nvmrc`, eslint, vitest, Mantine (with `postcss-preset-mantine`), TanStack Query, React Router. Then `npm run gen:api` against a running API, `client.ts`, `queries.ts`, `routes.tsx` + `RequireRole`, SetupPage, LoginPage, ChangePassword, TopBar, Tabs, AccountPage (tokens), UsersPage, then GenerateForm, JobList, JobDetail, AssetView. Verify with `npm run typecheck && npm run lint && npm test && npm run build`, then the manual sign-in and fake-provider runs from Verification using `npm run dev` against `uv run studio serve` + `uv run studio worker`.
16. Frontend templates: UseTemplate, TemplateList, TemplateEditor, TemplateHistory, TemplateTestRun; template and "mine / everyone" filters in JobList; before/after in JobDetail. Same checks as step 15 plus the template walk-through in Verification.
17. Dockerfile + docker-compose. One multi-stage image (`python:3.12-slim`, uv `--frozen --no-dev` copied from `ghcr.io/astral-sh/uv` stage, non-root user `app` uid 10001, `WORKDIR /app`, `curl` installed for the healthcheck). Compose services:
    - `db`: `image: postgres:17`, `environment: POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` from `.env`, `volumes: pgdata:/var/lib/postgresql/data`, `ports: "127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"`, healthcheck `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`, `restart: unless-stopped`. Top-level `volumes: {pgdata: {}}`.
    - `api`: `command: studio serve`, `ports: 8000:8000`, `WORKER_ENABLED=false`, healthcheck `curl -f http://localhost:8000/healthz`.
    - `worker`: `command: studio worker`, healthcheck `studio health` (exits non-zero if its own heartbeat is stale), `stop_grace_period: 45s` (> `SHUTDOWN_GRACE_S`).
    - `web`: built from `web/Dockerfile` (stage 1 `node:22-alpine`: `npm ci && npm run build`; stage 2 `nginx:1.27-alpine` with `dist/` and `nginx.conf`), `ports: "${WEB_PORT:-8080}:80"`, `depends_on: {api: {condition: service_healthy}}`, `restart: unless-stopped`. nginx: `try_files $uri /index.html`; `location /v1/` and `location = /healthz` proxy to `http://api:8000`; `proxy_read_timeout 60s`; `proxy_buffering off` for `/v1/assets/` and `/v1/inputs/`; `client_max_body_size 25m` (several input images per request); `proxy_set_header Host $http_host`, `X-Forwarded-For` and `X-Forwarded-Proto`, so the API's `Origin` check and login throttle see the browser's host and IP (uvicorn trusts these headers only from the compose network, via `--forwarded-allow-ips`).
    - `migrate`: same image, `command: studio db upgrade`, `depends_on: {db: {condition: service_healthy}}`, `restart: "no"`; exits when the schema is at head.
    - `api` and `worker`: `depends_on: {db: {condition: service_healthy}, migrate: {condition: service_completed_successfully}}`, `environment: DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`, `env_file: .env`, `volumes: ./data:/app/data`, `user: "${UID:-10001}:${GID:-10001}"`, `restart: unless-stopped`.
    Verify on the Linux box: `mkdir -p data && docker compose up --build -d`, `docker compose ps` shows `db`, `api`, `worker` healthy and `web` up, read the setup token from `docker compose logs api`, finish setup at `http://<host>:8080/setup`, create a creator and a tester, run a fake-provider job as each, then `docker compose up -d --scale worker=3` and confirm three worker heartbeats in `/healthz`. `docker compose stop worker` mid-job and confirm the job is requeued after `STALE_JOB_AFTER_S`. `docker compose restart db` while idle: `api` and `worker` recover without restarting (the pool reconnects; the LISTEN connection is re-opened).
18. Hardening: `npm run e2e` (Playwright roles and templates specs) against the compose stack; complete `test_permissions.py` (route x role table for every endpoint), webhook private-host rule, prompt redaction (template prompts too), login throttle under concurrency, list endpoint.

## Verification

- `uv run ruff check . && uv run ruff format --check .`
- `docker compose up -d db && uv run pytest` (FakeProvider only, no provider network calls; Postgres from compose): pipeline POST -> poll -> GET asset bytes for image (n=2) and video; template call with an uploaded image -> output asset; template CRUD, versions; setup, login, sessions, tokens, user management and the route x role permission table; webhook delivered with signature; 422/401/404/503 cases; worker retry/policy/timeout/shutdown; atomic claim.
- Two-process run (only the `db` container needed): `WORKER_ENABLED=false ENABLE_FAKE_PROVIDER=true uv run studio serve` and `ENABLE_FAKE_PROVIDER=true uv run studio worker` in separate shells; POST a job to the API, confirm the worker picks it up, `/healthz` lists the worker heartbeat, asset downloads. Kill the worker mid-job (`SLEEP:30` prompt) and confirm the job returns to `queued` after `STALE_JOB_AFTER_S`.
- Accounts, by hand (under `npm run dev`, and again on `:8080` in compose with an empty database):
  - the first visit shows Setup; a wrong setup token is refused; the right one creates the admin and lands on Users. Opening `/setup` again shows "already set up".
  - the admin adds `c@example.com` (creator) and `t@example.com` (tester); each temporary password is shown once. Signing in as each forces a password change first.
  - the tester sees only Use template; typing `/templates/<id>` or `/users` shows "your role can't do this", and the API returns 403 for the same calls (try with curl and the tester's token).
  - the creator sees Use template, Generate and Templates, but not Users.
  - eleven wrong passwords for one email -> "too many attempts"; signing in works again after the window.
  - the admin deactivates the tester: the tester's open tab drops to login on its next request, and the tester's API token returns 401. The admin can't deactivate their own row.
  - Account: create a token, run the shown curl, revoke it, and the same curl returns 401.
- Frontend: `cd web && npm run typecheck && npm run lint && npm test && npm run build`, and `npm run e2e` against the compose stack. Then by hand in the console as a creator with `ENABLE_FAKE_PROVIDER=true`:
  - image `n=2` and a video job go queued -> running -> succeeded, and the assets render and download;
  - `FAIL_TRANSIENT` shows the attempt count climbing, then success or `failed` at max attempts; `FAIL_POLICY` fails at once with `content_policy`;
  - `SLEEP:30`, then `docker compose stop worker` (or kill the worker process): the job goes back to `queued` after `STALE_JOB_AFTER_S` and `/healthz` turns `degraded`;
  - a 422 (e.g. `n=3` on a provider with `max_images=2`) shows the error next to the field;
  - reloading `/jobs/<id>` reopens that job.
- Templates, by hand with `ENABLE_FAKE_PROVIDER=true`, signed in as the creator unless stated:
  - create "Ghibli (fake)" on the fake provider with a `photo` slot and a `{{mood}}` variable; it saves as draft v1. Test-run it with a photo: input and output side by side.
  - as the tester, the draft isn't listed; activate it as the creator and it appears.
  - typing `{{weather}}` in the prompt without declaring it blocks the save with the field error; adding it fixes it.
  - as the tester: Use template lists it without the prompt, a run succeeds, Job detail shows no prompt, and the job list shows only the tester's own jobs.
  - as the creator, in two tabs: save in one, then save in the other -> the conflict message names who saved first.
  - as the creator, change the model (v2) while a `SLEEP:30` job from v1 is queued: that job still reports v1; History shows v1 and v2 with author and the model as the changed field; restore v1 as v3.
  - archive it: it vanishes from Use template and a call returns 404.
  - upload a 15 MB file -> 413; a `.txt` renamed to `.jpg` -> 422 naming the slot; a phone photo taken in portrait comes out portrait.
  - repeat the run once with real Gemini and the "Ghibli Image Generation with Gemini" example.
- Docker (on the Linux box): `docker compose up --build -d`, same curl flow, then `docker compose up -d --scale worker=3`; `docker compose logs -f worker` shows claims and completions.
- Real smoke: `uv run pytest -m smoke tests/smoke` with keys set; and end-to-end `uv run studio serve` then `STUDIO_TOKEN=crt_... uv run studio generate --media image --provider gemini --out ./out "a red bicycle on a beach"`, and `--media video --duration 5` for Omni and Kling.

## Risks

- Content-policy rejections -> `failed/content_policy`, never retried; partial results are success with fewer assets.
- Large videos streamed to `DATA_DIR/tmp` then `os.replace`d; no retention policy in v1 (follow-up: `ASSET_RETENTION_DAYS`, `DELETE /v1/generations/{id}`).
- Retries after a mid-flight cancel can double-bill a provider; bounded by `max_attempts` and non-retryable timeout.
- Prompts are stored in Postgres and returned by GET; logs never contain them unless `LOG_PROMPTS`.
- Postgres in compose is single-node with no backups: `docker compose down -v` deletes `pgdata` and every job record (the asset files in `./data` survive but become orphaned). For anything beyond dev, point `DATABASE_URL` at a managed Postgres and add `pg_dump` backups; no code change needed.
- Connection budget: each `api` and `worker` process opens up to `DB_POOL_SIZE + DB_MAX_OVERFLOW` pooled connections plus one LISTEN connection per worker. With `--scale worker=N`, keep `(N + 1) * (DB_POOL_SIZE + DB_MAX_OVERFLOW + 1)` under Postgres `max_connections` (100 by default).
- Assets and job records live in two places (volume and Postgres): a crash between writing files and committing `mark_succeeded` leaves orphan files; the retry overwrites them at the same `<job_id>/<idx>` paths.
- The default credentials (`studio`/`studio`) are for dev only. Postgres is published on loopback only; set a real `POSTGRES_PASSWORD` in `.env` anywhere else.
- Worker crash between provider success and `mark_succeeded`: the job is requeued by heartbeat age and re-billed once. Bounded by `max_attempts`.
- Google Interactions API is new and `gemini-omni-1.1-flash` has a listed retirement of "2026-11-17 or later"; keep model IDs in config defaults, not code.
- No rate limiting or idempotency in v1; follow-up: `Idempotency-Key` header, per-key quotas.
- First-run window: until setup is done, anyone who can read the api log (or knows `SETUP_TOKEN`) can become admin. Finish setup right after the first `docker compose up`, and don't share logs before then.
- Plain HTTP: on a shared host without TLS, passwords and session cookies cross the network in the clear. Put the stack behind HTTPS (and set `COOKIE_SECURE=true`) before anyone signs in from another machine; until then, keep ports on `127.0.0.1`.
- No email: there's no invite or "forgot password" mail. The admin hands out temporary passwords out of band and resets them on request; a locked-out admin recovers with `studio users reset-password` from a shell on the host.
- Any creator can edit or archive any template, and any creator can see every job (including testers' uploaded photos). This fits one small trusted team; per-template owners or teams are a follow-up.
- API tokens don't expire; they last until revoked or the owner is deactivated. A token expiry option is a follow-up.
- The provider calls with input images are not verified yet (see "Image input"). Some image models may not take input images at all, or take fewer than a template needs; the save-time checks only know what `image_input_models` and `max_input_images` say.
- Users upload personal photos, often with faces. They are stored with the job until it's deleted, sent to the chosen provider (fal: to fal's storage), and visible to the uploader, all creators and the admin. Metadata is stripped on upload, but there's no retention policy in v1; the `ASSET_RETENTION_DAYS` follow-up must cover `inputs/` too. Check each provider's data-use terms before real user traffic.
- Providers refuse some photo edits (minors, real public figures, named artists' styles); these end as `failed/content_policy`, never retried. Template prompts should describe a style rather than name a studio or artist.
- Template prompts are the creators' work and are hidden from testers in the API, but a determined tester can often infer them from outputs; hiding is a convenience, not a secret.
- No per-user quotas or spend limits in v1: a tester can run active templates as often as they like. Follow-up: per-user daily job limits.

## Open questions

- Should testers also be able to try **draft** templates that a creator shares with them, before activation? (Now: active only.)
- Should creators see all jobs, or only their own plus jobs run on templates they edited? (Now: all.)
- Single sign-on (Google Workspace) instead of passwords later? The `users` table would stay; only the login step changes.
- Should callers be able to pass an image URL instead of uploading a file (`photo_url=`)? It would need the same private-host check as webhooks.
- Image -> video templates (e.g. animate the Ghibli still with Kling image-to-video): same template model, `media_type: video`; needs the providers' image-to-video calls verified.


## App users, credits and subscriptions (added 2026-11-03)

The people using a client app (e.g. Reelify) now have accounts. Decisions (user, 2026-11-03): sign-in
with Google **and** a phone code sent by our own SMS gateway; subscriptions that grant credits; payments
(Razorpay / phone billing) come later.

- Accounts are per app (`app_users`, unique `(app_id, google_sub)` and `(app_id, phone)`). A Google account
  and a phone number are separate accounts (no linking yet).
- Sessions are opaque bearer tokens (`cas_…`, sha256 in `app_user_sessions`), 90-day sliding expiry, sent
  with the app key. `AppUserDep` (studio/deps.py) resolves them; `apps.require_login` makes them
  mandatory for the catalog, runs and results.
- Phone codes: HMAC-SHA256 (`OTP_SECRET`) of a 6-digit code, 5 min, 5 tries, resend after 30 s, hourly
  limits per number/device/IP. `SmsSender`: `log` (dev) or `msg91` (DLT template). Store-review numbers
  get fixed codes.
- Google: ID token checked against Google's certs (cached by Cache-Control), issuer, expiry,
  `aud` ∈ `apps.google_client_ids` (Web client ids), verified email.
- Credits: `credit_ledger` is the source of truth, one row per change with a unique idempotency key
  (`signup:`, `gen:<job>`, `refund:<job>`, `grant:<sub>:m<n>`, `adjust:`); `app_users.credits` is
  updated in the same transaction (check `credits >= 0`). A run is charged in the transaction that
  inserts its job, under a row lock (no overspending in parallel). A job that ends `failed` is refunded
  in the transaction that marks it failed (`mark_failed`, and `requeue_stale` for lost workers).
- `templates.credit_cost` (default 1) is pricing, not versioned content; editors set it.
- Plans (per app) grant `credits_per_month` every month for every billing period. Subscriptions are
  granted by admins (`provider = manual`) until a `PaymentProvider` exists; workers run
  `grant_due_credits` from the heartbeat loop (once a minute, safe in parallel) and expire ended
  subscriptions. Credits don't expire.
- Later: Razorpay (`PaymentProvider` + signed webhook). Play Store apps selling digital goods must use
  Play Billing or Google's user-choice / alternative billing (India) — check before building it.
