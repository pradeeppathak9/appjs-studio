from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SetupState(BaseModel):
    needed: bool


class SetupRequest(BaseModel):
    setup_token: str = Field(max_length=200)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(max_length=256)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v


class SetupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_admin: bool

    model_config = {"from_attributes": True}


class AppUpdate(BaseModel):
    name: str | None = None
    phonepe_client_id: str | None = None
    phonepe_client_secret: str | None = None
    phonepe_merchant_id: str | None = None
    phonepe_environment: str | None = None
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_environment: str | None = None
    trial_enabled: bool | None = None
    trial_amount: int | None = None
    trial_period_days: int | None = None


class AppResponse(BaseModel):
    id: str
    name: str
    phonepe_enabled: bool
    razorpay_enabled: bool
    phonepe_client_id: str | None
    phonepe_client_secret: str | None
    phonepe_merchant_id: str | None
    phonepe_environment: str
    razorpay_key_id: str | None
    razorpay_key_secret: str | None
    razorpay_webhook_secret: str | None
    razorpay_environment: str
    api_key: str
    enabled: bool
    trial_enabled: bool
    trial_amount: int | None
    trial_period_days: int | None

    model_config = {"from_attributes": True}


# ── Admin ──────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = None
    is_admin: bool | None = None


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_admin: bool
    created_at: datetime
    apps_count: int = 0
    # The primary (first) admin, which cannot be demoted, renamed or deleted.
    # Reported by the server so the dashboard disables the control from the same
    # rule the API enforces.
    is_protected: bool = False

    model_config = {"from_attributes": True}


class AdminAppCreate(BaseModel):
    user_id: int
    name: str
    phonepe_enabled: bool = True
    razorpay_enabled: bool = False


class AdminAppUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    phonepe_enabled: bool | None = None
    razorpay_enabled: bool | None = None
    trial_enabled: bool | None = None
    trial_amount: int | None = None
    trial_period_days: int | None = None


class AdminAppResponse(BaseModel):
    id: str
    name: str
    owner_email: str | None
    phonepe_enabled: bool
    razorpay_enabled: bool
    phonepe_environment: str
    razorpay_environment: str
    enabled: bool
    trial_enabled: bool
    trial_amount: int | None
    trial_period_days: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAppGrantUser(BaseModel):
    user_id: int


class AdminUserAppResponse(BaseModel):
    """One app, as seen from a single user's access list."""
    app_id: str
    name: str
    phonepe_enabled: bool
    razorpay_enabled: bool
    enabled: bool
    granted: bool
    granted_at: datetime | None


class AppUserResponse(BaseModel):
    user_id: int
    email: str
    full_name: str | None
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Subscriptions ──────────────────────────────────────────

class SubscriptionResponse(BaseModel):
    id: str
    app_id: str
    phone_number: str
    amount: int
    max_amount: int | None
    amount_type: str
    frequency: str
    auth_workflow_type: str
    product_type: str
    state: str
    phonepe_subscription_id: str | None
    phonepe_order_id: str | None
    next_payment_date: int | None
    last_payment_status: str | None
    total_payments: int
    trail_days: int
    expire_at: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledTransactionResponse(BaseModel):
    id: str
    subscription_id: str
    payment_date: int
    amount: int
    state: str
    attempts: int
    created_at: datetime
    transaction_id: str | None = None
    merchant_order_id: str | None = None

    model_config = {"from_attributes": True}


class SubscriptionTransactionResponse(BaseModel):
    id: str
    subscription_id: str
    scheduled_transaction_id: str | None
    amount: int
    state: str
    payment_due_date: int | None
    transaction_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Razorpay Subscriptions ──────────────────────────────────

class RazorpaySubscriptionResponse(BaseModel):
    id: str
    app_id: str
    phone_number: str
    name: str
    email: str | None
    amount: int
    max_amount: int | None
    amount_type: str
    frequency: str
    method: str
    state: str
    razorpay_customer_id: str | None
    razorpay_order_id: str | None
    razorpay_token_id: str | None
    next_payment_date: int | None
    last_payment_status: str | None
    total_payments: int
    trail_days: int
    expire_at: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RazorpayTransactionResponse(BaseModel):
    id: str
    subscription_id: str
    amount: int
    state: str
    razorpay_order_id: str | None
    razorpay_payment_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Summary ────────────────────────────────────────────────

class SummaryPeriod(BaseModel):
    """One set of summary counters, over all time or over a single window."""
    subscriptions_total: int
    subscriptions_by_state: dict[str, int]
    scheduled_total: int
    scheduled_by_state: dict[str, int]
    # Face value of those scheduled payments, in paise. `scheduled_value_paise` is
    # every state; the by-state split lets the UI show just the upcoming ones.
    scheduled_value_paise: int = 0
    scheduled_value_by_state_paise: dict[str, int] = {}
    transactions_total: int
    transactions_by_state: dict[str, int]
    revenue_collected_paise: int
    payment_revenue_collected_paise: int
    trial_revenue_collected_paise: int
    trial_setups_count: int


class SummaryResponse(SummaryPeriod):
    # The window the counters cover, echoed back so the UI can label the panel.
    # Either bound may be null, meaning unbounded on that side (the "All" preset).
    window_start: date | None = None
    window_end: date | None = None


SetupResponse.model_rebuild()  # resolves the forward reference to UserResponse
