from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, model_validator

from creative.templates.models import InputSlot, TemplateParams, Variable

# ---- errors -------------------------------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---- generations --------------------------------------------------------------------------------


class GenerationCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    media_type: Literal["image", "video"] = "image"
    provider: str | None = None
    model: str | None = None
    aspect_ratio: str = "1:1"
    n: int = Field(1, ge=1, le=8)
    duration_seconds: int | None = Field(None, ge=1, le=60)
    negative_prompt: str | None = Field(None, max_length=2000)
    seed: int | None = None
    webhook_url: HttpUrl | None = None


class AssetOut(BaseModel):
    id: UUID
    url: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_seconds: float | None


class InputOut(BaseModel):
    id: UUID
    slot: str
    role: str
    url: str
    mime_type: str
    width: int
    height: int


class JobTemplateRef(BaseModel):
    id: UUID
    slug: str
    title: str
    version: int | None


class JobError(BaseModel):
    code: str
    message: str | None


class WebhookState(BaseModel):
    url: str
    status: str | None
    attempts: int


class UserRef(BaseModel):
    id: UUID
    name: str


class JobAppRef(BaseModel):
    id: UUID
    slug: str
    name: str
    device_id: str | None = None


class JobResponse(BaseModel):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    media_type: str
    provider: str
    model: str
    request: dict[str, Any]
    template: JobTemplateRef | None
    inputs: list[InputOut]
    assets: list[AssetOut]
    error: JobError | None
    attempt: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    webhook: WebhookState | None
    created_by: UserRef | None
    app: JobAppRef | None = None


class AppRunResponse(JobResponse):
    """POST /v1/app/templates/{slug}/generations: the queued job, plus the user's balance after the charge
    (null without a signed-in user) so the app can show it at once."""

    credits: int | None = None


class JobList(BaseModel):
    items: list[JobResponse]


# ---- meta ---------------------------------------------------------------------------------------


class ProviderInfo(BaseModel):
    name: str
    image: bool
    video: bool
    default_image_model: str | None
    default_video_model: str | None
    known_image_models: list[str]
    known_video_models: list[str]
    max_images: int
    image_aspect_ratios: list[str]
    video_aspect_ratios: list[str]
    video_durations: list[int]
    supports_negative_prompt: bool
    supports_seed: bool
    image_input: bool
    image_input_models: list[str]
    max_input_images: int


class WorkerInfo(BaseModel):
    id: str
    hostname: str
    heartbeat_at: datetime
    inflight: int
    fresh: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok"]
    workers: list[WorkerInfo]
    jobs: dict[str, int]


# ---- auth ---------------------------------------------------------------------------------------

Role = Literal["admin", "user"]
AppRoleName = Literal["admin", "editor", "tester"]


class SetupState(BaseModel):
    needed: bool


