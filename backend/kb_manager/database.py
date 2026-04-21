"""Async database engine, session factory, and FastAPI dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)

engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    """Create the async engine from settings and bind the session factory."""
    global engine, async_session_factory
    settings = get_settings()
    # Mask password in log output
    safe_url = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "***"
    logger.info("🗄️ Creating async engine → %s", safe_url)
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("🗄️ Session factory bound successfully")
    return engine


async def dispose_engine() -> None:
    """Dispose the engine, releasing all connection pool resources."""
    global engine, async_session_factory
    if engine is not None:
        logger.info("🗄️ Disposing database engine and connection pool...")
        await engine.dispose()
        engine = None
        async_session_factory = None
        logger.info("🗄️ Database engine disposed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    if async_session_factory is None:
        logger.error("❌ Database engine not initialised — call init_engine() first")
        raise RuntimeError("Database engine not initialised. Call init_engine() first.")
    async with async_session_factory() as session:
        yield session
