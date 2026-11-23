"""SQLAlchemy table models. Alembic migrations in migrations/versions must match these
(tests/test_migrations.py runs `alembic check`)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _ts(nullable: bool = False, default_now: bool = False) -> Mapped:
    return mapped_column(
        DateTime(timezone=True), nullable=nullable, server_default=func.now() if default_now else None
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="status"),
        Index("ix_jobs_queued", "created_at", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs_running_heartbeat", "heartbeat_at", postgresql_where=text("status = 'running'")),
        Index("ix_jobs_created_at", text("created_at DESC")),
        Index("ix_jobs_created_by", "created_by", text("created_at DESC")),
        Index("ix_jobs_template", "template_id", text("created_at DESC")),
        Index("ix_jobs_app", "app_id", text("created_at DESC")),
        Index("ix_jobs_app_device", "app_id", "device_id", text("created_at DESC")),
        Index("ix_jobs_app_user", "app_user_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    media_type: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(256))
    request: Mapped[dict] = mapped_column(JSONB)
    webhook_url: Mapped[str | None] = mapped_column(Text)
    webhook_status: Mapped[str | None] = mapped_column(String(16))
    webhook_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime] = _ts(default_now=True)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    heartbeat_at: Mapped[datetime | None] = _ts(nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    template_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("templates.id"))
    template_version: Mapped[int | None] = mapped_column(Integer)
    app_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id"))
    device_id: Mapped[str | None] = mapped_column(String(128))
    # the signed-in end user of the app who ran it, and what it cost them (refunded if it fails)
    app_user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("app_users.id"))
    credits_charged: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)
    started_at: Mapped[datetime | None] = _ts(nullable=True)
    finished_at: Mapped[datetime | None] = _ts(nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("job_id", "idx"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _ts(default_now=True)


class JobInput(Base):
    __tablename__ = "job_inputs"
    __table_args__ = (UniqueConstraint("job_id", "slot"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    slot: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _ts(default_now=True)


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(256))
    started_at: Mapped[datetime] = _ts(default_now=True)
    heartbeat_at: Mapped[datetime] = _ts(default_now=True)
    inflight: Mapped[int] = mapped_column(Integer, server_default="0")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin','user')", name="role"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)
    last_login_at: Mapped[datetime | None] = _ts(nullable=True)
    deleted_at: Mapped[datetime | None] = _ts(nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = _ts(default_now=True)
    last_seen_at: Mapped[datetime] = _ts(default_now=True)
    expires_at: Mapped[datetime] = _ts()
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _ts(default_now=True)
    last_used_at: Mapped[datetime | None] = _ts(nullable=True)
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_email_at", "email", "at"),
        Index("ix_login_attempts_ip_at", "ip", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320))
    ip: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = _ts(default_now=True)
    ok: Mapped[bool] = mapped_column(Boolean)


class Template(Base):
    """A template belongs to one app; its slug is unique within that app."""

    __tablename__ = "templates"
    __table_args__ = (
        CheckConstraint("status IN ('draft','active')", name="status"),
        CheckConstraint("credit_cost >= 0", name="credit_cost"),
        UniqueConstraint("app_id", "slug"),
        Index("ix_templates_app_position", "app_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id"))
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    deleted_at: Mapped[datetime | None] = _ts(nullable=True)
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(String(16))
    current_version: Mapped[int] = mapped_column(Integer)
    # credits a signed-in app user pays per run; pricing, so not part of the versioned content
    credit_cost: Mapped[int] = mapped_column(Integer, server_default="1")
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (PrimaryKeyConstraint("template_id", "version"),)

    template_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    media_type: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(256))
    allowed_models: Mapped[list[str]] = mapped_column(ARRAY(String(256)), server_default="{}")
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB)
    inputs: Mapped[list] = mapped_column(JSONB)
    variables: Mapped[list] = mapped_column(JSONB)
    reference_uploads: Mapped[list[UUID]] = mapped_column(ARRAY(PgUUID(as_uuid=True)), server_default="{}")
    cover_upload: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("uploads.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)


class TemplateEvent(Base):
    __tablename__ = "template_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    at: Mapped[datetime] = _ts(default_now=True)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    app_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id"))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)


class App(Base):
    """A client application (e.g. an Android app): the workspace that owns templates. Users reach it
    through `app_members` (editor or tester); admins reach every app."""

    __tablename__ = "apps"
    __table_args__ = (
        CheckConstraint("status IN ('active','disabled')", name="status"),
        CheckConstraint("payment_provider IN ('none','razorpay','phonepe')", name="payment_provider"),
        CheckConstraint("payment_mode IN ('test','live')", name="payment_mode"),
        CheckConstraint("phone_provider IN ('msg91','firebase')", name="phone_provider"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    platform: Mapped[str] = mapped_column(String(32), server_default="android")
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    daily_job_limit: Mapped[int | None] = mapped_column(Integer)
    device_hourly_limit: Mapped[int | None] = mapped_column(Integer)
    # end-user sign-in (see creative/endusers)
    auth_google_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    auth_phone_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    google_client_ids: Mapped[list[str]] = mapped_column(ARRAY(String(256)), server_default="{}")
    # phone sign-in: msg91 = our server texts the code (the app's own MSG91 account when set, else the
    # server's); firebase = the app verifies the number with Firebase Auth and sends us its ID token
    phone_provider: Mapped[str] = mapped_column(String(16), server_default="msg91")
    msg91_template_id: Mapped[str | None] = mapped_column(String(64))
    msg91_otp_var: Mapped[str | None] = mapped_column(String(32))
    msg91_auth_key_enc: Mapped[str | None] = mapped_column(Text)  # Fernet, see creative/secrets.py
    firebase_project_id: Mapped[str | None] = mapped_column(String(64))
    signup_credits: Mapped[int] = mapped_column(Integer, server_default="0")
    require_login: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # payments: which gateway the app's purchases go through, and its public identifiers. Secret
    # keys are added with the checkout integration, not stored before anything uses them.
    payment_provider: Mapped[str] = mapped_column(String(16), server_default="none")
    payment_mode: Mapped[str] = mapped_column(String(8), server_default="test")
    razorpay_key_id: Mapped[str | None] = mapped_column(String(64))
    phonepe_merchant_id: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)
    deleted_at: Mapped[datetime | None] = _ts(nullable=True)


class AppMember(Base):
    __tablename__ = "app_members"
    __table_args__ = (
        PrimaryKeyConstraint("app_id", "user_id"),
        CheckConstraint("role IN ('editor','tester')", name="role"),
    )

    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _ts(default_now=True)


class AppKey(Base):
    __tablename__ = "app_keys"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    last_used_at: Mapped[datetime | None] = _ts(nullable=True)
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)


# ---- end users of an app (e.g. Reelify's users), their credits and subscriptions ----------------------


class AppUser(Base):
    """Someone signed in to one app's client. Accounts are per app: the same Google account or phone
    number in two apps is two users."""

    __tablename__ = "app_users"
    __table_args__ = (
        CheckConstraint("status IN ('active','blocked')", name="status"),
        CheckConstraint("credits >= 0", name="credits"),
        Index(
            "uq_app_users_app_google",
            "app_id",
            "google_sub",
            unique=True,
            postgresql_where=text("google_sub IS NOT NULL"),
        ),
        Index(
            "uq_app_users_app_phone",
            "app_id",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        Index("ix_app_users_app_created", "app_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    google_sub: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))  # E.164
    name: Mapped[str | None] = mapped_column(String(200))
    photo_url: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[int] = mapped_column(Integer, server_default="0")  # cache of sum(credit_ledger.delta)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    created_at: Mapped[datetime] = _ts(default_now=True)
    last_seen_at: Mapped[datetime | None] = _ts(nullable=True)
    deleted_at: Mapped[datetime | None] = _ts(nullable=True)


class AppUserSession(Base):
    __tablename__ = "app_user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the bearer token
    app_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    device_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = _ts(default_now=True)
    last_used_at: Mapped[datetime] = _ts(default_now=True)
    expires_at: Mapped[datetime] = _ts()
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_challenges_phone", "app_id", "phone", text("created_at DESC")),
        Index("ix_otp_challenges_device", "app_id", "device_id", text("created_at DESC")),
        Index("ix_otp_challenges_ip", "ip", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    phone: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    device_id: Mapped[str | None] = mapped_column(String(128))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _ts(default_now=True)
    expires_at: Mapped[datetime] = _ts()
    consumed_at: Mapped[datetime | None] = _ts(nullable=True)


class Plan(Base):
    """A subscription plan of an app. Prices are informational until a payment provider is wired in."""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="status"),
        CheckConstraint("billing_period IN ('month','year')", name="billing_period"),
        CheckConstraint("credits_per_month >= 0 AND price_minor >= 0", name="amounts"),
        UniqueConstraint("app_id", "slug"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    price_minor: Mapped[int] = mapped_column(Integer)  # e.g. paise
    currency: Mapped[str] = mapped_column(String(3), server_default="INR")
    billing_period: Mapped[str] = mapped_column(String(8))
    credits_per_month: Mapped[int] = mapped_column(Integer)
    badge: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    external_ids: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('active','cancelled','expired')", name="status"),
        Index("ix_subscriptions_user", "app_user_id", text("created_at DESC")),
        Index("ix_subscriptions_due", "next_credit_grant_at", postgresql_where=text("status = 'active'")),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE")
    )
    plan_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))  # manual | razorpay | ...
    provider_ref: Mapped[str | None] = mapped_column(String(255))
    current_period_start: Mapped[datetime] = _ts()
    current_period_end: Mapped[datetime] = _ts()
    next_credit_grant_at: Mapped[datetime | None] = _ts(nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class CreditEntry(Base):
    """Every change to an app user's credits. `app_users.credits` is kept equal to the sum, in the
    same transaction. `idempotency_key` makes grants, charges and refunds happen at most once."""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('signup','subscription_grant','generation','refund','admin_adjust')", name="reason"
        ),
        Index("ix_credit_ledger_user", "app_user_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    app_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"))
    app_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE")
    )
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = _ts(default_now=True)
