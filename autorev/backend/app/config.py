from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://autorev:autorev@postgres:5432/autorev"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200  # 30 days

    # Token for the /setup page that creates the first admin (app/setup.py). If unset, one is
    # generated and printed in the backend log while no admin exists.
    setup_token: SecretStr | None = None

    # Payment gateways this server offers, comma-separated (AUTOREV_GATEWAYS=razorpay runs Razorpay
    # only). A gateway left out has no API routes, no scheduled tasks, and can't be switched on for an app.
    gateways: str = "phonepe,razorpay"

    # Development only: let outbound webhooks go to private / loopback addresses (e.g. Studio on the
    # Docker network). Never in production: it lets an app owner make the worker call internal services.
    webhook_allow_private: bool = False

    model_config = {"env_prefix": "AUTOREV_"}

    def gateway_on(self, name: str) -> bool:
        return name in {g.strip().lower() for g in self.gateways.split(",") if g.strip()}

    @property
    def enabled_gateways(self) -> list[str]:
        return [g for g in ("phonepe", "razorpay") if self.gateway_on(g)]


settings = Settings()
