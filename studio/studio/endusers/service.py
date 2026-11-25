"""End users of an app (e.g. the people using Reelify): sign-in with Google or a phone code,
bearer sessions, profile and account deletion. Accounts belong to one app."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studio.config import Settings
from studio.db.tables import App, AppUser, AppUserSession, OtpChallenge
from studio.endusers.credits import apply_entry
from studio.endusers.firebase import FirebaseVerifier
from studio.endusers.google import GoogleVerifier
from studio.endusers.sms import SmsSender, app_sms_sender, sms_sender
from studio.errors import ForbiddenError, NotFoundError, RateLimitedError, ServiceError, ValidationFailed
from studio.secrets import SecretBox

log = logging.getLogger(__name__)

TOKEN_PREFIX = "cas_"
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class AccountBlocked(ForbiddenError):
    code = "account_blocked"


class SignInMethodDisabled(ForbiddenError):
    code = "sign_in_method_disabled"


class OtpInvalid(ServiceError):
    status, code = 400, "otp_invalid"


class OtpExpired(ServiceError):
    status, code = 400, "otp_expired"


@dataclass
class SignIn:
    token: str
    expires_at: datetime
    user: AppUser
    is_new: bool


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def normalize_phone(raw: str, default_cc: str) -> str:
    """E.164 (+<country><number>). A bare 10-digit number gets the default country code."""
    digits = re.sub(r"[\s\-().]", "", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]  # national trunk prefix
        if len(digits) == 10:
            digits = f"+{default_cc}{digits}"
        elif 11 <= len(digits) <= 15:
            digits = "+" + digits  # country code included, without the +
        else:
            raise ValidationFailed("enter a valid mobile number", "phone")
    if not PHONE_RE.match(digits):
        raise ValidationFailed("enter a valid mobile number", "phone")
    return digits


def guessable_code(code: str) -> bool:
    """True for codes someone would try first: one digit repeated, a run up or down (123456,
    987654, 890123), or a repeated 2- or 3-digit block (121212, 123123)."""
    d = [int(c) for c in code]
    steps = {(b - a) % 10 for a, b in zip(d, d[1:], strict=False)}
    return len(steps) == 1 and steps <= {0, 1, 9} or code[:2] * 3 == code or code[:3] * 2 == code


def parse_test_numbers(spec: str, default_cc: str) -> dict[tuple[str | None, str], str]:
    """`OTP_TEST_NUMBERS`: comma-separated `[app-slug/]phone:code`. Keys are (slug or None, E.164 phone);
    an entry without a slug works in every app. Entries with a guessable code are dropped (logged)."""
    out: dict[tuple[str | None, str], str] = {}
    for i, part in enumerate(filter(None, (p.strip() for p in spec.split(","))), 1):
        target, _, code = part.partition(":")
        slug, _, phone = target.rpartition("/")
        if not re.fullmatch(r"\d{6}", code):
            raise RuntimeError(f"OTP_TEST_NUMBERS: entry {i} needs a 6-digit code after ':'")
        if guessable_code(code):
            log.error("OTP_TEST_NUMBERS: entry %d is ignored: its code is too easy to guess", i)
            continue
        out[(slug.strip() or None, normalize_phone(phone, default_cc))] = code
    return out


class AppUserService:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        http: httpx.AsyncClient,
        sms: SmsSender | None = None,
        box: SecretBox | None = None,
    ):
        self.settings = settings
        self.db = sessions
        self.http = http
        self.google = GoogleVerifier(http, settings.google_certs_url)
        self.firebase = FirebaseVerifier(http, settings.firebase_certs_url)
        self.sms = sms or sms_sender(settings, http)
        self.box = box or SecretBox(settings.secrets_key)
        secret = settings.otp_secret.get_secret_value() if settings.otp_secret else None
        if not secret and settings.sms_provider != "log":
            log.warning("OTP_SECRET is not set: codes sent before a restart won't verify after it")
        self._otp_key = (secret or secrets.token_hex(32)).encode()
        self.test_numbers = parse_test_numbers(settings.otp_test_numbers, settings.default_phone_country_code)
        if self.test_numbers:
            log.info(
                "OTP_TEST_NUMBERS: %d fixed-code number(s); no SMS is sent to them", len(self.test_numbers)
            )
        # how long a real SMS send takes (moving average); fixed-code sends wait about as long, so the
        # response time doesn't tell which numbers are test numbers
        self._send_latency_s = 0.4
        self.dev_code: str | None = None
        if settings.otp_dev_code:
            if not re.fullmatch(r"\d{6}", settings.otp_dev_code):
                raise RuntimeError("OTP_DEV_CODE must be 6 digits")
            if settings.sms_provider == "log":
                self.dev_code = settings.otp_dev_code
                log.warning(
                    "OTP_DEV_CODE is set: every phone sign-in code is %s (development only)", self.dev_code
                )
            else:
                log.warning("OTP_DEV_CODE is ignored: it only works with SMS_PROVIDER=log")

    # ---- sessions ------------------------------------------------------------------------------
    async def _new_session(
        self, s: AsyncSession, user: AppUser, device_id: str | None
    ) -> tuple[str, datetime]:
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(days=self.settings.app_session_days)
        s.add(
            AppUserSession(
                id=_sha(raw), app_user_id=user.id, app_id=user.app_id, device_id=device_id, expires_at=expires
            )
        )
        return raw, expires

    async def resolve_session(self, app_id: UUID, token: str) -> AppUser | None:
        """The user behind a bearer token for this app, or None (unknown, expired, revoked, deleted,
        or a token from another app). Blocked users are returned; the caller refuses them."""
        if not token.startswith(TOKEN_PREFIX):
            return None
        now = datetime.now(UTC)
        async with self.db() as s:
            row = (
                await s.execute(
                    select(AppUserSession, AppUser)
                    .join(AppUser, AppUser.id == AppUserSession.app_user_id)
                    .where(AppUserSession.id == _sha(token))
                )
            ).first()
        if not row:
            return None
        sess, user = row
        if (
            sess.app_id != app_id
            or sess.revoked_at is not None
            or sess.expires_at <= now
            or user.deleted_at is not None
        ):
            return None
        if (now - sess.last_used_at).total_seconds() > 60:
            async with self.db.begin() as s:
                await s.execute(
                    update(AppUserSession)
                    .where(AppUserSession.id == sess.id)
                    .values(
                        last_used_at=func.now(),
                        expires_at=func.now() + timedelta(days=self.settings.app_session_days),
                    )
                )
                await s.execute(update(AppUser).where(AppUser.id == user.id).values(last_seen_at=func.now()))
        return user

    async def logout(self, token: str) -> None:
        async with self.db.begin() as s:
            await s.execute(
                update(AppUserSession)
                .where(AppUserSession.id == _sha(token), AppUserSession.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )

    # ---- accounts ------------------------------------------------------------------------------
    async def _upsert(
        self, s: AsyncSession, app: App, key: str, value: str, profile: dict
    ) -> tuple[AppUser, bool]:
        """Find the app's user by google_sub or phone, or create them (with the signup credits).
        Concurrent first sign-ins of the same person end up with one account."""
        column = getattr(AppUser, key)
        new_id = await s.scalar(
            insert(AppUser)
            .values(id=uuid.uuid4(), app_id=app.id, **{key: value}, **profile, last_seen_at=func.now())
            .on_conflict_do_nothing(index_elements=["app_id", key], index_where=text(f"{key} IS NOT NULL"))
            .returning(AppUser.id)
        )
        if new_id is not None:
            if app.signup_credits > 0:
                await apply_entry(
                    s,
                    app_id=app.id,
                    app_user_id=new_id,
                    delta=app.signup_credits,
                    reason="signup",
                    key=f"signup:{new_id}",
                )
            user = await s.get(AppUser, new_id, populate_existing=True)
            return user, True
        user = await s.scalar(
            select(AppUser).where(AppUser.app_id == app.id, column == value).with_for_update()
        )
        if user.status == "blocked":
            raise AccountBlocked("this account is blocked")
        changes = {k: v for k, v in profile.items() if v is not None and getattr(user, k) != v}
        changes["last_seen_at"] = func.now()
        await s.execute(update(AppUser).where(AppUser.id == user.id).values(**changes))
        return await s.get(AppUser, user.id, populate_existing=True), False

    async def sign_in_google(self, app: App, id_token: str, device_id: str | None) -> SignIn:
        if not app.auth_google_enabled:
            raise SignInMethodDisabled("Google sign-in is turned off for this app")
        claims = await self.google.verify(id_token, list(app.google_client_ids))
        profile = {
            "email": claims.get("email"),
            "name": claims.get("name"),
            "photo_url": claims.get("picture"),
        }
        async with self.db.begin() as s:
            user, is_new = await self._upsert(s, app, "google_sub", claims["sub"], profile)
            token, expires = await self._new_session(s, user, device_id)
        return SignIn(token, expires, user, is_new)

    async def sign_in_firebase(self, app: App, id_token: str, device_id: str | None) -> SignIn:
        """Phone sign-in verified by Firebase Auth on the device. Accounts are keyed by phone number,
        so a number that signed in by SMS code before lands on the same account."""
        if not app.auth_phone_enabled:
            raise SignInMethodDisabled("phone sign-in is turned off for this app")
        if app.phone_provider != "firebase":
            raise SignInMethodDisabled("this app's phone sign-in uses SMS codes (/v1/app/auth/otp/send)")
        claims = await self.firebase.verify_phone(id_token, app.firebase_project_id)
        phone = normalize_phone(claims["phone_number"], self.settings.default_phone_country_code)
        async with self.db.begin() as s:
            user, is_new = await self._upsert(s, app, "phone", phone, {})
            token, expires = await self._new_session(s, user, device_id)
        return SignIn(token, expires, user, is_new)

    # ---- phone codes -----------------------------------------------------------------------------
    def _hash_code(self, challenge_id: UUID, code: str) -> str:
        return hmac.new(self._otp_key, f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _check_sms_sign_in(app: App) -> None:
        if not app.auth_phone_enabled:
            raise SignInMethodDisabled("phone sign-in is turned off for this app")
        if app.phone_provider == "firebase":
            raise SignInMethodDisabled("this app's phone sign-in uses Firebase (/v1/app/auth/firebase)")

    def sms_for(self, app: App) -> SmsSender:
        return app_sms_sender(app, self.box, self.http, self.sms)

    def test_code(self, app: App, phone: str) -> str | None:
        return self.test_numbers.get((app.slug, phone)) or self.test_numbers.get((None, phone))

    async def send_otp(
        self, app: App, phone_raw: str, device_id: str | None, ip: str | None
    ) -> tuple[OtpChallenge, str]:
        self._check_sms_sign_in(app)
        phone = normalize_phone(phone_raw, self.settings.default_phone_country_code)
        st = self.settings
        now = datetime.now(UTC)
        hour = now - timedelta(hours=1)
        async with self.db() as s:
            last = await s.scalar(
                select(func.max(OtpChallenge.created_at)).where(
                    OtpChallenge.app_id == app.id, OtpChallenge.phone == phone
                )
            )
            if last and (now - last).total_seconds() < st.otp_resend_after_s:
                wait = st.otp_resend_after_s - int((now - last).total_seconds())
                raise RateLimitedError(
                    f"wait {wait}s before asking for another code", details=[{"retry_after_s": wait}]
                )

            async def count(*where) -> int:
                return await s.scalar(select(func.count()).where(OtpChallenge.created_at > hour, *where)) or 0

            if (
                await count(OtpChallenge.app_id == app.id, OtpChallenge.phone == phone)
                >= st.otp_per_phone_per_hour
            ):
                raise RateLimitedError("too many codes for this number; try again in an hour")
            if device_id and (
                await count(OtpChallenge.app_id == app.id, OtpChallenge.device_id == device_id)
                >= st.otp_per_device_per_hour
            ):
                raise RateLimitedError("too many codes from this device; try again in an hour")
            if ip and await count(OtpChallenge.ip == ip) >= st.otp_per_ip_per_hour:
                raise RateLimitedError("too many codes from this network; try again in an hour")

        test_code = self.test_code(app, phone)
        fixed = test_code or self.dev_code
        code = fixed or f"{secrets.randbelow(1_000_000):06d}"
        challenge = OtpChallenge(
            id=uuid.uuid4(),
            app_id=app.id,
            phone=phone,
            device_id=device_id,
            ip=ip,
            expires_at=now + timedelta(seconds=st.otp_ttl_s),
        )
        challenge.code_hash = self._hash_code(challenge.id, code)
        async with self.db.begin() as s:
            s.add(challenge)
        if not fixed:
            started = time.monotonic()
            await self.sms_for(app).send_otp(phone, code)
            self._send_latency_s = 0.8 * self._send_latency_s + 0.2 * (time.monotonic() - started)
        elif test_code:
            await asyncio.sleep(self._send_latency_s * (0.8 + 0.4 * secrets.randbelow(1000) / 1000))
        return challenge, phone

    async def verify_otp(self, app: App, challenge_id: UUID, code: str, device_id: str | None) -> SignIn:
        self._check_sms_sign_in(app)
        code = (code or "").strip()
        result: SignIn | None = None
        async with self.db.begin() as s:
            ch = await s.get(OtpChallenge, challenge_id, with_for_update=True)
            if ch is None or ch.app_id != app.id or ch.consumed_at is not None:
                raise OtpExpired("this code has expired; ask for a new one")
            if ch.expires_at <= datetime.now(UTC) or ch.attempts >= self.settings.otp_max_attempts:
                raise OtpExpired("this code has expired; ask for a new one")
            ch.attempts += 1  # committed even when the code is wrong
            left = self.settings.otp_max_attempts - ch.attempts
            ok = bool(re.fullmatch(r"\d{6}", code)) and hmac.compare_digest(
                self._hash_code(ch.id, code), ch.code_hash
            )
            if ok:
                ch.consumed_at = func.now()
                user, is_new = await self._upsert(s, app, "phone", ch.phone, {})
                token, expires = await self._new_session(s, user, device_id)
                result = SignIn(token, expires, user, is_new)
        if result is None:
            if left <= 0:
                raise OtpExpired("too many wrong codes; ask for a new one")
            raise OtpInvalid("that code didn't work", "code", details=[{"attempts_left": left}])
        return result

    # ---- the signed-in user ---------------------------------------------------------------------
    async def rename(self, user: AppUser, name: str | None) -> AppUser:
        async with self.db.begin() as s:
            await s.execute(
                update(AppUser).where(AppUser.id == user.id).values(name=(name or "").strip() or None)
            )
            return await s.get(AppUser, user.id, populate_existing=True)

    async def delete_account(self, user: AppUser) -> None:
        """Remove personal data and sign out everywhere. Jobs and the ledger stay (unlinked from a
        person) for accounting; the user's photos are removed with their jobs by retention, not here."""
        async with self.db.begin() as s:
            await s.execute(
                update(AppUser)
                .where(AppUser.id == user.id)
                .values(
                    deleted_at=func.now(),
                    google_sub=None,
                    phone=None,
                    email=None,
                    name=None,
                    photo_url=None,
                )
            )
            await s.execute(
                update(AppUserSession)
                .where(AppUserSession.app_user_id == user.id, AppUserSession.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )

    # ---- console ------------------------------------------------------------------------------------
    async def list(self, app_id: UUID, q: str | None = None, limit: int = 50) -> list[AppUser]:
        users, _ = await self.page(app_id, q, limit, 0)
        return users

    async def page(
        self, app_id: UUID, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[AppUser], int]:
        """One page of the app's users, newest first, and how many match in all. `q` matches name, email
        or phone (substring, any case), or a user id exactly."""
        where = [AppUser.app_id == app_id, AppUser.deleted_at.is_(None)]
        if q and q.strip():
            term = q.strip()
            like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            match = [AppUser.email.ilike(like), AppUser.phone.ilike(like), AppUser.name.ilike(like)]
            try:
                match.append(AppUser.id == UUID(term))
            except ValueError:
                pass
            where.append(or_(*match))
        query = (
            select(AppUser)
            .where(*where)
            .order_by(AppUser.created_at.desc(), AppUser.id)
            .limit(min(max(limit, 1), 200))
            .offset(max(offset, 0))
        )
        async with self.db() as s:
            total = await s.scalar(select(func.count()).select_from(AppUser).where(*where))
            return list((await s.scalars(query)).all()), total or 0

    async def get(self, app_id: UUID, user_id: UUID) -> AppUser:
        async with self.db() as s:
            user = await s.get(AppUser, user_id)
        if user is None or user.app_id != app_id or user.deleted_at is not None:
            raise NotFoundError("user not found")
        return user

    async def set_status(self, app_id: UUID, user_id: UUID, status: str) -> AppUser:
        await self.get(app_id, user_id)
        async with self.db.begin() as s:
            await s.execute(update(AppUser).where(AppUser.id == user_id).values(status=status))
            if status == "blocked":
                await s.execute(
                    update(AppUserSession)
                    .where(AppUserSession.app_user_id == user_id, AppUserSession.revoked_at.is_(None))
                    .values(revoked_at=func.now())
                )
        return await self.get(app_id, user_id)

    async def counts(self, app_id: UUID) -> dict[str, int]:
        async with self.db() as s:
            total = await s.scalar(
                select(func.count()).where(AppUser.app_id == app_id, AppUser.deleted_at.is_(None))
            )
        return {"users": total or 0}
