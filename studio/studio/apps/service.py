"""Apps are workspaces: each owns its templates, has members (editor or tester) and keys for its
client (e.g. Android) to call /v1/app/* with `X-App-Key: cak_...`."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studio.auth.service import AppRole, Role
from studio.db.tables import App, AppKey, AppMember, AppUser, Job, Template, User
from studio.errors import ConflictError, NotFoundError, ServiceError, ValidationFailed
from studio.secrets import SecretBox

KEY_PREFIX = "cak_"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])$")
AUTOREV_APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
AUTOREV_SECRET_RE = re.compile(r"^\S{16,200}$")
MSG91_TEMPLATE_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
MSG91_VAR_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
MSG91_KEY_RE = re.compile(r"^\S{10,200}$")
FIREBASE_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
# The app's own AI provider keys, by provider name: write-only settings fields like the MSG91 key.
PROVIDER_KEY_FIELDS = {
    "gemini": "gemini_api_key",
    "openai": "openai_api_key",
    "fal": "fal_api_key",
    "openrouter": "openrouter_api_key",
}
PROVIDER_KEY_RE = re.compile(r"^\S{10,500}$")
# write-only fields: encrypted into <name>_enc, never returned
SECRET_FIELDS = (
    "msg91_auth_key",
    *PROVIDER_KEY_FIELDS.values(),
    "autorev_api_key",
    "autorev_webhook_secret",
)


class RateLimited(ServiceError):
    status, code = 429, "rate_limited"


class AppFields(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    platform: str = Field("android", pattern="^(android|ios|web|other)$")
    status: str = Field("active", pattern="^(active|disabled)$")
    daily_job_limit: int | None = Field(None, ge=1)
    device_hourly_limit: int | None = Field(None, ge=1)
    # end-user sign-in; fields left out of an update keep their value
    auth_google_enabled: bool = False
    auth_phone_enabled: bool = False
    google_client_ids: list[str] = Field(default_factory=list, max_length=10)
    phone_provider: str = Field("msg91", pattern="^(msg91|firebase)$")
    msg91_template_id: str | None = Field(None, max_length=64)
    msg91_otp_var: str | None = Field(None, max_length=32)
    # write-only: a value replaces the saved key, null removes it, leaving it out keeps it
    msg91_auth_key: str | None = Field(None, max_length=200)
    firebase_project_id: str | None = Field(None, max_length=64)
    # the app's own AI provider keys, write-only like msg91_auth_key: a value replaces the saved key,
    # null removes it (the server's key is used again), leaving it out keeps it
    gemini_api_key: str | None = Field(None, max_length=500)
    openai_api_key: str | None = Field(None, max_length=500)
    fal_api_key: str | None = Field(None, max_length=500)
    openrouter_api_key: str | None = Field(None, max_length=500)
    signup_credits: int = Field(0, ge=0, le=100_000)
    require_login: bool = False
    # payments: the gateway, and the autorev app it bills through (gateway keys and test/live mode are
    # set in autorev). The API key and webhook secret are write-only like msg91_auth_key.
    payment_provider: str = Field("none", pattern="^(none|razorpay|phonepe)$")
    autorev_app_id: str | None = Field(None, max_length=64)
    autorev_api_key: str | None = Field(None, max_length=200)
    autorev_webhook_secret: str | None = Field(None, max_length=200)

    @field_validator(
        "autorev_app_id",
        "autorev_api_key",
        "autorev_webhook_secret",
        "msg91_template_id",
        "msg91_otp_var",
        "msg91_auth_key",
        "firebase_project_id",
        "gemini_api_key",
        "openai_api_key",
        "fal_api_key",
        "openrouter_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v

    @field_validator("msg91_template_id")
    @classmethod
    def _msg91_template(cls, v: str | None) -> str | None:
        if v is not None and not MSG91_TEMPLATE_RE.match(v):
            raise ValueError("an MSG91 template id is letters and digits (MSG91 → Flow / OTP templates)")
        return v

    @field_validator("msg91_otp_var")
    @classmethod
    def _msg91_var(cls, v: str | None) -> str | None:
        if v is not None and not MSG91_VAR_RE.match(v):
            raise ValueError("the variable name in the template, without the ## (e.g. otp)")
        return v

    @field_validator("msg91_auth_key")
    @classmethod
    def _msg91_key(cls, v: str | None) -> str | None:
        if v is not None and not MSG91_KEY_RE.match(v):
            raise ValueError("an MSG91 auth key has no spaces and is at least 10 characters")
        return v

    @field_validator("gemini_api_key", "openai_api_key", "fal_api_key", "openrouter_api_key")
    @classmethod
    def _provider_key(cls, v: str | None) -> str | None:
        if v is not None and not PROVIDER_KEY_RE.match(v):
            raise ValueError("paste the whole API key: no spaces, at least 10 characters")
        return v

    @field_validator("firebase_project_id")
    @classmethod
    def _firebase_project(cls, v: str | None) -> str | None:
        if v is not None and not FIREBASE_PROJECT_RE.match(v):
            raise ValueError("a Firebase project id looks like my-app-1a2b3 (Project settings → General)")
        return v

    @field_validator("autorev_app_id")
    @classmethod
    def _autorev_app_id(cls, v: str | None) -> str | None:
        if v is not None and not AUTOREV_APP_ID_RE.match(v):
            raise ValueError("paste the App ID from autorev (letters and digits, from the app's Settings)")
        return v

    @field_validator("autorev_api_key", "autorev_webhook_secret")
    @classmethod
    def _autorev_secret(cls, v: str | None) -> str | None:
        if v is not None and not AUTOREV_SECRET_RE.match(v):
            raise ValueError("paste the whole value from autorev: no spaces, at least 16 characters")
        return v

    @field_validator("google_client_ids")
    @classmethod
    def _client_ids(cls, v: list[str]) -> list[str]:
        ids = list(dict.fromkeys(x.strip() for x in v if x.strip()))
        bad = [x for x in ids if len(x) > 256 or not x.endswith(".apps.googleusercontent.com")]
        if bad:
            raise ValueError("Google client ids look like 1234-abc.apps.googleusercontent.com")
        return ids


class AppCreate(AppFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug: 3-64 lower-case letters, digits and dashes; no dash at the ends")
        return v


class AppPatch(AppFields):
    """PATCH: only the fields sent change (each settings section saves on its own)."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)


