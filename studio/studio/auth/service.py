from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studio.auth.passwords import check_rules, hash_password, temporary_password, verify_password
from studio.config import Settings
from studio.db.tables import ApiToken, AppMember, LoginAttempt, Session, User
from studio.errors import ServiceError

SETUP_LOCK_ID = 7_360_112_002
TOKEN_PREFIX = "crt_"


class Role(IntEnum):
    """Global role. What a user may do inside an app comes from their membership (AppRole)."""

    user = 1
    admin = 3

    @classmethod
    def of(cls, user: User) -> Role:
        return cls[user.role]


class AppRole(IntEnum):
    """Role inside one app. Admins act as `admin` in every app."""

    tester = 1
    editor = 2
    admin = 3


class AuthError(ServiceError):
    status = 400
    code = "auth_error"


class InvalidCredentials(AuthError):
    status, code = 401, "invalid_credentials"


class Throttled(AuthError):
    status, code = 429, "too_many_attempts"


class SetupForbidden(AuthError):
    status, code = 403, "invalid_setup_token"


class AlreadySetUp(AuthError):
    status, code = 409, "already_set_up"


class NotAllowed(AuthError):
    status, code = 403, "not_allowed"


class NotFound(AuthError):
    status, code = 404, "not_found"


class Conflict(AuthError):
    status, code = 409, "conflict"


class Invalid(AuthError):
    status, code = 422, "validation_error"


