from functools import cached_property
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Providers
    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    fal_key: SecretStr | None = None
    fal_models_file: Path | None = None  # default: creative/providers/fal.yaml
    openrouter_api_key: SecretStr | None = None
    openrouter_models_file: Path | None = None  # default: creative/providers/openrouter.yaml
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    enable_fake_provider: bool = False
    default_image_provider: str | None = None
    default_video_provider: str | None = None

    # Storage
    data_dir: Path = Path("./data")
    database_url: SecretStr = SecretStr("postgresql://creative:creative@localhost:5432/creative")
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_command_timeout_s: float = 10

    # Worker
    worker_enabled: bool = True
    worker_concurrency: int = 2
    worker_poll_interval_s: float = 0.5
    worker_heartbeat_s: float = 15
    stale_job_after_s: float = 120
    job_max_attempts: int = 3
    retry_backoff_base_s: float = 5
    job_timeout_image_s: float = 180
    job_timeout_video_s: float = 900
    shutdown_grace_s: float = 30

    # Accounts
    setup_token: SecretStr | None = None
    session_idle_hours: float = 12
    session_max_age_hours: float = 168
    cookie_secure: bool = False
    password_min_length: int = 12
    login_max_failures: int = 10
    login_max_failures_per_ip: int = 30
    login_window_min: float = 15

    # End users of apps (creative/endusers): sessions and phone sign-in
    app_session_days: float = 90
    default_phone_country_code: str = "91"  # for 10-digit numbers sent without +<country>
    sms_provider: str = "log"  # log (codes go to the api log; dev only) | msg91
    otp_secret: SecretStr | None = None  # HMAC key for stored codes; random per process when unset
    otp_ttl_s: int = 300
    otp_resend_after_s: int = 30
    otp_max_attempts: int = 5
    otp_per_phone_per_hour: int = 5
    otp_per_device_per_hour: int = 10
    otp_per_ip_per_hour: int = 30
    # fixed codes for store reviewers, no SMS sent: "+919999999999:123456,+15555550100:000000"
    otp_test_numbers: str = ""
    # development only: every code is this 6-digit value (honoured only with SMS_PROVIDER=log)
    otp_dev_code: str = ""
    msg91_auth_key: SecretStr | None = None
    msg91_template_id: str | None = None  # a DLT-approved OTP template with an ##otp## variable
    msg91_otp_var: str = "otp"
    google_certs_url: str = "https://www.googleapis.com/oauth2/v1/certs"
    firebase_certs_url: str = (
        "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
    )
    # encrypts credentials entered in the console (e.g. an app's MSG91 auth key); any long random string
    secrets_key: SecretStr | None = None

    # Uploads
    input_image_max_bytes: int = 10 * 1024 * 1024
    input_image_max_pixels: int = 40_000_000
    input_image_max_side: int = 2048

    # Webhooks
    webhook_secret: SecretStr | None = None
    webhook_timeout_s: float = 10
    webhook_max_attempts: int = 3
    allow_private_webhooks: bool = False

    # Server
    log_prompts: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: str | None = None

    @cached_property
    def sqlalchemy_url(self) -> str:
        url = self.database_url.get_secret_value()
        for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix) :]
        return url

    @cached_property
    def asyncpg_dsn(self) -> str:
        return self.sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)
