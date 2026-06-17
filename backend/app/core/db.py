from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.environment == "development",
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"statement_cache_size": 0},
)

session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_db(project_id: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        if project_id:
            await session.execute(
                text("SELECT set_config('app.current_project_id', :pid, true)"),
                {"pid": project_id},
            )

        try:
            yield session

        except Exception:
            await session.rollback()
            raise