@dataclass
class Principal:
    user: User
    via: str  # "session" | "token"
    session_id: str | None = None

    @property
    def role(self) -> Role:
        return Role.of(self.user)


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession]):
        self.settings = settings
        self.db = sessions
        self.setup_token: str | None = (
            settings.setup_token.get_secret_value() if settings.setup_token else None
        )

    # ---- setup ---------------------------------------------------------------------------------
    async def user_count(self) -> int:
        async with self.db() as s:
            return await s.scalar(select(func.count()).select_from(User)) or 0

    async def setup_needed(self) -> bool:
        return await self.user_count() == 0

    async def ensure_setup_token(self) -> str | None:
        """Generate a setup token for this process when none is configured and no users exist."""
        if self.setup_token is None and await self.setup_needed():
            self.setup_token = secrets.token_urlsafe(18)
        return self.setup_token if await self.setup_needed() else None

    async def setup(self, token: str, email: str, name: str, password: str) -> User:
        if not self.setup_token or not hmac.compare_digest(token.encode(), self.setup_token.encode()):
            raise SetupForbidden("the setup token is wrong")
        return await self.create_first_admin(email, name, password)

    async def create_first_admin(self, email: str, name: str, password: str, *, allow_existing=False) -> User:
        email = normalize_email(email)
        self._check_password(password, email)
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self.db.begin() as s:
            await s.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": SETUP_LOCK_ID})
            if not allow_existing and await s.scalar(select(func.count()).select_from(User)):
                raise AlreadySetUp("setup is already done")
            if await s.scalar(select(User.id).where(User.email == email)):
                raise Conflict("a user with this email exists", "email")
            user = User(id=uuid4(), email=email, name=name.strip(), role="admin", password_hash=password_hash)
            s.add(user)
        return user

    # ---- login / sessions ------------------------------------------------------------------------
    async def _throttled(self, s: AsyncSession, email: str, ip: str | None) -> bool:
        since = _now() - timedelta(minutes=self.settings.login_window_min)
        by_email = await s.scalar(
            select(func.count()).where(LoginAttempt.email == email, LoginAttempt.at > since, ~LoginAttempt.ok)
        )
        if by_email >= self.settings.login_max_failures:
            return True
        if ip:
            by_ip = await s.scalar(
                select(func.count()).where(LoginAttempt.ip == ip, LoginAttempt.at > since, ~LoginAttempt.ok)
            )
            return by_ip >= self.settings.login_max_failures_per_ip
        return False

    async def login(
        self, email: str, password: str, ip: str | None, user_agent: str | None
    ) -> tuple[User, str]:
        email = normalize_email(email)
        async with self.db() as s:
            if await self._throttled(s, email, ip):
                raise Throttled("too many failed sign-in attempts; try again later")
            user = await s.scalar(select(User).where(User.email == email))
        ok = await asyncio.to_thread(verify_password, user.password_hash if user else None, password)
        ok = ok and user is not None and user.is_active
        async with self.db.begin() as s:
            s.add(LoginAttempt(email=email, ip=ip, ok=ok))
            if not ok:
                raise_after = True
            else:
                raise_after = False
                await s.execute(update(User).where(User.id == user.id).values(last_login_at=func.now()))
        if raise_after:
            raise InvalidCredentials("wrong email or password")
        return user, await self.new_session(user.id, ip, user_agent)

    async def new_session(self, user_id: UUID, ip: str | None, user_agent: str | None) -> str:
        token = secrets.token_urlsafe(32)
        async with self.db.begin() as s:
            s.add(
                Session(
                    id=_sha(token),
                    user_id=user_id,
                    ip=ip,
                    user_agent=(user_agent or "")[:500],
                    expires_at=_now() + timedelta(hours=self.settings.session_max_age_hours),
                )
            )
        return token

    async def resolve_session(self, token: str) -> Principal | None:
        sid = _sha(token)
        async with self.db() as s:
            row = (await s.execute(select(Session, User).join(User).where(Session.id == sid))).first()
        if not row:
            return None
        sess, user = row
        now = _now()
        idle = timedelta(hours=self.settings.session_idle_hours)
        if not user.is_active or sess.expires_at <= now or sess.last_seen_at + idle <= now:
            await self.end_session(token)
            return None
        if (now - sess.last_seen_at).total_seconds() > 60:
            async with self.db.begin() as s:
                await s.execute(update(Session).where(Session.id == sid).values(last_seen_at=func.now()))
        return Principal(user, "session", sid)

    async def end_session(self, token: str) -> None:
        async with self.db.begin() as s:
            await s.execute(Session.__table__.delete().where(Session.id == _sha(token)))

    async def end_user_sessions(self, s: AsyncSession, user_id: UUID, keep: str | None = None) -> None:
        q = Session.__table__.delete().where(Session.user_id == user_id)
        if keep:
            q = q.where(Session.id != keep)
        await s.execute(q)

    # ---- API tokens -----------------------------------------------------------------------------
    async def resolve_api_token(self, token: str) -> Principal | None:
        if not token.startswith(TOKEN_PREFIX):
            return None
        async with self.db() as s:
            row = (
                await s.execute(select(ApiToken, User).join(User).where(ApiToken.token_hash == _sha(token)))
            ).first()
        if not row:
            return None
        tok, user = row
        if tok.revoked_at is not None or not user.is_active:
            return None
        if tok.last_used_at is None or (_now() - tok.last_used_at).total_seconds() > 60:
            async with self.db.begin() as s:
                await s.execute(update(ApiToken).where(ApiToken.id == tok.id).values(last_used_at=func.now()))
        return Principal(user, "token")

    async def create_token(self, user_id: UUID, name: str) -> tuple[ApiToken, str]:
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        tok = ApiToken(
            id=uuid4(),
            user_id=user_id,
            name=name.strip()[:200] or "token",
            token_hash=_sha(raw),
            prefix=raw[:8],
        )
        async with self.db.begin() as s:
            s.add(tok)
        async with self.db() as s:
            tok = await s.get(ApiToken, tok.id)
        return tok, raw

    async def list_tokens(self, user_id: UUID) -> list[ApiToken]:
        async with self.db() as s:
            q = select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc())
            return list((await s.scalars(q)).all())

    async def revoke_token(self, user_id: UUID, token_id: UUID) -> None:
        async with self.db.begin() as s:
            done = await s.execute(
                update(ApiToken)
                .where(ApiToken.id == token_id, ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            if done.rowcount != 1:
                raise NotFound("token not found")

    # ---- own account ----------------------------------------------------------------------------
    def _check_password(self, password: str, email: str) -> None:
        try:
            check_rules(password, email=email, min_length=self.settings.password_min_length)
        except ValueError as e:
            raise Invalid(str(e), "password") from e

    async def change_password(self, p: Principal, current: str, new: str) -> None:
        if not await asyncio.to_thread(verify_password, p.user.password_hash, current):
            raise InvalidCredentials("the current password is wrong", "current_password")
        if current == new:
            raise Invalid("the new password must differ from the current one", "new_password")
        self._check_password(new, p.user.email)
        new_hash = await asyncio.to_thread(hash_password, new)
        async with self.db.begin() as s:
            await s.execute(
                update(User)
                .where(User.id == p.user.id)
                .values(password_hash=new_hash, must_change_password=False, updated_at=func.now())
            )
            await self.end_user_sessions(s, p.user.id, keep=p.session_id)

    async def rename(self, user_id: UUID, name: str) -> None:
        async with self.db.begin() as s:
            await s.execute(
                update(User).where(User.id == user_id).values(name=name.strip(), updated_at=func.now())
            )

    # ---- user management (admin) -------------------------------------------------------------------
    async def list_users(self) -> list[tuple[User, int]]:
        async with self.db() as s:
            counts = (
                select(ApiToken.user_id, func.count().label("n"))
                .where(ApiToken.revoked_at.is_(None))
                .group_by(ApiToken.user_id)
                .subquery()
            )
            rows = await s.execute(
                select(User, func.coalesce(counts.c.n, 0))
                .outerjoin(counts, counts.c.user_id == User.id)
                .where(User.deleted_at.is_(None))
                .order_by(User.created_at)
            )
            return [(u, n) for u, n in rows]

    async def get_user(self, user_id: UUID) -> User:
        async with self.db() as s:
            user = await s.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFound("user not found")
        return user

    async def create_user(self, actor: User, email: str, name: str, role: str) -> tuple[User, str]:
        email = normalize_email(email)
        if role not in ("user", "admin"):
            raise Invalid("role must be user or admin", "role")
        password = temporary_password()
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self.db.begin() as s:
            if await s.scalar(select(User.id).where(User.email == email)):
                raise Conflict("a user with this email exists", "email")
            user = User(
                id=uuid4(),
                email=email,
                name=name.strip(),
                role=role,
                password_hash=password_hash,
                must_change_password=True,
                created_by=actor.id,
            )
            s.add(user)
        return await self.get_user(user.id), password

    async def _active_admins(self, s: AsyncSession) -> int:
        return await s.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
        )

    async def update_user(
        self, actor: User, user_id: UUID, *, name: str | None, role: str | None, is_active: bool | None
    ) -> User:
        async with self.db.begin() as s:
            await s.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": SETUP_LOCK_ID})
            user = await s.get(User, user_id, with_for_update=True)
            if user is None or user.deleted_at is not None:
                raise NotFound("user not found")
            demote = role is not None and role != "admin" and user.role == "admin"
            deactivate = is_active is False and user.is_active
            if user.id == actor.id and (demote or deactivate):
                raise NotAllowed("you can't demote or deactivate yourself")
            if (demote or (deactivate and user.role == "admin")) and await self._active_admins(s) <= 1:
                raise NotAllowed("the last active admin can't be removed")
            if role is not None and role not in ("admin", "user"):
                raise Invalid("unknown role", "role")
            changed_access = (role is not None and role != user.role) or deactivate
            if name is not None:
                user.name = name.strip()
            if role is not None:
                user.role = role
            if is_active is not None:
                user.is_active = is_active
            user.updated_at = _now()
            if changed_access:
                await self.end_user_sessions(s, user.id)
            if deactivate:
                await s.execute(
                    update(ApiToken)
                    .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
                    .values(revoked_at=func.now())
                )
        return await self.get_user(user_id)

    async def delete_user(self, actor: User, user_id: UUID) -> None:
        """Remove a user for good: they can't sign in, their sessions and tokens end, and their email
        is free again. The row stays (renamed out of the way) so jobs and template versions keep
        their author's name."""
        async with self.db.begin() as s:
            await s.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": SETUP_LOCK_ID})
            user = await s.get(User, user_id, with_for_update=True)
            if user is None or user.deleted_at is not None:
                raise NotFound("user not found")
            if user.id == actor.id:
                raise NotAllowed("you can't delete yourself")
            if user.role == "admin" and user.is_active and await self._active_admins(s) <= 1:
                raise NotAllowed("the last active admin can't be removed")
            user.deleted_at = _now()
            user.is_active = False
            user.email = f"deleted+{user.id}@users.invalid"
            user.password_hash = ""
            user.must_change_password = False
            user.updated_at = _now()
            await self.end_user_sessions(s, user.id)
            await s.execute(
                update(ApiToken)
                .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            await s.execute(AppMember.__table__.delete().where(AppMember.user_id == user.id))

    async def reset_password(self, user_id: UUID) -> str:
        password = temporary_password()
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self.db.begin() as s:
            done = await s.execute(
                update(User)
                .where(User.id == user_id, User.deleted_at.is_(None))
                .values(password_hash=password_hash, must_change_password=True, updated_at=func.now())
            )
            if done.rowcount != 1:
                raise NotFound("user not found")
            await self.end_user_sessions(s, user_id)
        return password

    async def set_password(self, email: str, password: str) -> None:
        """Shell recovery (`studio users reset-password`)."""
        email = normalize_email(email)
        self._check_password(password, email)
        password_hash = await asyncio.to_thread(hash_password, password)
        async with self.db.begin() as s:
            user = await s.scalar(select(User).where(User.email == email))
            if user is None:
                raise NotFound("no user with this email")
            user.password_hash = password_hash
            user.must_change_password = False
            user.is_active = True
            await self.end_user_sessions(s, user.id)
