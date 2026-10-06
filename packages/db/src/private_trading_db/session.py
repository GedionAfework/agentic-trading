from collections.abc import AsyncIterator

from private_trading_core.config import get_settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # NullPool avoids cross-event-loop connection reuse under TestClient on Windows.
        kwargs: dict[str, object] = {
            "pool_pre_ping": True,
            "echo": settings.app_env == "development"
            and settings.log_level.upper() == "DEBUG",
        }
        if settings.app_env == "development":
            kwargs["poolclass"] = NullPool
        # Do not call pgvector.asyncpg.register_vector here: SQLAlchemy's VECTOR
        # bind processor already serializes embeddings to text, and registering
        # the asyncpg codec breaks inserts/queries (expects list, gets string).
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