@dataclass
class AppPrincipal:
    """A call made with an app key."""

    app: App
    key_id: UUID
    device_id: str | None
    user: AppUser | None = None  # the signed-in end user, when the call carries their bearer token


@dataclass
class Counts:
    templates: int = 0
    active_templates: int = 0
    keys: int = 0
    members: int = 0


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AppService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], box: SecretBox | None = None):
        self.db = sessions
        self.box = box or SecretBox(None)

    def _encrypt_secrets(self, changes: dict) -> dict:
        """Turn write-only fields into their encrypted columns: a value is encrypted, None clears."""
        for name in SECRET_FIELDS:
            if name in changes:
                value = changes.pop(name)
                changes[f"{name}_enc"] = self.box.encrypt(value) if value else None
        return changes

    # ---- apps ------------------------------------------------------------------------------------
    async def provider_keys(self, app_id: UUID | None) -> dict[str, str]:
        """The app's own provider keys, decrypted, by provider name (only those it has). A key that
        can't be decrypted (SECRETS_KEY changed or missing) raises rather than falling back to the
        server's key, so an app never runs on the server's account by surprise."""
        if app_id is None:
            return {}
        async with self.db() as s:
            app = await s.get(App, app_id)
        if app is None:
            return {}
        out = {}
        for provider, field in PROVIDER_KEY_FIELDS.items():
            token = getattr(app, f"{field}_enc")
            if token:
                out[provider] = self.box.decrypt(token)
        return out

    def autorev_credentials(self, app: App) -> tuple[str, str] | None:
        """The app's autorev app id and API key, decrypted; None until both are set."""
        if not app.autorev_app_id or not app.autorev_api_key_enc:
            return None
        return app.autorev_app_id, self.box.decrypt(app.autorev_api_key_enc)

    def autorev_webhook_secret(self, app: App) -> str | None:
        return self.box.decrypt(app.autorev_webhook_secret_enc) if app.autorev_webhook_secret_enc else None

    async def by_autorev_app(self, autorev_app_id: str) -> App | None:
        async with self.db() as s:
            return await s.scalar(
                select(App).where(App.autorev_app_id == autorev_app_id, App.deleted_at.is_(None))
            )

    async def get(self, app_id: UUID) -> App:
        async with self.db() as s:
            app = await s.get(App, app_id)
        if app is None or app.deleted_at is not None:
            raise NotFoundError("app not found")
        return app

    async def counts(self, app_ids: list[UUID]) -> dict[UUID, Counts]:
        out = {a: Counts() for a in app_ids}
        if not app_ids:
            return out
        async with self.db() as s:
            rows = await s.execute(
                select(Template.app_id, func.count(), func.count().filter(Template.status == "active"))
                .where(Template.app_id.in_(app_ids), Template.deleted_at.is_(None))
                .group_by(Template.app_id)
            )
            for app_id, n, active in rows:
                out[app_id].templates, out[app_id].active_templates = n, active
            rows = await s.execute(
                select(AppKey.app_id, func.count())
                .where(AppKey.app_id.in_(app_ids), AppKey.revoked_at.is_(None))
                .group_by(AppKey.app_id)
            )
            for app_id, n in rows:
                out[app_id].keys = n
            rows = await s.execute(
                select(AppMember.app_id, func.count())
                .join(User, User.id == AppMember.user_id)
                .where(AppMember.app_id.in_(app_ids), User.deleted_at.is_(None))
                .group_by(AppMember.app_id)
            )
            for app_id, n in rows:
                out[app_id].members = n
        return out

    async def list_all(self) -> list[App]:
        async with self.db() as s:
            q = select(App).where(App.deleted_at.is_(None)).order_by(App.name)
            return list((await s.scalars(q)).all())

    async def visible_to(self, user: User) -> list[tuple[App, AppRole]]:
        """The apps a user can open, with their role in each (admins: every app, as admin)."""
        if Role.of(user) == Role.admin:
            return [(a, AppRole.admin) for a in await self.list_all()]
        async with self.db() as s:
            rows = await s.execute(
                select(App, AppMember.role)
                .join(AppMember, AppMember.app_id == App.id)
                .where(AppMember.user_id == user.id, App.deleted_at.is_(None))
                .order_by(App.name)
            )
            return [(a, AppRole[r]) for a, r in rows]

    async def role_of(self, user: User, app_id: UUID) -> AppRole | None:
        if Role.of(user) == Role.admin:
            return AppRole.admin
        async with self.db() as s:
            r = await s.scalar(
                select(AppMember.role).where(AppMember.app_id == app_id, AppMember.user_id == user.id)
            )
        return AppRole[r] if r else None

    async def create(self, actor: User, body: AppCreate) -> App:
        async with self.db.begin() as s:
            if await s.scalar(select(App.id).where(App.slug == body.slug)):
                raise ConflictError("an app with this slug exists", "slug")
            fields = self._encrypt_secrets(body.model_dump())
            app = App(id=uuid.uuid4(), created_by=actor.id, **fields)
            s.add(app)
        return await self.get(app.id)

    async def update(self, app_id: UUID, body: AppFields) -> App:
        """PUT and PATCH: the fields sent change, the rest keep their value."""
        changes = body.model_dump(exclude_unset=True)
        for required in ("name", "description", "platform", "status", "phone_provider"):
            if required in changes and changes[required] is None:
                raise ValidationFailed(f"{required} can't be empty", required)
        changes = self._encrypt_secrets(changes)
        async with self.db.begin() as s:
            app = await s.get(App, app_id, with_for_update=True)
            if app is None or app.deleted_at is not None:
                raise NotFoundError("app not found")
            await s.execute(update(App).where(App.id == app_id).values(**changes, updated_at=func.now()))
        return await self.get(app_id)

    async def delete(self, app_id: UUID) -> None:
        """Soft delete: the app, its templates and members disappear; keys stop working; past jobs
        keep their app name. The slug is freed for a new app."""
        async with self.db.begin() as s:
            app = await s.get(App, app_id, with_for_update=True)
            if app is None or app.deleted_at is not None:
                raise NotFoundError("app not found")
            app.deleted_at = func.now()
            app.status = "disabled"
            app.slug = f"deleted-{app.id.hex[:12]}"
            await s.execute(
                update(AppKey)
                .where(AppKey.app_id == app_id, AppKey.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            await s.execute(
                update(Template)
                .where(Template.app_id == app_id, Template.deleted_at.is_(None))
                .values(deleted_at=func.now())
            )
            await s.execute(delete(AppMember).where(AppMember.app_id == app_id))

    # ---- members -----------------------------------------------------------------------------------
    async def members(self, app_id: UUID) -> list[tuple[User, str]]:
        async with self.db() as s:
            rows = await s.execute(
                select(User, AppMember.role)
                .join(AppMember, AppMember.user_id == User.id)
                .where(AppMember.app_id == app_id, User.deleted_at.is_(None))
                .order_by(User.name)
            )
            return [(u, r) for u, r in rows]

    async def memberships(self, user_id: UUID) -> list[tuple[App, str]]:
        async with self.db() as s:
            rows = await s.execute(
                select(App, AppMember.role)
                .join(AppMember, AppMember.app_id == App.id)
                .where(AppMember.user_id == user_id, App.deleted_at.is_(None))
                .order_by(App.name)
            )
            return [(a, r) for a, r in rows]

    async def set_member(self, app_id: UUID, user_id: UUID, role: str) -> None:
        if role not in ("editor", "tester"):
            raise ValidationFailed("role must be editor or tester", "role")
        await self.get(app_id)
        async with self.db.begin() as s:
            user = await s.get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("user not found")
            if user.role == "admin":
                raise ValidationFailed("admins can already open every app", "user_id")
            await s.execute(
                insert(AppMember)
                .values(app_id=app_id, user_id=user_id, role=role)
                .on_conflict_do_update(index_elements=["app_id", "user_id"], set_={"role": role})
            )

    async def remove_member(self, app_id: UUID, user_id: UUID) -> None:
        async with self.db.begin() as s:
            done = await s.execute(
                delete(AppMember).where(AppMember.app_id == app_id, AppMember.user_id == user_id)
            )
            if done.rowcount != 1:
                raise NotFoundError("not a member of this app")

    # ---- keys ------------------------------------------------------------------------------------
    async def keys(self, app_id: UUID) -> list[AppKey]:
        async with self.db() as s:
            q = select(AppKey).where(AppKey.app_id == app_id).order_by(AppKey.created_at.desc())
            return list((await s.scalars(q)).all())

    async def create_key(self, actor: User, app_id: UUID, name: str) -> tuple[AppKey, str]:
        await self.get(app_id)
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        key = AppKey(
            id=uuid.uuid4(),
            app_id=app_id,
            name=name.strip() or "key",
            key_hash=_sha(raw),
            prefix=raw[:8],
            created_by=actor.id,
        )
        async with self.db.begin() as s:
            s.add(key)
        async with self.db() as s:
            return await s.get(AppKey, key.id), raw

    async def revoke_key(self, app_id: UUID, key_id: UUID) -> None:
        async with self.db.begin() as s:
            done = await s.execute(
                update(AppKey)
                .where(AppKey.id == key_id, AppKey.app_id == app_id, AppKey.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            if done.rowcount != 1:
                raise NotFoundError("key not found")

    async def resolve_key(self, raw: str) -> tuple[App, AppKey] | None:
        if not raw.startswith(KEY_PREFIX):
            return None
        async with self.db() as s:
            row = (await s.execute(select(AppKey, App).join(App).where(AppKey.key_hash == _sha(raw)))).first()
        if not row:
            return None
        key, app = row
        if key.revoked_at is not None or app.deleted_at is not None:
            return None
        if key.last_used_at is None or (datetime.now(UTC) - key.last_used_at).total_seconds() > 60:
            async with self.db.begin() as s:
                await s.execute(update(AppKey).where(AppKey.id == key.id).values(last_used_at=func.now()))
        return app, key

    # ---- limits ----------------------------------------------------------------------------------
    async def check_limits(self, app: App, device_id: str | None) -> None:
        now = datetime.now(UTC)
        async with self.db() as s:
            if app.daily_job_limit:
                n = await s.scalar(
                    select(func.count()).where(
                        Job.app_id == app.id,
                        Job.created_by.is_(None),
                        Job.created_at > now - timedelta(days=1),
                    )
                )
                if n >= app.daily_job_limit:
                    raise RateLimited("this app has reached its daily limit; try again later")
            if app.device_hourly_limit and device_id:
                n = await s.scalar(
                    select(func.count()).where(
                        Job.app_id == app.id,
                        Job.device_id == device_id,
                        Job.created_at > now - timedelta(hours=1),
                    )
                )
                if n >= app.device_hourly_limit:
                    raise RateLimited("too many requests from this device; try again later")

    async def usage(self, app_id: UUID) -> dict[str, int]:
        """Jobs from the app's clients (not console tests) in the last 24 h."""
        now = datetime.now(UTC)
        since = now - timedelta(days=1)
        async with self.db() as s:
            day = await s.scalar(
                select(func.count()).where(
                    Job.app_id == app_id, Job.created_by.is_(None), Job.created_at > since
                )
            )
            devices = await s.scalar(
                select(func.count(func.distinct(Job.device_id))).where(
                    Job.app_id == app_id, Job.created_by.is_(None), Job.created_at > since
                )
            )
        return {"jobs_24h": day or 0, "devices_24h": devices or 0}
