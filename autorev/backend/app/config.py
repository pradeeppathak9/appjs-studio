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

    model_config = {"env_prefix": "AUTOREV_"}


settings = Settings()