class SetupIn(BaseModel):
    setup_token: str
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class MeResponse(BaseModel):
    id: UUID
    email: str
    name: str
    role: Role
    must_change_password: bool


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class NameChange(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: Role
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    active_tokens: int = 0


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: Role = "user"


class UserCreated(BaseModel):
    user: UserOut
    temporary_password: str


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None


class TemporaryPassword(BaseModel):
    temporary_password: str


# ---- templates ----------------------------------------------------------------------------------


class TemplatePublic(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str
    media_type: str
    version: int
    inputs: list[InputSlot]
    variables: list[Variable]
    model: str
    allowed_models: list[str]
    has_reference_images: bool
    cover_url: str | None = None
    credit_cost: int = Field(description="credits a signed-in user pays per run")


class TemplateVersionOut(BaseModel):
    version: int
    title: str
    description: str
    media_type: str
    provider: str
    model: str
    allowed_models: list[str]
    prompt: str
    negative_prompt: str | None
    params: TemplateParams
    inputs: list[InputSlot]
    variables: list[Variable]
    reference_uploads: list[UUID]
    cover_upload: UUID | None = None
    note: str | None
    created_by: UserRef
    created_at: datetime


class TemplateFull(BaseModel):
    id: UUID
    app_id: UUID
    slug: str
    title: str
    description: str
    status: Literal["draft", "active"]
    position: int
    current_version: int
    credit_cost: int
    cover_url: str | None = None
    created_at: datetime
    updated_at: datetime
    current: TemplateVersionOut
    versions: list[TemplateVersionOut] | None = None


class TemplateSaved(BaseModel):
    template: TemplateFull
    warnings: list[str]


class TemplateStatusIn(BaseModel):
    status: Literal["draft", "active"]


class TemplateOrderIn(BaseModel):
    template_ids: list[UUID] = Field(max_length=500)


class TemplateCopyIn(BaseModel):
    target_app_id: UUID
    slug: str | None = None


class UploadOut(BaseModel):
    id: UUID
    url: str
    mime_type: str
    width: int
    height: int


# ---- apps -----------------------------------------------------------------------------------------


class AppOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    platform: str
    status: Literal["active", "disabled"]
    daily_job_limit: int | None
    device_hourly_limit: int | None
    auth_google_enabled: bool
    auth_phone_enabled: bool
    google_client_ids: list[str]
    phone_provider: Literal["msg91", "firebase"]
    msg91_template_id: str | None
    msg91_otp_var: str | None
    msg91_auth_key_set: bool = Field(description="an MSG91 auth key is saved (the key itself is write-only)")
    firebase_project_id: str | None
    secrets_key_set: bool = Field(
        False, description="app detail only: the server can store credentials (SECRETS_KEY is set)"
    )
    signup_credits: int
    require_login: bool
    payment_provider: Literal["none", "razorpay", "phonepe"]
    payment_mode: Literal["test", "live"]
    razorpay_key_id: str | None
    phonepe_merchant_id: str | None
    created_at: datetime
    updated_at: datetime
    template_count: int = 0
    active_template_count: int = 0
    active_key_count: int = 0
    member_count: int = 0


class AppDetail(AppOut):
    usage: dict[str, int]


class MyApp(AppOut):
    """An app as its member sees it, with their role in it."""

    role: AppRoleName


class MemberOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: Literal["editor", "tester"]
    is_active: bool


class MemberIn(BaseModel):
    role: Literal["editor", "tester"]


class Membership(BaseModel):
    app_id: UUID
    app_slug: str
    app_name: str
    role: Literal["editor", "tester"]


class AppKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AppKeyOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class AppKeyCreated(AppKeyOut):
    key: str


class AppInfo(BaseModel):
    """What an app learns about itself."""

    slug: str
    name: str
    description: str
    platform: str


class AppCatalog(BaseModel):
    app: AppInfo
    templates: list[TemplatePublic]


# ---- end users of an app: sign-in, profile, credits, plans ---------------------------------------


class SignInMethods(BaseModel):
    google: bool
    phone: bool
    google_client_id: str | None = Field(
        None, description="the OAuth Web client id to request Google ID tokens for (Credential Manager)"
    )
    phone_provider: Literal["msg91", "firebase"] | None = Field(
        None,
        description="with phone on: msg91 = /auth/otp/send + /auth/otp/verify (our server texts the code); "
        "firebase = verify the number with Firebase Auth on the device, then POST /auth/firebase",
    )
    firebase_project_id: str | None = Field(
        None,
        description="with phone_provider firebase: the Firebase project of the app's google-services.json",
    )


class PaymentConfig(BaseModel):
    provider: Literal["none", "razorpay", "phonepe"] = Field(
        description="the gateway purchases go through; none = payments not available yet"
    )
    mode: Literal["test", "live"]
    razorpay_key_id: str | None = Field(None, description="for Razorpay Checkout on the device")


class AppClientConfig(BaseModel):
    """What the app needs before sign-in: which sign-in buttons to show, whether sign-in is
    required to list templates, and the payment gateway."""

    app: AppInfo
    sign_in: SignInMethods
    require_login: bool
    payments: PaymentConfig


class GoogleSignInIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=8000)


class FirebaseSignInIn(BaseModel):
    id_token: str = Field(
        min_length=20, max_length=8000, description="FirebaseUser.getIdToken() after phone sign-in"
    )


class OtpSendIn(BaseModel):
    phone: str = Field(min_length=6, max_length=24, description="+<country><number>, or 10 digits")


class OtpSendOut(BaseModel):
    challenge_id: UUID
    phone: str = Field(description="the number the code was sent to, in E.164")
    expires_in_s: int
    resend_after_s: int


class OtpVerifyIn(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=1, max_length=12)


class PlanRef(BaseModel):
    id: UUID
    slug: str
    name: str


class SubscriptionOut(BaseModel):
    id: UUID
    plan: PlanRef
    status: Literal["active", "cancelled", "expired"]
    provider: str
    current_period_start: datetime
    current_period_end: datetime
    next_credit_grant_at: datetime | None
    created_at: datetime


class AppUserOut(BaseModel):
    id: UUID
    name: str | None
    email: str | None
    phone: str | None
    photo_url: str | None
    sign_in: Literal["google", "phone"]
    credits: int
    subscription: SubscriptionOut | None = None
    created_at: datetime


class SignInOut(BaseModel):
    token: str = Field(description="send as `Authorization: Bearer <token>`; keep it in secure storage")
    expires_at: datetime = Field(description="sliding: extended each day the token is used")
    is_new: bool
    user: AppUserOut


class MeUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)


