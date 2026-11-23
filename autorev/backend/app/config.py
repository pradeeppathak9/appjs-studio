from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://autorev:autorev@postgres:5432/autorev"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200  # 30 days

    admin_email: str = "admin@autorev.app"
    # Seeds the first admin only (see _seed_admin). Override with
    # AUTOREV_ADMIN_PASSWORD — never commit a real password here.
    admin_password: str = "change-me-in-production"

    model_config = {"env_prefix": "AUTOREV_"}


settings = Settings()
