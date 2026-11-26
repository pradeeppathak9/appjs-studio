from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Providers
    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    fal_key: SecretStr | None = None
    fal_models_file: Path | None = None  # default: studio/providers/fal.yaml
    openrouter_api_key: SecretStr | None = None
    openrouter_models_file: Path | None = None  # default: studio/providers/openrouter.yaml
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    enable_fake_provider: bool = False
    default_image_provider: str | None = None
    default_video_provider: str | None = None

    # Storage
    data_dir: Path = Path("./data")  # the local store; with ASSET_STORE=s3 only tmp/ is used
    # Where generated assets, input photos and creator uploads live: local (DATA_DIR) | s3 (any
    # S3-compatible bucket, e.g. Cloudflare R2). docs/STORAGE.md has the setup.
    asset_store: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # R2: https://<account id>.r2.cloudflarestorage.com; unset = AWS
    s3_region: str = "auto"  # R2 takes "auto"; AWS needs the bucket's region, e.g. ap-south-1
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    # files are served by redirect to a presigned URL valid this long ...
    s3_url_expiry_s: int = 3600
    # ... or, when set, to <base>/<key> for assets/ and uploads/ (a public custom domain or CDN in
    # front of the bucket). Input photos always get presigned URLs.
    s3_public_base_url: str | None = None
    database_url: SecretStr = SecretStr("postgresql://studio:studio@localhost:5432/appjs")
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

    # End users of apps (studio/endusers): sessions and phone sign-in
    app_session_days: float = 90
    default_phone_country_code: str = "91"  # for 10-digit numbers sent without +<country>
    sms_provider: str = "log"  # log (codes go to the api log; dev only) | msg91 | whatsapp
    otp_secret: SecretStr | None = None  # HMAC key for stored codes; random per process when unset
    otp_ttl_s: int = 300
    otp_resend_after_s: int = 30
    otp_max_attempts: int = 5
    otp_per_phone_per_hour: int = 5
    otp_per_device_per_hour: int = 10
    otp_per_ip_per_hour: int = 30
    # fixed codes for store reviewers / testers, no SMS sent: "[app-slug/]phone:code,...", e.g.
    # "restyle-ai/+919999999999:482913"; guessable codes (000000, 123456, ...) are ignored. Off when empty.
    otp_test_numbers: str = ""
    # development only: every code is this 6-digit value (honoured only with SMS_PROVIDER=log)
    otp_dev_code: str = ""
    msg91_auth_key: SecretStr | None = None
    msg91_template_id: str | None = None  # a DLT-approved OTP template with an ##otp## variable
    msg91_otp_var: str = "otp"
    # SMS_PROVIDER=whatsapp: Meta Cloud API, a system user's permanent token and an approved
    # Authentication template (one body variable for the code, plus a copy-code / one-tap button)
    whatsapp_token: SecretStr | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_template: str | None = None
    whatsapp_language: str = "en"
    whatsapp_api_version: str = "v25.0"
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

    # Payments: autorev (../autorev) runs the gateways; each app stores its autorev app id and key
    autorev_url: str = "http://autorev-api:8000"  # on the Docker network `appjs`
    autorev_timeout_s: float = 20

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
