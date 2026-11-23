from __future__ import annotations

import re
from dataclasses import dataclass, replace
from uuid import UUID

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from creative.apps.service import AppPrincipal, AppService
from creative.auth.service import AppRole, AuthService, Principal, Role
from creative.config import Settings
from creative.endusers.billing import BillingService
from creative.endusers.service import AccountBlocked, AppUserService
from creative.errors import ServiceError
from creative.jobs.pg_repository import PgJobQueue, PgJobRepository
from creative.jobs.service import GenerationService
from creative.jobs.webhooks import WebhookSender
from creative.jobs.worker import Worker
from creative.providers.registry import ProviderRegistry
from creative.storage.local import LocalAssetStore
from creative.templates.service import TemplateService

SESSION_COOKIE = "creative_session"


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    db: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    store: LocalAssetStore
    registry: ProviderRegistry
    repo: PgJobRepository
    queue: PgJobQueue
    auth: AuthService
    generations: GenerationService
    templates: TemplateService
    webhooks: WebhookSender
    apps: AppService
    endusers: AppUserService
    billing: BillingService
    worker: Worker | None = None


def get_state(request: Request) -> AppState:
    return request.app.state.creative


class Unauthenticated(ServiceError):
    status, code = 401, "unauthenticated"


class Forbidden(ServiceError):
    status, code = 403, "forbidden"


class NotFound(ServiceError):
    status, code = 404, "not_found"


class PasswordChangeRequired(ServiceError):
    status, code = 403, "password_change_required"


async def current_principal(request: Request, state: AppState = Depends(get_state)) -> Principal:
    if hasattr(request.state, "principal"):
        return request.state.principal
    principal = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        principal = await state.auth.resolve_api_token(auth[7:].strip())
        if principal is None:
            raise Unauthenticated("invalid or revoked API token")
    elif token := request.cookies.get(SESSION_COOKIE):
        principal = await state.auth.resolve_session(token)
    if principal is None:
        raise Unauthenticated("sign in required")
    request.state.principal = principal
    return principal


class RoleDep:
    """`Depends(require_role(Role.admin))`. Every /v1 route has one (or `public()`, an
    `AppRoleDep` or the app key), which
    tests/test_permissions.py checks by walking the app's routes."""

    def __init__(self, min_role: Role | None, allow_pending_password: bool = False):
        self.min_role = min_role
        self.allow_pending_password = allow_pending_password

    async def __call__(self, request: Request, state: AppState = Depends(get_state)) -> Principal | None:
        if self.min_role is None:
            return None
        p = await current_principal(request, state)
        if p.user.must_change_password and not self.allow_pending_password:
            raise PasswordChangeRequired("change your temporary password first")
        if p.role < self.min_role:
            raise Forbidden(f"this needs the {self.min_role.name} role")
        return p


def require_role(role: Role, *, allow_pending_password: bool = False) -> RoleDep:
    return RoleDep(role, allow_pending_password)


def public() -> RoleDep:
    return RoleDep(None)


signed_in = require_role(Role.user)
signed_in_pending_ok = require_role(Role.user, allow_pending_password=True)
admin = require_role(Role.admin)


@dataclass
class AppContext:
    principal: Principal
    app: object  # creative.db.tables.App
    role: AppRole

    @property
    def can_edit(self) -> bool:
        return self.role >= AppRole.editor


class AppRoleDep:
    """`Depends(app_member(AppRole.editor))` on routes under /v1/apps/{app_id}: the signed-in user
    needs at least that role in the app (admins have every role). No access at all is a 404."""

    def __init__(self, min_role: AppRole):
        self.min_role = min_role
        self.user_dep = RoleDep(Role.user)

    async def __call__(
        self, request: Request, app_id: UUID, state: AppState = Depends(get_state)
    ) -> AppContext:
        p = await self.user_dep(request, state)
        role = await state.apps.role_of(p.user, app_id)
        if role is None:
            raise NotFound("app not found")
        app = await state.apps.get(app_id)
        if role < self.min_role:
            raise Forbidden(f"this needs the {self.min_role.name} role in this app")
        return AppContext(p, app, role)


def app_member(role: AppRole = AppRole.tester) -> AppRoleDep:
    return AppRoleDep(role)


tester = app_member(AppRole.tester)
editor = app_member(AppRole.editor)


DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class AppDisabled(ServiceError):
    status, code = 403, "app_disabled"


class AppKeyDep:
    """`Depends(app_key)`: the caller is an app (e.g. Android), identified by `X-App-Key: cak_...`.
    `X-Device-Id` (optional, opaque, per install) is recorded on jobs and used for per-device limits."""

    async def __call__(self, request: Request, state: AppState = Depends(get_state)) -> AppPrincipal:
        raw = request.headers.get("x-app-key", "").strip()
        found = await state.apps.resolve_key(raw) if raw else None
        if found is None:
            raise Unauthenticated("missing or invalid X-App-Key")
        app, key = found
        if app.status != "active":
            raise AppDisabled("this app is disabled")
        device = request.headers.get("x-device-id")
        if device is not None and not DEVICE_ID_RE.match(device):
            raise ServiceError("X-Device-Id: 1-128 characters of letters, digits and . _ : -", "x-device-id")
        return AppPrincipal(app, key.id, device)


app_key = AppKeyDep()


class AppUserDep:
    """`Depends(app_user())`: an app-key call (see `AppKeyDep`) that may also carry the end user's
    session, `Authorization: Bearer cas_...`.

    - `required=True`: the user must be signed in.
    - `required=None`: signed in only if the app has `require_login` on; a token, when sent, must
      still be valid.
    The returned `AppPrincipal.user` is the signed-in user or None."""

    def __init__(self, required: bool | None):
        self.required = required

    async def __call__(
        self, request: Request, a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)
    ) -> AppPrincipal:
        user = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            user = await state.endusers.resolve_session(a.app.id, auth[7:].strip())
            if user is None:
                raise Unauthenticated("your session has ended; sign in again")
            if user.status == "blocked":
                raise AccountBlocked("this account is blocked")
        need = a.app.require_login if self.required is None else self.required
        if need and user is None:
            raise Unauthenticated("sign in required")
        return replace(a, user=user)


def app_user(required: bool | None = True) -> AppUserDep:
    return AppUserDep(required)


signed_in_app_user = app_user(True)
app_user_if_required = app_user(None)