class CreditEntryOut(BaseModel):
    id: UUID
    delta: int
    reason: Literal["signup", "subscription_grant", "generation", "refund", "admin_adjust"]
    note: str | None
    job_id: UUID | None
    created_at: datetime


class PlanOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    price_minor: int = Field(description="in the currency's minor unit, e.g. 19900 = Rs 199.00")
    currency: str
    billing_period: Literal["month", "year"]
    credits_per_month: int
    badge: str | None


class PlanAdminOut(PlanOut):
    status: Literal["active", "archived"]
    position: int
    created_at: datetime
    updated_at: datetime


class PlanOrderIn(BaseModel):
    plan_ids: list[UUID] = Field(max_length=100)


class AppUserAdminOut(AppUserOut):
    status: Literal["active", "blocked"]
    last_seen_at: datetime | None


class SubscriptionAdminOut(SubscriptionOut):
    """A subscription as admins see it: also the payment-gateway subscription it is linked to."""

    provider_ref: str | None = Field(
        None, description="the gateway's subscription id (Razorpay `sub_…`, PhonePe subscription id)"
    )
    cancel_at_period_end: bool = False


class AppUserDetail(AppUserAdminOut):
    subscriptions: list[SubscriptionAdminOut]
    ledger: list[CreditEntryOut]


class AppUserPage(BaseModel):
    items: list[AppUserAdminOut]
    total: int = Field(description="users matching the search, across all pages")
    limit: int
    offset: int


class CreditEntryPage(BaseModel):
    items: list[CreditEntryOut]
    total: int
    limit: int
    offset: int


# Razorpay subscription ids look like sub_00000000000001; PhonePe's are merchant-chosen ids.
PROVIDER_REF_PATTERNS = {"razorpay": r"^sub_[A-Za-z0-9]{6,40}$", "phonepe": r"^[A-Za-z0-9_.:-]{1,64}$"}


class SubscriptionLinkIn(BaseModel):
    provider: Literal["manual", "razorpay", "phonepe"]
    provider_ref: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _ref_fits_provider(self) -> SubscriptionLinkIn:
        ref = (self.provider_ref or "").strip() or None
        if self.provider == "manual":
            self.provider_ref = None
            return self
        if ref is None:
            raise ValueError(f"enter the {self.provider} subscription id")
        if not re.match(PROVIDER_REF_PATTERNS[self.provider], ref):
            example = "sub_Abc123XYZ" if self.provider == "razorpay" else "letters, digits, _ . : - (max 64)"
            raise ValueError(f"that doesn't look like a {self.provider} subscription id ({example})")
        self.provider_ref = ref
        return self


class AppUserStatusIn(BaseModel):
    status: Literal["active", "blocked"]


class CreditAdjustIn(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000, description="credits to add (negative: remove)")
    note: str = Field(min_length=1, max_length=500)


class CreditBalance(BaseModel):
    credits: int


class SubscriptionGrantIn(BaseModel):
    plan_id: UUID
