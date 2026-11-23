from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from studio.api import (
    admin,
    admin_endusers,
    assets,
    auth,
    client,
    client_auth,
    generations,
    meta,
    templates,
)
from studio.api.errors import error_response, install_error_handlers
from studio.apps.providers import AppProviders
from studio.apps.service import AppService
from studio.auth.service import AuthService
from studio.config import Settings
from studio.db.engine import create_engine, require_head, session_factory
from studio.deps import AppState
from studio.endusers.billing import BillingService
from studio.endusers.service import AppUserService
from studio.jobs.pg_repository import PgJobQueue, PgJobRepository
from studio.jobs.service import GenerationService
from studio.jobs.webhooks import WebhookSender
from studio.jobs.worker import Worker
from studio.providers.registry import ProviderRegistry
from studio.secrets import SecretBox
from studio.storage.local import LocalAssetStore
from studio.templates.service import TemplateService

log = logging.getLogger(__name__)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


async def build_state(settings: Settings, registry: ProviderRegistry | None = None) -> AppState:
    engine = create_engine(settings)
    await require_head(engine)
    db = session_factory(engine)
    http = httpx.AsyncClient(timeout=30)
    box = SecretBox(settings.secrets_key)
    store = LocalAssetStore(settings.data_dir)
    registry = registry or ProviderRegistry.from_settings(settings, http, store.temp_dir())
    repo, queue = PgJobRepository(db), PgJobQueue(db)
    apps = AppService(db, box)
    providers = AppProviders(registry, apps)  # an app's own provider keys, else the server's
    generations_svc = GenerationService(settings, db, repo, registry, providers)
    return AppState(
        settings=settings,
        engine=engine,
        db=db,
        http=http,
        store=store,
        registry=registry,
        repo=repo,
        queue=queue,
        auth=AuthService(settings, db),
        generations=generations_svc,
        templates=TemplateService(settings, db, registry, store, repo, providers),
        webhooks=WebhookSender(settings, http, repo, generations_svc.payload_for_webhook),
        apps=apps,
        providers=providers,
        endusers=AppUserService(settings, db, http, box=box),
        billing=BillingService(db),
    )


async def close_state(state: AppState) -> None:
    await state.registry.aclose()
    await state.http.aclose()
    await state.engine.dispose()


def make_worker(state: AppState) -> Worker:
    return Worker(
        state.settings,
        state.queue,
        state.repo,
        state.store,
        state.registry,
        state.webhooks,
        billing=state.billing,
        providers=state.providers,
    )


def create_app(settings: Settings | None = None, registry: ProviderRegistry | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = await build_state(settings, registry)
        app.state.studio = state
        if token := await state.auth.ensure_setup_token():
            log.warning("First-run setup: open /setup and use setup token %s", token)
        if not state.registry.providers:
            log.warning(
                "no providers configured: set GOOGLE_API_KEY, OPENAI_API_KEY, FAL_KEY or "
                "ENABLE_FAKE_PROVIDER=true"
            )
        if settings.worker_enabled:
            state.worker = make_worker(state)
            await state.worker.start()
        try:
            yield
        finally:
            if state.worker:
                await state.worker.stop()
            await close_state(state)

    app = FastAPI(title="AppJs Studio", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """CSRF guard: a browser write must come from this site. Bearer-token calls and clients
        that send neither Origin nor Referer (curl, SDKs) are not browsers and pass."""
        if request.method in UNSAFE and not request.headers.get("authorization", "").lower().startswith(
            "bearer "
        ):
            source = request.headers.get("origin") or request.headers.get("referer")
            if source:
                allowed = {request.headers.get("host", "")}
                if settings.cors_origins:
                    allowed |= {urlsplit(o.strip()).netloc for o in settings.cors_origins.split(",")}
                if urlsplit(source).netloc not in allowed:
                    return error_response(403, "cross_site_request", "request from another site refused")
        return await call_next(request)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for r in (
        meta.router,
        auth.router,
        generations.router,
        assets.router,
        templates.apps_router,
        templates.router,
        templates.manage,
        admin.router,
        admin_endusers.router,
        client_auth.router,
        client.router,
    ):
        app.include_router(r)
    return app
