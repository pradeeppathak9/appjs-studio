from __future__ import annotations

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from creative.config import Settings

NOTIFY_CHANNEL = "creative_jobs"


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"command_timeout": settings.db_command_timeout_s},
    )


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def listen_connection(settings: Settings) -> asyncpg.Connection:
    """A dedicated connection outside the pool, for LISTEN."""
    return await asyncpg.connect(settings.asyncpg_dsn)


async def current_revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
        if not exists:
            return None
        return await conn.scalar(text("SELECT version_num FROM alembic_version"))


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def alembic_config(url: str | None = None):
    from pathlib import Path

    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


async def require_head(engine: AsyncEngine) -> None:
    current, head = await current_revision(engine), head_revision()
    if current != head:
        raise SystemExit(
            f"Database schema is at {current or 'nothing'}, expected {head}. "
            "Run `creative db upgrade` (in compose: the migrate service)."
        )
